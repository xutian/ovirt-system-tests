#
# Copyright 2017 Red Hat, Inc.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301 USA
#
# Refer to the README and COPYING files for full details of the license
#

import os
import random

import nose.tools as nt
from nose import SkipTest
from ovirtsdk.infrastructure import errors
from ovirtsdk.xml import params

# TODO: import individual SDKv4 types directly (but don't forget sdk4.Error)
import ovirtsdk4 as sdk4

from lago import utils
from ovirtlago import testlib

import test_utils
from test_utils import network_utils_v4

API_V4 = True
MB = 2 ** 20

# DC/Cluster
DC_NAME = 'performance-dc'
DC_VER_MAJ = 4
DC_VER_MIN = 2
SD_FORMAT = 'v4'
CLUSTER_NAME = 'performance-cluster'
DC_QUOTA_NAME = 'DC-QUOTA'

# Storage
MASTER_SD_TYPE = 'nfs'

# Simulate Hosts and Vms
USE_VDSMFAKE = os.environ.has_key('OST_USE_VDSMFAKE')
VMS_COUNT = int(os.environ.get('OST_VM_COUNT', 100))
HOST_COUNT = int(os.environ.get('OST_HOST_COUNT', 10))
VM_NAME = "vm"
VM_TEMPLATE = "template"
POOL_NAME = "pool"
TEMPLATE_BLANK = 'Blank'
VM1_NAME='vm1'
GLANCE_IMAGE_TO_IMPORT = 'CirrOS 0.4.0 for x86_64'

SD_NFS_NAME = 'nfs'
SD_SECOND_NFS_NAME = 'second-nfs'
SD_NFS_HOST_NAME = testlib.get_prefixed_name('engine')
SD_NFS_PATH = '/exports/nfs/share1'
SD_SECOND_NFS_PATH = '/exports/nfs/share2'

SD_ISCSI_NAME = 'iscsi'
SD_ISCSI_HOST_NAME = testlib.get_prefixed_name('engine')
SD_ISCSI_TARGET = 'iqn.2014-07.org.ovirt:storage'
SD_ISCSI_PORT = 3260
SD_ISCSI_NR_LUNS = 2

SD_ISO_NAME = 'iso'
SD_ISO_HOST_NAME = SD_NFS_HOST_NAME
SD_ISO_PATH = '/exports/nfs/iso'

SD_TEMPLATES_NAME = 'templates'
SD_TEMPLATES_HOST_NAME = SD_NFS_HOST_NAME
SD_TEMPLATES_PATH = '/exports/nfs/exported'

SD_GLANCE_NAME = 'ovirt-image-repository'
GLANCE_AVAIL = False
CIRROS_IMAGE_NAME = 'CirrOS 0.4.0 for x86_64'
GLANCE_DISK_NAME = CIRROS_IMAGE_NAME.replace(" ", "_") + '_glance_disk'
TEMPLATE_CIRROS = CIRROS_IMAGE_NAME.replace(" ", "_") + '_glance_template'
GLANCE_SERVER_URL = 'http://glance.ovirt.org:9292/'

# Network
VM_NETWORK = 'VM_Network'
VM_NETWORK_VLAN_ID = 100
MIGRATION_NETWORK = 'Migration_Net'


@testlib.with_ovirt_prefix
def vdsmfake_setup(prefix):
    """
    Prepare a large setup using vdsmfake
    """

    playbookName = 'vdsmfake-setup.yml'
    engine = prefix.virt_env.engine_vm()
    playbook = os.path.join(os.environ.get('SUITE'),
                            'test-scenarios', playbookName)

    engine.copy_to(playbook, '/tmp/%s' % playbookName)

    result = engine.ssh(['ansible-playbook /tmp/%s' % playbookName])

    nt.eq_(
        result.code, 0, 'Setting up vdsmfake failed.'
                        ' Exit code is %s' % result.code
    )


# TODO: support resolving hosts over IPv6 and arbitrary network
def _get_host_ip(prefix, host_name):
    return prefix.virt_env.get_vm(host_name).ip()

def _get_host_all_ips(prefix, host_name):
    return prefix.virt_env.get_vm(host_name).all_ips()

def _hosts_in_dc(api, dc_name=DC_NAME):
    hosts = api.hosts.list(query='datacenter={} AND status=up'.format(dc_name))
    if hosts:
        return sorted(hosts, key=lambda host: host.name)
    raise RuntimeError('Could not find hosts that are up in DC %s' % dc_name)

def _hosts_in_dc_4(api, dc_name=DC_NAME, random_host=False):
    hosts_service = api.system_service().hosts_service()
    hosts = hosts_service.list(search='datacenter={} AND status=up'.format(dc_name))
    if hosts:
        if random_host:
            return random.choice(hosts)
        else:
            return sorted(hosts, key=lambda host: host.name)
    raise RuntimeError('Could not find hosts that are up in DC %s' % dc_name)

def _random_host_from_dc(api, dc_name=DC_NAME):
    return random.choice(_hosts_in_dc(api, dc_name))

def _random_host_from_dc_4(api, dc_name=DC_NAME):
    return _hosts_in_dc_4(api, dc_name, True)

def _all_hosts_up(hosts_service, total_hosts):
    installing_hosts = hosts_service.list(search='datacenter={} AND status=installing or status=initializing'.format(DC_NAME))
    if len(installing_hosts) == len(total_hosts): # All hosts still installing
        return False

    up_hosts = hosts_service.list(search='datacenter={} AND status=up'.format(DC_NAME))
    if len(up_hosts) == len(total_hosts):
        return True

    _check_problematic_hosts(hosts_service)

def _single_host_up(hosts_service, total_hosts):
    installing_hosts = hosts_service.list(search='datacenter={} AND status=installing or status=initializing'.format(DC_NAME))
    if len(installing_hosts) == len(total_hosts): # All hosts still installing
        return False

    up_hosts = hosts_service.list(search='datacenter={} AND status=up'.format(DC_NAME))
    if len(up_hosts):
        return True

    _check_problematic_hosts(hosts_service)

def _check_problematic_hosts(hosts_service):
    problematic_hosts = hosts_service.list(search='datacenter={} AND status=nonoperational or status=installfailed'.format(DC_NAME))
    if len(problematic_hosts):
        dump_hosts = '%s hosts failed installation:\n' % len(problematic_hosts)
        for host in problematic_hosts:
            host_service = hosts_service.host_service(host.id)
            dump_hosts += '%s: %s\n' % (host.name, host_service.get().status)
        raise RuntimeError(dump_hosts)


@testlib.with_ovirt_prefix
def add_dc(prefix):
    if API_V4:
        api = prefix.virt_env.engine_vm().get_api(api_ver=4)
        add_dc_4(api)
    else:
        api = prefix.virt_env.engine_vm().get_api()
        add_dc_3(api)


def add_dc_3(api):
    p = params.DataCenter(
        name=DC_NAME,
        local=False,
        version=params.Version(
            major=DC_VER_MAJ,
            minor=DC_VER_MIN,
        ),
    )
    nt.assert_true(api.datacenters.add(p))


def add_dc_4(api):
    dcs_service = api.system_service().data_centers_service()
    nt.assert_true(
        dcs_service.add(
            sdk4.types.DataCenter(
                name=DC_NAME,
                description='APIv4 DC',
                local=False,
                version=sdk4.types.Version(major=DC_VER_MAJ,minor=DC_VER_MIN),
            ),
        )
    )


@testlib.with_ovirt_prefix
def add_cluster(prefix):
    api = prefix.virt_env.engine_vm().get_api(api_ver=4)
    clusters_service = api.system_service().clusters_service()
    nt.assert_true(
        clusters_service.add(
            sdk4.types.Cluster(
                name=CLUSTER_NAME,
                description='APIv4 Cluster',
                data_center=sdk4.types.DataCenter(
                    name=DC_NAME,
                ),
                ballooning_enabled=True,
            ),
        )
    )


class FakeHostVm:
    def __init__(self, name):
        self._name = name

    def name(self):
        return self._name

    def root_password(self):
        return 'password'


def get_fake_hosts():
    return [FakeHostVm('%s.vdsm.fake' % i) for i in range(1, HOST_COUNT)]

@testlib.with_ovirt_prefix
def add_hosts(prefix):
    hosts = get_fake_hosts() if USE_VDSMFAKE else prefix.virt_env.host_vms()
    if not USE_VDSMFAKE:
        for host in hosts:
            host.ssh(['ntpdate', '-4', testlib.get_prefixed_name('engine')])

    api = prefix.virt_env.engine_vm().get_api_v4()
    add_hosts_4(api, hosts)


def add_hosts_4(api, hosts):
    hosts_service = api.system_service().hosts_service()

    def _add_host_4(vm):
        return hosts_service.add(
            sdk4.types.Host(
                name=vm.name(),
                description='host %s' % vm.name(),
                address=vm.name(),
                root_password=str(vm.root_password()),
                override_iptables=True,
                cluster=sdk4.types.Cluster(
                    name=CLUSTER_NAME,
                ),
            ),
        )

    for host in hosts:
        nt.assert_true(
            _add_host_4(host)
        )


@testlib.with_ovirt_prefix
def verify_add_hosts(prefix):
    hosts = prefix.virt_env.host_vms()

    api = prefix.virt_env.engine_vm().get_api_v4()
    verify_add_hosts_4(api)


def verify_add_hosts_4(api):
    hosts_service = api.system_service().hosts_service()
    total_hosts = hosts_service.list(search='datacenter={}'.format(DC_NAME))

    testlib.assert_true_within_long(
        lambda: _single_host_up(hosts_service, total_hosts)
    )

@testlib.with_ovirt_prefix
def verify_add_all_hosts(prefix):
    api = prefix.virt_env.engine_vm().get_api_v4()
    hosts_service = api.system_service().hosts_service()
    total_hosts = hosts_service.list(search='datacenter={}'.format(DC_NAME))

    testlib.assert_true_within_long(
        lambda: _all_hosts_up(hosts_service, total_hosts)
    )

    if not USE_VDSMFAKE:
        for host in prefix.virt_env.host_vms():
            host.ssh(['rm', '-rf', '/dev/shm/yum', '/dev/shm/*.rpm'])


def _add_storage_domain_4(api, p):
    system_service = api.system_service()
    sds_service = system_service.storage_domains_service()
    sd = sds_service.add(p)

    sd_service = sds_service.storage_domain_service(sd.id)
    testlib.assert_true_within_long(
        lambda: sd_service.get().status == sdk4.types.StorageDomainStatus.UNATTACHED
    )

    dc_service = test_utils.data_center_service(system_service, DC_NAME)
    attached_sds_service = dc_service.storage_domains_service()
    attached_sds_service.add(
        sdk4.types.StorageDomain(
            id=sd.id,
        ),
    )

    attached_sd_service = attached_sds_service.storage_domain_service(sd.id)
    testlib.assert_true_within_long(
        lambda: attached_sd_service.get().status == sdk4.types.StorageDomainStatus.ACTIVE
    )


@testlib.with_ovirt_prefix
def add_master_storage_domain(prefix):
    if MASTER_SD_TYPE == 'iscsi':
        add_iscsi_storage_domain(prefix)
    else:
        add_nfs_storage_domain(prefix)


def add_nfs_storage_domain(prefix):
    add_generic_nfs_storage_domain_4(prefix, SD_NFS_NAME, SD_NFS_HOST_NAME, SD_NFS_PATH, nfs_version='v4_2')


# TODO: add this over the storage network and with IPv6
def add_second_nfs_storage_domain(prefix):
    add_generic_nfs_storage_domain_4(prefix, SD_SECOND_NFS_NAME,
                                   SD_NFS_HOST_NAME, SD_SECOND_NFS_PATH)


def add_generic_nfs_storage_domain_4(prefix, sd_nfs_name, nfs_host_name, mount_path, sd_format=SD_FORMAT, sd_type='data', nfs_version='v4_1'):
    if sd_type == 'data':
        dom_type = sdk4.types.StorageDomainType.DATA
    elif sd_type == 'iso':
        dom_type = sdk4.types.StorageDomainType.ISO
    elif sd_type == 'export':
        dom_type = sdk4.types.StorageDomainType.EXPORT

    if nfs_version == 'v3':
        nfs_vers = sdk4.types.NfsVersion.V3
    elif nfs_version == 'v4':
        nfs_vers = sdk4.types.NfsVersion.V4
    elif nfs_version == 'v4_1':
        nfs_vers = sdk4.types.NfsVersion.V4_1
    elif nfs_version == 'v4_2':
        nfs_vers = sdk4.types.NfsVersion.V4_2
    else:
        nfs_vers = sdk4.types.NfsVersion.AUTO

    api = prefix.virt_env.engine_vm().get_api(api_ver=4)
    p = sdk4.types.StorageDomain(
        name=sd_nfs_name,
        description='APIv4 NFS storage domain',
        type=dom_type,
        host=_random_host_from_dc_4(api, DC_NAME),
        storage=sdk4.types.HostStorage(
            type=sdk4.types.StorageType.NFS,
            address=_get_host_ip(prefix, nfs_host_name),
            path=mount_path,
            nfs_version=nfs_vers,
        ),
    )

    _add_storage_domain_4(api, p)


def add_iscsi_storage_domain(prefix):
    ret = prefix.virt_env.get_vm(SD_ISCSI_HOST_NAME).ssh(['cat', '/root/multipath.txt'])
    nt.assert_equals(ret.code, 0)
    lun_guids = ret.out.splitlines()[0:SD_ISCSI_NR_LUNS-1]

    add_iscsi_storage_domain_4(prefix, lun_guids)

def add_iscsi_storage_domain_4(prefix, lun_guids):
    api = prefix.virt_env.engine_vm().get_api_v4()

    ips = _get_host_all_ips(prefix, SD_ISCSI_HOST_NAME)
    luns = []
    for lun_id in lun_guids:
        for ip in ips:
            lun=sdk4.types.LogicalUnit(
                id=lun_id,
                address=ip,
                port=SD_ISCSI_PORT,
                target=SD_ISCSI_TARGET,
                username='username',
                password='password',
            )
            luns.append(lun)

    p = sdk4.types.StorageDomain(
        name=SD_ISCSI_NAME,
        description='iSCSI Storage Domain',
        type=sdk4.types.StorageDomainType.DATA,
        discard_after_delete=True,
        data_center=sdk4.types.DataCenter(
            name=DC_NAME,
        ),
        host=_random_host_from_dc_4(api, DC_NAME),
        storage_format=sdk4.types.StorageFormat.V4,
        storage=sdk4.types.HostStorage(
            type=sdk4.types.StorageType.ISCSI,
            override_luns=True,
            volume_group=sdk4.types.VolumeGroup(
                logical_units=luns
            ),
        ),
    )

    _add_storage_domain_4(api, p)


def add_iso_storage_domain(prefix):
    add_generic_nfs_storage_domain_4(prefix, SD_ISO_NAME, SD_ISO_HOST_NAME, SD_ISO_PATH, sd_format='v1', sd_type='iso', nfs_version='v3')


def add_templates_storage_domain(prefix):
    add_generic_nfs_storage_domain_4(prefix, SD_TEMPLATES_NAME, SD_TEMPLATES_HOST_NAME, SD_TEMPLATES_PATH, sd_format='v1', sd_type='export', nfs_version='v4_1')


@testlib.with_ovirt_api
def import_templates(api):
    #TODO: Fix the exported domain generation
    raise SkipTest('Exported domain generation not supported yet')
    templates = api.storagedomains.get(
        SD_TEMPLATES_NAME,
    ).templates.list(
        unregistered=True,
    )

    for template in templates:
        template.register(
            action=params.Action(
                cluster=params.Cluster(
                    name=CLUSTER_NAME,
                ),
            ),
        )

    for template in api.templates.list():
        testlib.assert_true_within_short(
            lambda: api.templates.get(template.name).status.state == 'ok',
        )


def generic_import_from_glance(prefix, image_name=CIRROS_IMAGE_NAME, as_template=False, image_ext='_glance_disk', template_ext='_glance_template', dest_storage_domain=MASTER_SD_TYPE, dest_cluster=CLUSTER_NAME):
    api = prefix.virt_env.engine_vm().get_api()
    glance_provider = api.storagedomains.get(SD_GLANCE_NAME)
    target_image = glance_provider.images.get(name=image_name)
    disk_name = image_name.replace(" ", "_") + image_ext
    template_name = image_name.replace(" ", "_") + template_ext
    import_action = params.Action(
        storage_domain=params.StorageDomain(
            name=dest_storage_domain,
        ),
        cluster=params.Cluster(
            name=dest_cluster,
        ),
        import_as_template=as_template,
        disk=params.Disk(
            name=disk_name,
        ),
        template=params.Template(
            name=template_name,
        ),
    )

    nt.assert_true(
        target_image.import_image(import_action)
    )



@testlib.with_ovirt_api
def verify_glance_import(api):
    for disk_name in (GLANCE_DISK_NAME, TEMPLATE_CIRROS):
        testlib.assert_true_within_long(
            lambda: api.disks.get(disk_name).status.state == 'ok',
        )


@testlib.with_ovirt_prefix
def list_glance_images(prefix):
    if API_V4:
        api = prefix.virt_env.engine_vm().get_api(api_ver=4)
        list_glance_images_4(api)
    else:
        api = prefix.virt_env.engine_vm().get_api()
        list_glance_images_3(api)


def list_glance_images_3(api):
    global GLANCE_AVAIL
    glance_provider = api.storagedomains.get(SD_GLANCE_NAME)
    if glance_provider is None:
        openstack_glance = add_glance_3(api)
        if openstack_glance is None:
            raise SkipTest('%s: GLANCE storage domain is not available.' % list_glance_images_3.__name__ )
        glance_provider = api.storagedomains.get(SD_GLANCE_NAME)

    if not check_glance_connectivity_3(api):
        raise SkipTest('%s: GLANCE connectivity test failed' % list_glance_images_3.__name__ )

    try:
        all_images = glance_provider.images.list()
        if len(all_images):
            GLANCE_AVAIL = True
    except errors.RequestError:
        raise SkipTest('%s: GLANCE is not available: client request error' % list_glance_images_3.__name__ )


def list_glance_images_4(api):
    global GLANCE_AVAIL
    search_query = 'name={}'.format(SD_GLANCE_NAME)
    storage_domains_service = api.system_service().storage_domains_service()
    glance_domain_list = storage_domains_service.list(search=search_query)

    if not glance_domain_list:
        openstack_glance = add_glance_4(api)
        if not openstack_glance:
            raise SkipTest('%s GLANCE storage domain is not available.' % list_glance_images_4.__name__ )
        glance_domain_list = storage_domains_service.list(search=search_query)

    if not check_glance_connectivity_4(api):
        raise SkipTest('%s: GLANCE connectivity test failed' % list_glance_images_4.__name__ )

    glance_domain = glance_domain_list.pop()
    glance_domain_service = storage_domains_service.storage_domain_service(glance_domain.id)

    try:
        all_images = glance_domain_service.images_service().list()
        if len(all_images):
            GLANCE_AVAIL = True
    except sdk4.Error:
        raise SkipTest('%s: GLANCE is not available: client request error' % list_glance_images_4.__name__ )


def add_glance_3(api):
    target_server = params.OpenStackImageProvider(
        name=SD_GLANCE_NAME,
        url=GLANCE_SERVER_URL
    )
    try:
        provider = api.openstackimageproviders.add(target_server)
        glance = []

        def get():
            instance = api.openstackimageproviders.get(id=provider.get_id())
            if instance:
                glance.append(instance)
                return True
            else:
                return False

        testlib.assert_true_within_short(func=get, allowed_exceptions=[errors.RequestError])
    except (AssertionError, errors.RequestError):
        # RequestError if add method was failed.
        # AssertionError if add method succeed but we couldn't verify that glance was actually added
        return None

    return glance.pop()


def add_glance_4(api):
    target_server = sdk4.types.OpenStackImageProvider(
        name=SD_GLANCE_NAME,
        description=SD_GLANCE_NAME,
        url=GLANCE_SERVER_URL,
        requires_authentication=False
    )

    try:
        providers_service = api.system_service().openstack_image_providers_service()
        providers_service.add(target_server)
        glance = []

        def get():
            providers = [
                provider for provider in providers_service.list()
                if provider.name == SD_GLANCE_NAME
            ]
            if not providers:
                return False
            instance = providers_service.provider_service(providers.pop().id)
            if instance:
                glance.append(instance)
                return True
            else:
                return False

        testlib.assert_true_within_short(func=get, allowed_exceptions=[errors.RequestError])
    except (AssertionError, errors.RequestError):
        # RequestError if add method was failed.
        # AssertionError if add method succeed but we couldn't verify that glance was actually added
        return None

    return glance.pop()


def check_glance_connectivity_3(api):
    avail = False
    try:
        glance = api.openstackimageproviders.get(name=SD_GLANCE_NAME)
        glance.testconnectivity()
        avail = True
    except errors.RequestError:
        pass

    return avail


def check_glance_connectivity_4(api):
    avail = False
    providers_service = api.system_service().openstack_image_providers_service()
    providers = [
        provider for provider in providers_service.list()
        if provider.name == SD_GLANCE_NAME
    ]
    if providers:
        glance = providers_service.provider_service(providers.pop().id)
        try:
            glance.test_connectivity()
            avail = True
        except sdk4.Error:
            pass

    return avail


def import_non_template_from_glance(prefix):
    if not GLANCE_AVAIL:
        raise SkipTest('%s: GLANCE is not available.' % import_non_template_from_glance.__name__ )
    generic_import_from_glance(prefix)


def import_template_from_glance(prefix):
    if not GLANCE_AVAIL:
        raise SkipTest('%s: GLANCE is not available.' % import_template_from_glance.__name__ )
    generic_import_from_glance(prefix, image_name=CIRROS_IMAGE_NAME, image_ext='_glance_template', as_template=True)


@testlib.with_ovirt_api
def set_dc_quota_audit(api):
    dc = api.datacenters.get(name=DC_NAME)
    dc.set_quota_mode('audit')
    nt.assert_true(
        dc.update()
    )


@testlib.with_ovirt_api
def add_quota_storage_limits(api):
    dc = api.datacenters.get(DC_NAME)
    quota = dc.quotas.get(name=DC_QUOTA_NAME)
    quota_storage = params.QuotaStorageLimit(limit=500)
    nt.assert_true(
        quota.quotastoragelimits.add(quota_storage)
    )


@testlib.with_ovirt_api
def add_quota_cluster_limits(api):
    dc = api.datacenters.get(DC_NAME)
    quota = dc.quotas.get(name=DC_QUOTA_NAME)
    quota_cluster = params.QuotaClusterLimit(vcpu_limit=20, memory_limit=10000)
    nt.assert_true(
        quota.quotaclusterlimits.add(quota_cluster)
    )


@testlib.with_ovirt_api4
def add_vm_blank(api):
    vm_memory = 512 * MB
    vm_params = params.VM(
        memory=vm_memory,
        os=params.OperatingSystem(
            type_='other_linux',
        ),
        type_='server',
        high_availability=params.HighAvailability(
            enabled=True,
        ),
        cluster=params.Cluster(
            name=CLUSTER_NAME,
        ),
        template=params.Template(
            name=TEMPLATE_BLANK,
        ),
        display=params.Display(
            smartcard_enabled=True,
            keyboard_layout='en-us',
            file_transfer_enabled=True,
            copy_paste_enabled=True,
        ),
        memory_policy=params.MemoryPolicy(
            guaranteed=vm_memory / 2,
        ),
    )

    vm_params.name = VM_TEMPLATE
    api.vms.add(vm_params)
    testlib.assert_true_within_short(
        lambda: api.vms.get(VM_TEMPLATE).status.state == 'down',
    )


@testlib.with_ovirt_api4
def add_nic(api):
    NIC_NAME = 'eth0'
    nic_params = params.NIC(
        name=NIC_NAME,
        interface='virtio',
        network=params.Network(
            name='ovirtmgmt',
        ),
    )
    api.vms.get(VM_TEMPLATE).nics.add(nic_params)


@testlib.with_ovirt_api4
def add_vm_template(api):
    sds = api.system_service().storage_domains_service()
    sd = sds.list(search='name=ovirt-image-repository')[0]
    sd_service = sds.storage_domain_service(sd.id)
    images_service = sd_service.images_service()
    images = images_service.list()

    image = next(
        (i for i in images if i.name == GLANCE_IMAGE_TO_IMPORT),
        None
    )

    # Find the service that manages the image that we found in the previous
    # step:
    image_service = images_service.image_service(image.id)

    # Import the image:
    image_service.import_(
        import_as_template=True,
        template=sdk4.types.Template(
            name=VM_TEMPLATE
        ),
        cluster=sdk4.types.Cluster(
            name=CLUSTER_NAME
        ),
        storage_domain=sdk4.types.StorageDomain(
            name=SD_NFS_NAME
        )
    )

    templates_service = api.system_service().templates_service()
    getTemplate = lambda: templates_service.list(search="name=%s" % VM_TEMPLATE)
    testlib.assert_true_within(
        lambda: len(getTemplate()) == 1 and
                sdk4.types.TemplateStatus.OK == getTemplate()[0].status,
        timeout=300
    )


@testlib.with_ovirt_api4
def add_vms(api):
    vm_pools_service = api.system_service().vm_pools_service()

    # Use the "add" method to create a new virtual machine pool:
    vm_pools_service.add(
        pool=sdk4.types.VmPool(
            name=POOL_NAME,
            cluster=sdk4.types.Cluster(
                name=CLUSTER_NAME,
            ),
            template=sdk4.types.Template(
                name=VM_TEMPLATE,
            ),
            size=VMS_COUNT,
            prestarted_vms=VMS_COUNT,
            max_user_vms=1,
        ),
    )

_TEST_LIST = [
    add_dc,
    add_cluster,
    add_hosts,
    verify_add_hosts,
    add_master_storage_domain,
    add_vm_template,
    verify_add_all_hosts,
    add_vms,
]


def test_gen():
    if USE_VDSMFAKE:
        _TEST_LIST.insert(0, vdsmfake_setup)
    for t in testlib.test_sequence_gen(_TEST_LIST):
        test_gen.__name__ = t.description
        yield t
