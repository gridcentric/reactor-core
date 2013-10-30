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

import logging
import time

import email
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from StringIO import StringIO

from novaclient import shell
from novaclient.v1_1.client import Client as NovaClient
import novaclient.exceptions

from reactor.config import Config
from reactor.cloud.connection import CloudConnection
from reactor.cloud.instance import Instance
from reactor.cloud.instance import STATUS_OKAY, STATUS_ERROR

STATUS_MAP = {
    "ACTIVE": STATUS_OKAY,
    "BUILD": STATUS_OKAY,
    "ERROR": STATUS_ERROR,
}

REACTOR_SCRIPT = """#!/bin/sh
if which curl; then
    CMD="curl -X POST %(url)s"
elif which wget; then
    CMD="wget --post-data='' %(url)s"
fi
ATTEMPTS=0
while ! $CMD && [ "$ATTEMPTS" -lt %(timeout)s ]; do
    sleep 1
    ATTEMPTS=$(($ATTEMPTS+1))
done
"""

MIME_TYPES = [
    ("#!", "x-shellscript"),
    ("#include-once\n", "x-include-once-url"),
    ("#include\n", "x-include-url"),
    ("#cloud-config-archive\n", "cloud-config-archive"),
    ("#upstart-job\n", "upstart-job"),
    ("#cloud-config\n", "cloud-config"),
    ("#part-handler\n", "part-handler"),
    ("#cloud-boothook\n", "cloud-boothook"),
]

def mime_type(data):
    for (header, mime) in MIME_TYPES:
        if data.startswith(header):
            return mime
    return "plain"

class BaseOsEndpointConfig(Config):

    # Cached client.
    _client = None

    def __init__(self, *args, **kwargs):
        super(BaseOsEndpointConfig, self).__init__(*args, **kwargs)

        # Initialize our list cache.
        self._list_cache = []
        self._last_refresh = None

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

    user_data = Config.text("User Data",
        order=6, description="Script or cloud-config for new instances.")

    filter_instances = Config.boolean("Filter Instances",
        default=False, order=7,
        description="Use only instances that match image, flavor, etc.")

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

    _ENDPOINT_CONFIG_CLASS = BaseOsEndpointConfig

    def __init__(self, *args, **kwargs):
        super(BaseOsConnection, self).__init__(*args, **kwargs)
        self._this_url = kwargs.get("this_url")

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
        config = self._endpoint_config(config)
        list_rate_limit = config.list_rate_limit

        if instance_id is not None:
            instances = self._list_instances(config, instance_id)

        elif config._last_refresh is not None and \
            (config._last_refresh + list_rate_limit) > time.time():
            instances = config._list_cache

        else:
            instances = self._list_instances(config, None)
            config._list_cache = instances
            config._last_refresh = time.time()

        instances = sorted(instances, key=lambda x: x._info.get("created", ""))

        def _sanitize(instance):
            # Extract the instance id.
            if hasattr(instance, 'id'):
                instance_id = instance.id
            else:
                instance_id = instance._info['id']

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

            # Extract a status.
            status = STATUS_MAP.get(instance._info.get('status'), STATUS_ERROR)

            return Instance(instance_id, name, addresses, status)

        # Return all sanitizing instances.
        return map(_sanitize, instances)

    def _user_data(self, user_data=None):
        reactor_script = REACTOR_SCRIPT % {
            "url": self._this_url,
            "timeout": 300,
        }

        if user_data:
            # If the user has provided user-data,
            # then we need to do a multi-part encoding
            # of the data. We provide the reactor script
            # as the second piece, to ensure they've gone
            # through the necessary setup prior to having
            # the instance registered.
            msg = MIMEMultipart()
            orig_msg = email.message_from_file(StringIO(user_data))

            for part in orig_msg.walk():
                # multipart/* are just containers.
                if part.get_content_maintype() == 'multipart':
                    continue

                if part.get_content_type() == "text/plain":
                    # We try to re-encode text/plain types as
                    # something else, more sane. This handles
                    # the plain shell script passed in.
                    msg.attach(MIMEText(
                        user_data, mime_type(part.get_payload(decode=True))))
                else:
                    msg.attach(part)

            # Attach the reactor script (final step).
            msg.attach(MIMEText(reactor_script, mime_type(reactor_script)))

            return msg.as_string()

        else:
            # Without a user script, we can just run
            # the reactor script directly. We don't need
            # to provide the multi-part encoding here.
            return reactor_script

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
        params.update({ "reactor": self._this_url } )

        # Reset the refresh so no matter what happens,
        # when we next call list() we will have an up
        # to date view of what's running on the cloud.
        config = self._endpoint_config(config)
        config._last_refresh = None

        # Finally, do the start.
        # NOTE: We don't catch any exceptions here,
        # they will be caught in the endpoint so that
        # they can be *logged*.
        return (self._start_instance(config, params=params), None)

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
        config = self._endpoint_config(config)
        config._last_refresh = None

    def reset_caches(self, config):
        # Just reset the refresh cache, so that the
        # next calls to list_instances will do a real
        # update and get the latest available data.
        config = self._endpoint_config(config)
        config._last_refresh = None

class OsApiEndpointConfig(BaseOsEndpointConfig):

    instance_name = Config.string(label="Instance Name", order=2,
        validate=lambda self: self.instance_name or \
            Config.error("Must provide an instance name."),
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

    # Enable specification of networks if the novaclient supports it.
    if "tenant_networks" in [ extension.name for extension in \
        shell.OpenStackComputeShell()._discover_extensions("1.1") ]:
        network_conf = Config.list(label="Network Configuration", default=[],
            order=2, validate=lambda self: self.validate_network_conf(),
            description="Network configuration for scaled instances. " +
            "This is identical to the --nic parameter in novaclient. " +
            "One network configuration per line.")

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

    def validate_network_conf(self):
        if self.validate_connection_params(False):
            # Parse netspecs into objects.
            try:
                networks = OsApiEndpointConfig.parse_netspecs(self.network_conf)
            except Exception as ex:
                Config.error("Failed to parse network conf: %s" % str(ex))

            known_networks = [nw._info["id"] for nw in self.novaclient().networks.list()]
            for network in networks:
                if (network["net-id"] is not None) and \
                        (network["net-id"] not in known_networks):
                    Config.error("Network '%s' not found" % network)
        else:
            # Can't connect to cloud, ignore this param for now
            return True

    @staticmethod
    def parse_netspecs(netspecs):
        parsed_specs = []
        for spec in netspecs:
            res = { "net-id": None,
                    "v4-fixed-ip": None,
                    "port-id": None }
            for keyval in spec.split(","):
                kv = keyval.split("=", 1)
                if len(kv) < 2:
                    raise ValueError("No value given for key '%s'" % str(kv[0]))
                key = kv[0]
                value = kv[1]

                if key not in res:
                    raise KeyError("'%s' is not a valid nic keyword" % str(key))
                res[key] = value
            parsed_specs.append(res)
        return parsed_specs

class Connection(BaseOsConnection):
    """ OpenStack """

    _ENDPOINT_CONFIG_CLASS = OsApiEndpointConfig

    def _list_instances(self, config, instance_id):
        """
        Returns a  list of instances from the endpoint.
        """
        config = self._endpoint_config(config)
        if instance_id is None:
            if config.filter_instances:
                search_opts = {
                    'name': config.instance_name,
                    'flavor': config.flavor_id,
                    'image': config.image_id
                }
            else:
                search_opts = None
            return config.novaclient().servers.list(search_opts=search_opts)
        else:
            try:
                return [config.novaclient().servers.get(instance_id)]
            except novaclient.exceptions.NotFound:
                return []

    def _start_instance(self, config, params):
        config = self._endpoint_config(config)
        instance_params = {
            "security_groups": config.security_groups,
            "key_name": config.key_name,
            "availability_zone": config.availability_zone,
            "userdata": self._user_data(config.user_data)
        }
        if hasattr(config, "network_conf"):
            instance_params["nics"] = \
                OsApiEndpointConfig.parse_netspecs(config.network_conf) or None

        return config.novaclient().servers.create(
            config.instance_name,
            config.image_id,
            config.flavor_id,
            **instance_params)
