import logging
import traceback
from httplib import HTTPException

from novaclient import shell
from novaclient.v1_1.client import Client as NovaClient

from reactor.config import Config
from reactor.cloud.connection import CloudConnection

class BaseOsEndpointConfig(Config):

    # Cached client.
    _client = None

    # Common authentication elements.
    auth_url = Config.string("auth_url", default="http://localhost:5000/v2.0/", order=0,
        description="The OpenStack authentication URL (OS_AUTH_URL).")

    username = Config.string("username", default="admin", order=1,
        description="The user for authentication (OS_USERNAME).")

    password = Config.string("password", default="admin", order=1,
        description="The api key or password (OS_PASSWORD).")

    tenant_name = Config.string("tenant_name", default="admin", order=1,
        description="The project or tenant (OS_TENANT_NAME).")

    region_name = Config.string("region_name", order=1,
        description="The region (OS_REGION_NAME).")

    # Elements common to launching and booting.
    security_groups = Config.list("security_groups", order=3,
        description="Security groups for new instances.")

    availability_zone = Config.string("availability_zone", order=3,
        description="Availability zone for new instances.")

    def _novaclient(self):
        if self._client is None:
            extensions = shell.OpenStackComputeShell()._discover_extensions("1.1")
            self._client = NovaClient(self.username,
                                      self.password,
                                      self.tenant_name,
                                      self.auth_url,
                                      region_name=self.region_name,
                                      extensions=extensions)
        return self._client

    def _validate(self):
        Config._validate(self)
        assert self._novaclient()

class BaseOsConnection(CloudConnection):

    _ENDPOINT_CONFIG_CLASS = BaseOsEndpointConfig

    def id(self, config, instance):
        return str(instance['id'])

    def name(self, config, instance):
        return instance.get('name', None)

    def addresses(self, config, instance):
        addresses = []
        for network_addresses in instance.get('addresses', {}).values():
            for network_addrs in network_addresses:
                addresses.append(str(network_addrs['addr']))
        return addresses

    def _list_instances(self, config):
        """ 
        Returns a  list of instances from the endpoint. This is implemented by the
        subclasses
        """
        return []

    def list_instances(self, config):
        """
        Lists the instances related to a endpoint. The identifier is used to 
        identify the related instances in the respective clouds.
        """
        # Pull out the _info dictionary from the Server object.
        instances = [instance._info for instance in self._list_instances(config)]
        return sorted(instances, key=lambda x: x.get('created', ""))

    def _start_instance(self, config, params={}):
        """
        Starts a new instance. This is implemented by the subclasses.
        """
        pass

    def start_instance(self, config, params={}):
        """
        Starts a new instance in the cloud using the endpoint.
        """
        try:
            self._start_instance(config, params=params)
        except HTTPException, e:
            traceback.print_exc()
            logging.error("Error starting instance: %s" % str(e))

    def _delete_instance(self, config, instance_id):
        try:
            config = self._endpoint_config(config)
            config._novaclient().servers._delete("/servers/%s" % (instance_id))
        except HTTPException, e:
            traceback.print_exc()
            logging.error("Error starting instance: %s" % str(e))

    def delete_instance(self, config, instance_id):
        """
        Remove the instance from the cloud.
        """
        self._delete_instance(config, instance_id)

class OsApiEndpointConfig(BaseOsEndpointConfig):

    instance_name = Config.string("instance_name", order=2,
        description="The name given to new instances.")

    flavor_id = Config.string("flavor_id", order=2,
        description="The flavor to use.")

    image_id = Config.string("image_id", order=2,
        description="The image ID to boot.")

    key_name = Config.string("key_name", order=2,
        description="The key_name (for injection).")

    def _validate(self):
        BaseOsEndpointConfig._validate(self)
        client = self._novaclient()
        assert self.image_id in [image._info['id'] for image in client.images.list()]
        assert self.flavor_id in [flavor._info['id'] for flavor in client.flavors.list()]
        assert self.key_name in [key._info['keypair']['name'] for key in client.keypairs.list()]

class Connection(BaseOsConnection):

    _ENDPOINT_CONFIG_CLASS = OsApiEndpointConfig

    def _list_instances(self, config):
        """ 
        Returns a  list of instances from the endpoint.
        """
        config = self._endpoint_config(config)
        search_opts = {
            'name': config.instance_name,
            'flavor': config.flavor_id,
            'image': config.image_id
        }
        instances = config._novaclient().servers.list(search_opts=search_opts)
        return instances

    def _start_instance(self, config, params={}):
        # TODO: We can pass in the reactor parameter here via 
        # CloudStart or some other standard support mechanism.
        config = self._endpoint_config(config)
        userdata = "reactor=%s" % params.get('reactor', '')
        config._novaclient().servers.create(
                                  config.instance_name,
                                  config.image_id,
                                  config.flavor_id,
                                  security_groups=config.security_groups,
                                  key_name=config.key_name,
                                  availability_zone=config.availability_zone,
                                  userdata=userdata)
