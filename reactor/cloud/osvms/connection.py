# Copyright 2013 GridCentric Inc.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from reactor.config import Config
from reactor.cloud.osapi.connection import BaseOsEndpointConfig
from reactor.cloud.osapi.connection import BaseOsConnection

class OsVmsEndpointConfig(BaseOsEndpointConfig):

    instance_id = Config.string(label="Live-Image", order=2,
        validate=lambda self: \
            self.novaclient().servers.get(self.instance_id)._info['status'] == 'BLESSED' or \
            Config.error("Server is not in BLESSED state."),
        description="The live-image to use.")

class Connection(BaseOsConnection):
    """ OpenStack + VMS """

    _ENDPOINT_CONFIG_CLASS = OsVmsEndpointConfig

    def _list_instances(self, config, instance_id):
        """
        Returns a list of instances from the endpoint.
        """
        import novaclient.exceptions
        config = self._endpoint_config(config)
        if instance_id is None:
            if config.filter_instances:
                server = config.novaclient().cobalt.get(config.instance_id)
                return server.list_launched()
            else:
                return config.novaclient().servers.list()
        else:
            try:
                return [config.novaclient().servers.get(instance_id)]
            except novaclient.exceptions.NotFound:
                return []

    def _start_instance(self, config, params):
        config = self._endpoint_config(config)
        server = config.novaclient().cobalt.get(config.instance_id)
        if 'name' in params:
            instance = server.launch(name=params['name'],
                              security_groups=config.security_groups,
                              availability_zone=config.availability_zone,
                              guest_params=params,
                              user_data=self._user_data(config.user_data))
        else:
            instance = server.launch(security_groups=config.security_groups,
                              availability_zone=config.availability_zone,
                              guest_params=params,
                              user_data=self._user_data(config.user_data))
        return instance[0]

    def is_available(self):
        try:
            from novaclient import shell

            # Fetch a list of extension names.
            extension_names = [
                extension.name
                for extension
                in shell.OpenStackComputeShell()._discover_extensions("1.1")
            ]

            # Check that the cobalt extension is installed.
            return (
                "cobalt" in extension_names or
                "cobalt_python_novaclient_ext" in extension_names
            )

        except ImportError:
            return False
