import logging
import traceback
from httplib import HTTPException

from novaclient import shell
from novaclient.v1_1.client import Client as NovaClient
import novaclient.exceptions

from reactor.config import Config
from reactor.cloud.connection import CloudConnection

class BaseOsEndpointConfig(Config):

    # Cached client.
    _client = None

    # Common authentication elements.
    auth_url = Config.string(label="OpenStack Auth URL",
        default="http://localhost:5000/v2.0/", order=0,
        validate=lambda self: self._validate_connection_params(),
        alternates=["authurl"],
        description="The OpenStack authentication URL (OS_AUTH_URL).")

    username = Config.string(label="OpenStack User",
        default="admin", order=1,
        alternates=["user"],
        description="The user for authentication (OS_USERNAME).")

    password = Config.string(label="OpenStack Password",
        default="admin", order=2,
        alternates=["apikey"],
        description="The api key or password (OS_PASSWORD).")

    tenant_name = Config.string("OpenStack Tenant/Project",
        default="admin", order=3,
        alternates=["project"],
        description="The project or tenant (OS_TENANT_NAME).")

    region_name = Config.string(label="Region Name",
        order=4,
        description="The region (OS_REGION_NAME).")

    # Elements common to launching and booting.
    security_groups = Config.list(label="Security Groups",
        order=5, description="Security groups for new instances.")

    availability_zone = Config.string(label="Availability Zone", order=5,
        description="Availability zone for new instances.")

    def _novaclient(self):
        if self._client is None:
            extensions = shell.OpenStackComputeShell()._discover_extensions("1.1")
            self._client = NovaClient(self.username,
                                      self.password,
                                      self.tenant_name,
                                      self.auth_url,
                                      region_name=self.region_name,
                                      service_type="compute",
                                      extensions=extensions)
        return self._client

    def _validate_connection_params(self, throwerror=True):
        try:
            self._novaclient().authenticate()
        except Exception, e:
            if throwerror:
                # If we got an unathorized exception, propagate
                if type(e) == novaclient.exceptions.Unauthorized:
                    Config.error(e.message)
                elif type(e) == novaclient.exceptions.EndpointNotFound:
                    Config.error("Problem connecting to cloud endpoint. Bad Region?")
                # Else it could be a number of things
                else:
                    Config.error("Could not connect to OpenStack cloud. Bad URL?")
            else:
                return False
        return True

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
            return self._start_instance(config, params=params)
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

    instance_name = Config.string(label="Instance Name", order=2,
        description="The name given to new instances.")

    flavor_id = Config.string(label="Flavor", order=2,
        validate=lambda self: self._validate_flavor(),
        description="The flavor to use.")

    image_id = Config.string(label="Image", order=2,
        validate=lambda self: self._validate_image(),
        description="The image ID to boot.")

    key_name = Config.string(label="Key Name", order=2,
        validate=lambda self: self._validate_keyname(),
        description="The key_name (for injection).")

    def _validate_flavor(self):
        if self._validate_connection_params(False):
            avail = [flavor._info['id'] for flavor in self._novaclient().flavors.list()]
            if self.flavor_id in avail:
                return True
            else:
                Config.error("Flavor %s not found" % self.flavor_id)
        else:
            # Can't connect to cloud, ignore this param for now
            return True

    def _validate_image(self):
        if self._validate_connection_params(False):
            avail = [image._info['id'] for image in self._novaclient().images.list()]
            if self.image_id in avail:
                return True
            else:
                Config.error("Image %s not found" % self.image_id)
        else:
            # Can't connect to cloud, ignore this param for now
            return True

    def _validate_keyname(self):
        if self._validate_connection_params(False):
            avail = [key._info['keypair']['name'] for key in self._novaclient().keypairs.list()]
            if self.key_name in avail:
                return True
            else:
                Config.error("Keyname %s not found" % self.key_name)
        else:
            # Can't connect to cloud, ignore this param for now
            return True

class Connection(BaseOsConnection):

    _ENDPOINT_CONFIG_CLASS = OsApiEndpointConfig

    def description(self):
        return "OpenStack"

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
        instance = config._novaclient().servers.create(
                                  config.instance_name,
                                  config.image_id,
                                  config.flavor_id,
                                  security_groups=config.security_groups,
                                  key_name=config.key_name,
                                  availability_zone=config.availability_zone,
                                  userdata=userdata)
        return instance[0].id
