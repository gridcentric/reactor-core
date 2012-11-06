import logging
import traceback
from httplib import HTTPException

from novaclient import shell
from novaclient.v1_1.client import Client as NovaClient

from reactor.config import SubConfig
import reactor.cloud.connection as cloud_connection

class BaseNovaConnection(cloud_connection.CloudConnection):

    def __init__(self, config):
        super(BaseNovaConnection, self).__init__(config)
        self.deleted_instance_ids = []
        self.config = self.create_config(config)

    def create_config(self, config):
        return BaseNovaConfig(config)

    def _list_instances(self):
        """ 
        Returns a  list of instances from the endpoint. This is implemented by the
        subclasses
        """
        return []

    def _novaclient(self):
        try:
            extensions = shell.OpenStackComputeShell()._discover_extensions("1.1")
            novaclient = NovaClient(self.config.user(),
                                    self.config.apikey(),
                                    self.config.project(),
                                    self.config.authurl(),
                                    region_name=self.config.region(),
                                    service_type=self.config.service_type(),
                                    extensions=extensions)
            return novaclient
        except Exception, e:
            traceback.print_exc()
            logging.error("Error creating nova client: %s" % str(e))

    def list_instances(self):
        """
        Lists the instances related to a endpoint. The identifier is used to 
        identify the related instances in the respective clouds.
        """
        # Pull out the _info dictionary from the Server object
        instances = [instance._info for instance in self._list_instances()]
        non_deleted_instances = []
        instance_ids_still_deleting = []
        for instance in instances:
            if str(instance['id']) not in self.deleted_instance_ids:
                non_deleted_instances.append(instance)
            else:
                instance_ids_still_deleting.append(str(instance['id']))

        self.deleted_instance_ids = instance_ids_still_deleting
        return sorted(non_deleted_instances, key=lambda x: x.get('created', ""))

    def _start_instance(self, params={}):
        """
        Starts a new instance. This is implemented by the subclasses.
        """
        pass

    def start_instance(self, params={}):
        """
        Starts a new instance in the cloud using the endpoint
        """
        try:
            self._start_instance(params=params)
        except HTTPException, e:
            traceback.print_exc()
            logging.error("Error starting instance: %s" % str(e))

    def _delete_instance(self, instance_id):
        self._novaclient().servers._delete("/servers/%s" % (instance_id))

    def delete_instance(self, instance_id):
        """
        Remove the instance from the cloud
        """
        try:
            self._mark_instance_deleted(instance_id)
            self._delete_instance(instance_id)
        except HTTPException, e:
            traceback.print_exc()
            logging.error("Error deleting instance: %s" % str(e))
            self._unmark_instance_deleted(instance)

    def _mark_instance_deleted(self, instance_id):
        self.deleted_instance_ids.append(instance_id)

    def _unmark_instance_deleted(self, instance):
        try:
            self.deleted_instance_ids.remove(instance_id)
        except:
            # It is alright if this throws an exception because in the end
            # we just want that id to not be in the deleted_instance_ids list.
            pass

class BaseNovaConfig(cloud_connection.CloudConnectionConfig):

    def user(self):
        return self._get("user", "admin")

    def apikey(self):
        return self._get("apikey", "admin")

    def project(self):
        return self._get("project", "admin")

    def authurl(self):
        return self._get("authurl", "http://localhost:8774/v1.1/")

    def region(self):
        region = self._get("region", '')
        if region == '':
            region = None
        return region

    def service_type(self):
        return self._get('service_type', 'compute')

class NovaConfig(BaseNovaConfig):

    def instance_name(self):
        return self._get("instance_name", "name")

    def flavor(self):
        return self._get("flavor_id", "1")

    def image(self):
        return self._get("image_id", "0")

    def security_groups(self):
        return self._get("security_groups", "").split(",")

    def key_name(self):
        return self._get("key_name", "") or None

class Connection(BaseNovaConnection):

    def __init__(self, config):
        super(Connection, self).__init__(config)

    def create_config(self, config):
        return NovaConfig(config)

    def _list_instances(self):
        """ 
        Returns a  list of instances from the endpoint.
        """
        search_opts = {
            'name':   self.config.instance_name(),
            'flavor': self.config.flavor(),
            'image':  self.config.image()
        }

        instances = self._novaclient().servers.list(search_opts=search_opts)
        return instances

    def _start_instance(self, params={}):
        # TODO: We can pass in the reactor parameter here via 
        # CloudStart or some other standard support mechanism.
        userdata = "reactor=%s" % params.get('reactor', '')
        self._novaclient().servers.create(self.config.instance_name(),
                                  self.config.image(),
                                  self.config.flavor(),
                                  security_groups=self.config.security_groups(),
                                  key_name=self.config.key_name(),
                                  userdata=userdata)
