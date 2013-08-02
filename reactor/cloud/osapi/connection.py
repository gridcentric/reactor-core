import logging
import time

from novaclient import shell
from novaclient.v1_1.client import Client as NovaClient
import novaclient.exceptions

from reactor.config import Config
from reactor.cloud.connection import CloudConnection
from reactor.cloud.instance import Instance

class BaseOsManagerConfig(Config):

    reactor = Config.string(label="Reactor address",
        default="localhost", order=0,
        description="Used internally by Reactor.")

class BaseOsEndpointConfig(Config):

    # Cached client.
    _client = None

    # Common authentication elements.
    auth_url = Config.string(label="OpenStack Auth URL",
        default="http://localhost:5000/v2.0/", order=0,
        validate=lambda self: self.validate_connection_params(),
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

    list_rate_limit = Config.integer(label="Rate limit",
        default=120, order=1,
        validate=lambda self: self.list_rate_limit >= 0 or \
            Config.error("Rate limit must be non-negative."),
        description="Limit list requests to this often.")

    # Elements common to launching and booting.
    security_groups = Config.list(label="Security Groups",
        order=5, description="Security groups for new instances.")

    availability_zone = Config.string(label="Availability Zone", order=5,
        description="Availability zone for new instances.")

    def novaclient(self):
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

    def validate_connection_params(self, throwerror=True):
        try:
            self.novaclient().authenticate()
        except Exception, e:
            if throwerror:
                # If we got an unathorized exception, propagate.
                if isinstance(e, novaclient.exceptions.Unauthorized):
                    Config.error(e.message)
                elif isinstance(e, novaclient.exceptions.EndpointNotFound):
                    Config.error("Problem connecting to cloud endpoint. Bad Region?")
                else:
                    Config.error("Could not connect to OpenStack cloud. Bad URL?")
            else:
                return False
        return True

class BaseOsConnection(CloudConnection):

    _MANAGER_CONFIG_CLASS = BaseOsManagerConfig
    _ENDPOINT_CONFIG_CLASS = BaseOsEndpointConfig

    def __init__(self, *args, **kwargs):
        super(BaseOsConnection, self).__init__(*args, **kwargs)
        self._list_cache = []
        self._last_refresh = None

    def _list_instances(self, config, instance_id):
        """
        Returns a list of instances from the endpoint.
        (This is implemented by the different subclasses).
        """
        raise NotImplementedError()

    def list_instances(self, config, instance_id=None):
        """
        Lists the instances related to a endpoint. The identifier is used to
        identify the related instances in the respective clouds.
        """
        list_rate_limit = self._endpoint_config(config).list_rate_limit

        if instance_id is not None:
            instances = self._list_instances(config, instance_id)

        elif self._last_refresh is not None and \
            (self._last_refresh + list_rate_limit) > time.time():
            instances = self._list_cache

        else:
            instances = self._list_instances(config, None)
            self._list_cache = instances
            self._last_refresh = time.time()

        instances = sorted(instances, key=lambda x: x._info.get("created", ""))

        def _sanitize(instance):
            # Extract the instance id.
            if hasattr(instance, 'id'):
                id = instance.id
            else:
                id = instance._info['id']

            # Extract the instance name.
            if hasattr(instance, 'name'):
                name = instance.name
            else:
                name = instance._info.get('name', None)

            # Extract all available instance addresses.
            addresses = []
            for network_addresses in instance._info.get('addresses', {}).values():
                for network_addrs in network_addresses:
                    addresses.append(str(network_addrs['addr']))

            return Instance(id, name, addresses)

        # Return all sanitizing instances.
        return map(_sanitize, instances)

    def _start_instance(self, config, params):
        """
        Starts a new instance. This is implemented by the subclasses.
        """
        pass

    def start_instance(self, config, params=None):
        """
        Starts a new instance in the cloud using the endpoint.
        """
        if params is None:
            params = {}

        # Inject the manager parameters.
        params.update({ "reactor" : self._manager_config().reactor })

        # Reset the refresh so no matter what happens,
        # when we next call list() we will have an up
        # to date view of what's running on the cloud.
        self._last_refresh = None

        # Finally, do the start.
        # NOTE: We don't catch any exceptions here,
        # they will be caught in the endpoint so that
        # they can be *logged*.
        return self._start_instance(config, params=params)

    def _delete_instance(self, config, instance_id):
        try:
            config = self._endpoint_config(config)
            config.novaclient().servers._delete("/servers/%s" % (instance_id))
        except novaclient.exceptions.NotFound:
            logging.info("Instance already gone? Weird.")

    def delete_instance(self, config, instance_id):
        """
        Remove the instance from the cloud.
        """
        # NOTE: Like launch_instance, we don't
        # catch all exceptions. Instead we let
        # them reach the endpoint so that they
        # can be logged.
        self._delete_instance(config, instance_id)

        # NOTE: Unlike launch_instance we only
        # reset the cache if the delete is successful.
        # When the launch fails, it's unclear what
        # state the system is in, and it's important
        # to establish truth. If the delete fails,
        # we don't need the instance so it's less
        # critical to get an immediate update.
        self._last_refresh = None

class OsApiEndpointConfig(BaseOsEndpointConfig):

    instance_name = Config.string(label="Instance Name", order=2,
        description="The name given to new instances.")

    flavor_id = Config.string(label="Flavor", order=2,
        validate=lambda self: self.validate_flavor(),
        description="The flavor to use.")

    image_id = Config.string(label="Image", order=2,
        validate=lambda self: self.validate_image(),
        description="The image ID to boot.")

    key_name = Config.string(label="Key Name", order=2,
        validate=lambda self: self.validate_keyname(),
        description="The key_name (for injection).")

    def validate_flavor(self):
        if self.validate_connection_params(False):
            avail = [flavor._info['id'] for flavor in self.novaclient().flavors.list()]
            if self.flavor_id in avail:
                return True
            else:
                Config.error("Flavor %s not found" % self.flavor_id)
        else:
            # Can't connect to cloud, ignore this param for now
            return True

    def validate_image(self):
        if self.validate_connection_params(False):
            avail = [image._info['id'] for image in self.novaclient().images.list()]
            if self.image_id in avail:
                return True
            else:
                Config.error("Image %s not found" % self.image_id)
        else:
            # Can't connect to cloud, ignore this param for now
            return True

    def validate_keyname(self):
        if self.key_name is None:
            # No keyname provided.
            return True
        elif self.validate_connection_params(False):
            avail = [key._info['keypair']['name'] for key in self.novaclient().keypairs.list()]
            if self.key_name in avail:
                return True
            else:
                Config.error("Keyname %s not found" % self.key_name)
        else:
            # Can't connect to cloud, ignore this param for now
            return True

class Connection(BaseOsConnection):
    """ OpenStack """

    _ENDPOINT_CONFIG_CLASS = OsApiEndpointConfig

    def _list_instances(self, config, instance_id):
        """
        Returns a  list of instances from the endpoint.
        """
        config = self._endpoint_config(config)
        if instance_id is None:
            search_opts = {
                'name': config.instance_name,
                'flavor': config.flavor_id,
                'image': config.image_id
            }
            return config.novaclient().servers.list(search_opts=search_opts)
        else:
            try:
                return [config.novaclient().servers.get(instance_id)]
            except novaclient.exceptions.NotFound:
                return []

    def _start_instance(self, config, params):
        config = self._endpoint_config(config)
        userdata = "reactor=%s" % params.get('reactor', '')
        instance = config.novaclient().servers.create(
                                  config.instance_name,
                                  config.image_id,
                                  config.flavor_id,
                                  security_groups=config.security_groups,
                                  key_name=config.key_name,
                                  availability_zone=config.availability_zone,
                                  userdata=userdata)
        return instance
