import logging
import traceback
from httplib import HTTPException

from gridcentric.pancake.cloud.nova.client.client import NovaClient as GridcentricNovaClient
from novaclient.v1_1.client import Client as NovaClient

import gridcentric.pancake.cloud.connection as cloud_connection

class BaseNovaConnector(cloud_connection.CloudConnection):

    def __init__(self, cloud_config):
        super(BaseNovaConnector, self).__init__(cloud_config)
        self.deleted_instance_ids = []

    def _list_instances(self):
        """ 
        Returns a  list of instances from the service. This is implemented by the
        subclasses
        """
        return []

    def list_instances(self):
        """
        Lists the instances related to a service. The identifier is used to 
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
        Starts a new instance in the cloud using the service
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

class NovaConnector(BaseNovaConnector):

    def __init__(self, cloud_config):
        super(NovaConnector, self).__init__(cloud_config)

    def _novaclient(self):
        try:
            novaclient = NovaClient(self.config['user'],
                                    self.config['apikey'],
                                    self.config['project'],
                                    self.config['authurl'])
            return novaclient.servers
        except Exception, e:
            traceback.print_exc()
            logging.error("Error creating nova client: %s" % str(e))

    def _list_instances(self):
        """ 
        Returns a  list of instances from the service.
        """
        search_opts = {'name': self.config['instance_name'],
                       'flavor': self.config['flavor_id'],
                       'image': self.config['image_id']}

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
        self._novaclient().create(self.config['instance_name'],
                                  self.config['image_id'],
                                  self.config['flavor_id'],
                                  security_groups=self.config['security_groups'].split(","),
                                  key_name=self.config['key_name'] or None)

    def _delete_instance(self, instance_id):
        self._novaclient()._delete("/servers/%s" % (instance_id))


class NovaVmsConnector(BaseNovaConnector):
    """ Connects to a nova cloud that has the Gridcentric VMS extension enabled. """

    def __init__(self, cloud_config):
        super(NovaVmsConnector, self).__init__(cloud_config)

    def _novaclient(self):
        try:
            novaclient = GridcentricNovaClient(self.config['authurl'],
                                    self.config['user'],
                                    self.config['apikey'],
                                    self.config['project'],
                                    'v1.1')
            return novaclient
        except Exception, e:
            traceback.print_exc()
            logging.error("Error creating nova client: %s" % str(e))

    def _list_instances(self):
        """ 
        Returns a  list of instances from the service.
        """
        return self._novaclient().list_launched_instances(self.config['instance_id'])

    def _start_instance(self, params={}):
        launch_params = { 'target' : self.config['target'], 'guest' : params }
        self._novaclient().launch_instance(self.config['instance_id'], params=launch_params)

    def _delete_instance(self, instance_id):
        self._novaclient().delete_instance(instance_id)
