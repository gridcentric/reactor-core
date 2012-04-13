
import logging
from httplib import HTTPException

from gridcentric.nova.client.client import NovaClient

import gridcentric.pancake.cloud.connection as cloud_connection


class NovaConnector(cloud_connection.CloudConnection):
    
    def __init__(self):
        self.credentials = None
        self.deleted_instance_ids = []
    
    def connect(self, credentials):
        """
        Connects to the cloud using the provided credentials
        """
        self.credentials = credentials
    
    def _novaclient(self):
        try:
            (auth_url, user, apikey, project) = self.credentials
            novaclient = NovaClient(auth_url,
                                         user,
                                         apikey,
                                         project,
                                         'v1.1')
            return novaclient
        except Exception, e:
            traceback.print_exc()
            logging.error("Error creating nova client: %s" % str(e))

    
    def list_instances(self, service_identifier):
        """
        Lists the instances related to a service. The identifier is used to 
        identify the related instances in the respective clouds.
        """
        instances = self._novaclient().list_launched_instances(service_identifier)
        non_deleted_instances = []
        instance_ids_still_deleting = []
        for instance in instances:
            if instance['id'] not in self.deleted_instance_ids:
                non_deleted_instances.append(instance)
            else:
                instance_ids_still_deleting.append(instance['id'])
        
        self.deleted_instance_ids = instance_ids_still_deleting
        return sorted(non_deleted_instances, key=lambda x: x.get('created',"")) 
    
    def start_instance(self, service_identifier, instance_info):
        """
        Starts a new instance in the cloud using the service
        """
        try: 
            instance_id = instance_info
            self._novaclient().launch_instance(instance_id)
        except HTTPException, e:
            traceback.print_exc()
            logging.error("Error launching instance: %s" % str(e))
    
    
    def delete_instance(self, instance_id):
        """
        Remove the instance from the cloud
        """
        try:
            self._mark_instance_deleted(instance_id)
            self._novaclient().delete_instance(instance_id)
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
