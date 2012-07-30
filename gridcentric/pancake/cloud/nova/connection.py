import logging
import traceback
from httplib import HTTPException

from novaclient.v1_1.client import Client as NovaClient

from gridcentric.pancake.config import SubConfig
import gridcentric.pancake.cloud.connection as cloud_connection
from gridcentric.pancake.cloud.nova.client.client import NovaClient as GridcentricNovaClient

class BaseNovaConnector(cloud_connection.CloudConnection):

    def __init__(self, config):
        super(BaseNovaConnector, self).__init__()
        self.deleted_instance_ids = []
        self.config = config

    def _list_instances(self):
        """ 
        Returns a  list of instances from the endpoint. This is implemented by the
        subclasses
        """
        return []

    def list_instances(self):
        """
        Lists the instances related to a endpoint. The identifier is used to 
        identify the related instances in the respective clouds.
        """
        instances = self._list_instances()
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
        pass

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

class BaseNovaConfig(SubConfig):

    def user(self):
        return self._get("user", "admin")

    def apikey(self):
        return self._get("apikey", "admin")

    def project(self):
        return self._get("apikey", "admin")

    def authurl(self):
        return self._get("authurl", "http://localhost:8774/v1.1/")

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

class NovaConnector(BaseNovaConnector):

    def __init__(self, config):
        super(NovaConnector, self).__init__(config)

    def _novaclient(self):
        try:
            novaclient = NovaClient(self.config.user(),
                                    self.config.apikey(),
                                    self.config.project(),
                                    self.config.authurl())
            return novaclient.servers
        except Exception, e:
            traceback.print_exc()
            logging.error("Error creating nova client: %s" % str(e))

    def _list_instances(self):
        """ 
        Returns a  list of instances from the endpoint.
        """
        search_opts = {
            'name':   self.config.instance_name(),
            'flavor': self.config.flavor(),
            'image':  self.config.image()
        }

        instances = self._novaclient().list(search_opts=search_opts)

        # The novaclient essentially wraps it instances in a server resource object.
        # We need to get at the raw object and return that.
        raw_instances = []
        for instance in instances:
            raw_instances.append(instance._info)

        return raw_instances

    def _start_instance(self, params={}):
        # TODO: We can pass in the pancake parameter here via 
        # CloudStart or some other standard support mechanism.
        self._novaclient().create(self.config.instance_name(),
                                  self.config.image(),
                                  self.config.flavor(),
                                  security_groups=self.config.security_groups(),
                                  key_name=self.config.key_name())

    def _delete_instance(self, instance_id):
        self._novaclient()._delete("/servers/%s" % (instance_id))

class NovaVmsConfig(BaseNovaConfig):

    def instance_id(self):
        return self._get("instance_id", "0")

    def target(self):
        return self._get("target", "0")

class NovaVmsConnector(BaseNovaConnector):
    """ Connects to a nova cloud that has the Gridcentric VMS extension enabled. """

    def __init__(self, config):
        super(NovaVmsConnector, self).__init__(config)

    def _novaclient(self):
        try:
            novaclient = GridcentricNovaClient(self.config.authurl(),
                                               self.config.user(),
                                               self.config.apikey(),
                                               self.config.project(),
                                               'v1.1')
            return novaclient
        except Exception, e:
            traceback.print_exc()
            logging.error("Error creating nova client: %s" % str(e))

    def _list_instances(self):
        """ 
        Returns a list of instances from the endpoint.
        """
        return self._novaclient().list_launched_instances(self.config.instance_id())

    def _start_instance(self, params={}):
        launch_params = { 'target' : self.config.target(), 'guest' : params }
        self._novaclient().launch_instance(self.config.instance_id(), params=launch_params)

    def _delete_instance(self, instance_id):
        self._novaclient().delete_instance(instance_id)
