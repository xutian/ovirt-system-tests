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

from ovirtlago import testlib
from ovirtsdk4 import Error as sdkError
from ovirtsdk4.types import (BootProtocol, DataCenter, HostNic, Ip,
                             IpAddressAssignment, IpVersion, Network,
                             NetworkAttachment)
import httplib
import test_utils
from test_utils import constants


def _get_attachment_by_id(host, network_id):
    return next(att for att in host.network_attachments_service().list()
                if att.network.id == network_id)


def attach_network_to_host(host, nic_name, network_name, ip_configuration,
                           bonds=[]):
    attachment = NetworkAttachment(
        network=Network(name=network_name),
        host_nic=HostNic(name=nic_name),
        ip_address_assignments=ip_configuration)

    testlib.assert_equals_within_short(
        lambda:
        _setup_host_networks_without_conflict(
            host=host,
            modified_bonds=bonds,
            modified_network_attachments=[attachment],
            check_connectivity=True), True, [])


def detach_network_from_host(engine, host, network_name, bond_name=None):
    network_id = engine.networks_service().list(
        search=u'name={}'.format(
            test_utils.quote_search_string(network_name)).encode('utf-8'))[0].id

    attachment = _get_attachment_by_id(host, network_id)
    bonds = [nic for nic in host.nics_service().list() if bond_name and
             nic.name == bond_name]  # there is no more than one bond
    testlib.assert_equals_within_short(
        lambda:
        _setup_host_networks_without_conflict(
            host=host,
            removed_bonds=bonds,
            removed_network_attachments=[attachment],
            check_connectivity=True), True, [])


def modify_ip_config(engine, host, network_name, ip_configuration):
    network_id = engine.networks_service().list(
        search=u'name={}'.format(
            test_utils.quote_search_string(network_name)).encode('utf-8'))[0].id

    attachment = _get_attachment_by_id(host, network_id)
    attachment.ip_address_assignments = ip_configuration

    testlib.assert_equals_within_short(
        lambda:
        _setup_host_networks_without_conflict(
            host=host,
            modified_network_attachments=[attachment],
            check_connectivity=True), True, [])


def create_dhcp_ip_configuration():
    return [
        IpAddressAssignment(assignment_method=BootProtocol.DHCP),
        IpAddressAssignment(assignment_method=BootProtocol.DHCP,
                            ip=Ip(version=IpVersion.V6))
    ]


def create_static_ip_configuration(ipv4_addr=None, ipv4_mask=None,
                                   ipv6_addr=None, ipv6_mask=None):
    assignments = []
    if ipv4_addr:
        assignments.append(IpAddressAssignment(
            assignment_method=BootProtocol.STATIC,
            ip=Ip(
                address=ipv4_addr,
                netmask=ipv4_mask)))
    if ipv6_addr:
        assignments.append(IpAddressAssignment(
            assignment_method=BootProtocol.STATIC,
            ip=Ip(
                address=ipv6_addr,
                netmask=ipv6_mask,
                version=IpVersion.V6)))

    return assignments


def get_network_attachment(engine, host, network_name, dc_name):
    dc = test_utils.data_center_service(engine, dc_name)

    # CAVEAT: .list(search='name=Migration_Network') is ignored, and the first
    #         network returned happened to be VM_Network in my case
    network = next(net for net in dc.networks_service().list()
                   if net.name == network_name)

    return _get_attachment_by_id(host, network.id)


def set_network_usages_in_cluster(engine, network_name, cluster_name, usages):
    cluster_service = test_utils.get_cluster_service(engine, cluster_name)

    network = engine.networks_service().list(
        search=u'name={}'.format(
            test_utils.quote_search_string(network_name)).encode('utf-8'))[0]
    network_service = cluster_service.networks_service().network_service(
        id=network.id)

    network.usages = usages

    return network_service.update(network)


def set_network_required_in_cluster(engine, network_name, cluster_name,
                                    required):
    cluster_service = test_utils.get_cluster_service(engine, cluster_name)

    network = engine.networks_service().list(
        search=u'name={}'.format(
            test_utils.quote_search_string(network_name)).encode('utf-8'))[0]
    network_service = cluster_service.networks_service().network_service(
        id=network.id)

    network.required = required

    return network_service.update(network)


def set_network_mtu(engine, network_name, dc_name, mtu):
    dc = test_utils.data_center_service(engine, dc_name)

    network = next(net for net in dc.networks_service().list()
                   if net.name == network_name)
    network_service = dc.networks_service().network_service(id=network.id)

    network.mtu = mtu

    return network_service.update(network)


def create_network_params(network_name, dc_name, **net_params):
    return Network(
        name=network_name,
        data_center=DataCenter(
            name=dc_name,
        ),
        **net_params
    )


def get_default_ovn_provider_id(engine):
    service = engine.openstack_network_providers_service()
    for provider in service.list():
        if provider.name == constants.DEFAULT_OVN_PROVIDER_NAME:
            return provider.id
    raise Exception('%s not present in oVirt' %
                    constants.DEFAULT_OVN_PROVIDER_NAME)


def _setup_host_networks_without_conflict(
        host,
        removed_bonds=None,
        modified_bonds=None,
        modified_network_attachments=None,
        removed_network_attachments=None,
        check_connectivity=False):
    try:
        host.setup_networks(
            removed_bonds=removed_bonds,
            modified_bonds=modified_bonds,
            modified_network_attachments=modified_network_attachments,
            removed_network_attachments=removed_network_attachments,
            check_connectivity=check_connectivity)
        return True
    except sdkError as e:
        if e.code == httplib.CONFLICT:
            return False
        else:
            raise
