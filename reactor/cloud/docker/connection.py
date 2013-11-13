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
from reactor.cloud.connection import CloudConnection
from reactor.cloud.instance import Instance

import docker

class DockerManagerConfig(Config):

    # Cached client.
    _client = None

    slots = Config.integer(label="Scheduler slots",
        default=1000, order=0,
        validate=lambda self: self.slots >= 0 or \
            Config.error("Slots must be greater than or equal to zero."),
        description="Number of available scheduler slots on this host.")

    def client(self):
        if self._client == None:
            self._client = docker.client.Client()
        return self._client

class DockerEndpointConfig(Config):

    slots = Config.integer(label="Scheduler slots",
        default=10, order=0,
        validate=lambda self: self.slots >= 0 or \
            Config.error("Slots must be greater than or equal to zero."),
        description="Slots required on a host in order to run.")

    image = Config.string(label="Image",
        default="", order=1,
        validate=lambda self: self.image or \
            Config.error("No image provided."),
        description="The docker image to use.")

    command = Config.string(label="Command",
        default="", order=1,
        validate=lambda self: self.command or \
            Config.error("No command provided."),
        description="The command to run inside the container.")

    user = Config.string(label="User",
        default="", order=2,
        description="The user used to run the command.")

    environment = Config.list(label="Environment",
        default=[], order=3,
        validate=lambda self: self.get_environment(),
        description="The environment for the command.")

    def get_environment(self):
        if self.environment:
            # Return as a dictionary of key=value pairs.
            return dict(map(
                lambda x: map(
                    lambda y: y.strip(),
                    x.split("=", 1)),
                self.environment))
        else:
            return {}

    mem_limit = Config.integer(label="Memory limit",
        default=0, order=3,
        validate=lambda self: self.mem_limit >= 0 or \
            Config.error("Memory limit must be non-negative."),
        description="The container memory limit.")

    dns = Config.string(label="DNS Sever",
        default="", order=4,
        description="The DNS server for the container.")

    hostname = Config.string(label="Hostname",
        default="", order=4,
        description="The hostname for the container.")

    def port(self):
        # Extract the port from the endpoint.
        from reactor.endpoint import EndpointConfig
        endpoint_config = EndpointConfig(obj=self)
        return endpoint_config.port

class Connection(CloudConnection):

    """ Docker """

    _MANAGER_CONFIG_CLASS = DockerManagerConfig
    _ENDPOINT_CONFIG_CLASS = DockerEndpointConfig

    def __init__(self, *args, **kwargs):
        super(Connection, self).__init__(*args, **kwargs)

        from . manager import DockerManager
        if kwargs.get('zkobj') != None:
            self._docker = DockerManager(
                zkobj=kwargs.get('zkobj'),
                this_ip=kwargs.get('this_ip'),
                this_url=kwargs.get('this_url'),
                config=self._manager_config())

    def list_instances(self, config, instance_id=None):
        """
        Lists the instances related to a endpoint. The identifier is used to
        identify the related instances in the respective clouds.
        """
        instances = self._docker.instances()
        if instance_id != None:
            if instance_id in instances:
                # Return only this specific instance.
                return [Instance(instance_id, instance_id, [instances.get(instance_id)])]
            else:
                # Return the empty array, nothing found.
                return []
        else:
            # Return all known instances and addresses.
            return map(lambda (x, y): Instance(x, x, [y]), instances.items())

    def start_instance(self, config, params=None):
        """
        Starts a new instance in the cloud using the endpoint.
        NOTE: Will return (Instance, instance_ips).
        """
        (instance_id, instance_ip) = self._docker.start(
            self._endpoint_config(config), params=params)
        if instance_ip is not None:
            instance_ips = [instance_ip]
        else:
            instance_ips = []
        return Instance(instance_id, instance_id, instance_ips), instance_ips

    def delete_instance(self, config, instance_id):
        """
        Remove the instance from the cloud.
        """
        self._docker.delete(instance_id)
