"""
The generic cloud connection interface. Essentially exposes common methods used
to interact with different clouds.
"""

def get_connection(cloud_type):

    if cloud_type == 'nova':
        import gridcentric.pancake.cloud.nova as nova_cloud
        return nova_cloud.NovaConnector()
    else:
        raise Exception("Unsupported cloud type: %s." %(cloud_type))

class CloudConnection(object):
    
    def connect(self, credentials):
        """
        Connects to the cloud using the provided credentials
        """
        pass
    
    def list_instances(self, service_identifier):
        """
        Lists the instances related to a service. The identifier is used to 
        identify the related instances in the respective clouds. Note that
        this list should be returned in order of oldest instance to youngest.
        """
        return []
    
    def start_instance(self, service_identifier, instance_info):
        """
        Starts a new instance in the cloud using the service
        """
        pass
    
    def delete_instance(self, instance_id):
        """
        Remove the instance from the cloud
        """
        pass
