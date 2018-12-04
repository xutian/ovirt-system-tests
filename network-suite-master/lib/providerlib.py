#
# Copyright 2018 Red Hat, Inc.
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
from contextlib import contextmanager

from ovirtsdk4 import types

from lib import syncutil
from lib.sdkentity import SDKRootEntity
from lib.sdkentity import SDKSubEntity
from lib.netlib import Network


class OpenStackImageProviders(SDKRootEntity):

    def create(self, name, url, requires_authentication):
        sdk_type = types.OpenStackImageProvider(
            name=name,
            url=url,
            requires_authentication=requires_authentication
        )
        self._create_sdk_entity(sdk_type)

    def is_provider_available(self, provider_name):
        providers_service = \
            self._parent_sdk_system.openstack_image_providers_service
        try:
            provider = next(provider for provider in providers_service.list()
                            if provider.name == provider_name)
        except StopIteration:
            return False
        provider_service = providers_service.service(provider.id)
        return provider_service is not None

    def wait_until_available(self):
        syncutil.sync(
            exec_func=lambda: self.is_provider_available(
                self.get_sdk_type().name
            ),
            exec_func_args=(),
            success_criteria=lambda s: s
        )

    def _get_parent_service(self, system):
        return system.openstack_image_providers_service


class OpenStackNetworkProvider(SDKRootEntity):

    def create(self, name, url, requires_authentication, username, password,
               authentication_url, tenant_name=None):
        sdk_type = types.OpenStackNetworkProvider(
            name=name,
            url=url,
            requires_authentication=requires_authentication,
            username=username,
            password=password,
            authentication_url=authentication_url,
            tenant_name=tenant_name
        )
        self._create_sdk_entity(sdk_type)

    def _get_parent_service(self, system):
        return system.openstack_network_providers_service

    @contextmanager
    def disable_auto_sync(self):
        orig_auto_sync = self.service.get().auto_sync
        self.service.update(
            types.OpenStackNetworkProvider(auto_sync=False)
        )
        try:
            yield
        finally:
            if orig_auto_sync:
                self.service.update(
                    types.OpenStackNetworkProvider(auto_sync=orig_auto_sync)
                )


class OpenStackNetwork(SDKSubEntity):

    def create(self, name):
        sdk_type = types.OpenStackNetwork(name=name)
        self._create_sdk_entity(sdk_type)

    def _get_parent_service(self, openstack_network_provider):
        return openstack_network_provider.service.networks_service()

    def create_external_network(self, datacenter):
        self.service.import_(
            async=False, data_center=types.DataCenter(id=datacenter.id))
        ovirt_network = Network(datacenter)
        ovirt_network.import_by_name(self.get_sdk_type().name)
        return ovirt_network
