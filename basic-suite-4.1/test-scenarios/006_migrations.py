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

import nose.tools as nt
from ovirtlago import testlib
from ovirtsdk.xml import params

import test_utils
from test_utils import network_utils_v3


DC_NAME = 'test-dc'
CLUSTER_NAME = 'test-cluster'

NIC_NAME = 'eth0'
VLAN200_IF_NAME = '{}.200'.format(NIC_NAME)

DEFAULT_MTU = 1500

MIGRATION_NETWORK = 'Migration_Net'
MIGRATION_NETWORK_IPv4_ADDR = '192.0.3.{}'
MIGRATION_NETWORK_IPv4_MASK = '255.255.255.0'
MIGRATION_NETWORK_IPv6_ADDR = '2001:0db8:85a3:0000:0000:574c:14ea:0a0{}'
MIGRATION_NETWORK_IPv6_MASK = '64'

VM0_NAME = 'vm0'


@testlib.with_ovirt_api
def prepare_migration_vlan(api):
    usages = params.Usages(['migration'])

    nt.assert_true(
        network_utils_v3.set_network_usages_in_cluster(
            api, MIGRATION_NETWORK, CLUSTER_NAME, usages)
    )

    # Set Migration_Network's MTU to match the other VLAN's on the NIC.
    nt.assert_true(
        network_utils_v3.set_network_mtu(
            api, MIGRATION_NETWORK, DC_NAME, DEFAULT_MTU)
    )


@testlib.with_ovirt_api
@testlib.with_ovirt_prefix
def migrate_vm(prefix, api):
    def current_running_host():
        host_id = api.vms.get(VM0_NAME).host.id
        return api.hosts.get(id=host_id).name

    src_host = current_running_host()
    dst_host = sorted([h.name() for h in prefix.virt_env.host_vms()
                       if h.name() != src_host])[0]

    migrate_params = params.Action(
        host=params.Host(
            name=dst_host
        ),
    )

    nt.assert_true(
      api.vms.get(VM0_NAME).migrate(migrate_params)
    )

    testlib.assert_true_within_short(
        lambda: api.vms.get(VM0_NAME).status.state == 'up'
    )

    nt.assert_equals(
        current_running_host(), dst_host
    )


@testlib.with_ovirt_api
def prepare_migration_attachments_ipv4(api):
    for index, host in enumerate(
            test_utils.hosts_in_cluster_v3(api, CLUSTER_NAME),
            start=1):
        ip_address = MIGRATION_NETWORK_IPv4_ADDR.format(index)

        ip_configuration = network_utils_v3.create_static_ip_configuration(
            ipv4_addr=ip_address,
            ipv4_mask=MIGRATION_NETWORK_IPv4_MASK)

        network_utils_v3.attach_network_to_host(
            api, host, NIC_NAME, MIGRATION_NETWORK, ip_configuration)

        nt.assert_equals(
            host.nics.list(name=VLAN200_IF_NAME)[0].ip.address,
            ip_address)


_TEST_LIST = [
    prepare_migration_vlan,

    prepare_migration_attachments_ipv4,
    migrate_vm,
]


def test_gen():
    for t in testlib.test_sequence_gen(_TEST_LIST):
        test_gen.__name__ = t.description
        yield t
