"""
The generic cloud connection interface.
"""

def get_connection(cloud_type, cloud_config):
    if cloud_type == 'nova-vms':
        import gridcentric.pancake.cloud.nova as nova_cloud
        return nova_cloud.NovaVmsConnector(cloud_config)

    elif cloud_type == 'nova':
        import gridcentric.pancake.cloud.nova as nova_cloud
        return nova_cloud.NovaConnector(cloud_config)

    elif cloud_type == 'none':
        return CloudConnection({})

    else:
        raise Exception("Unsupported cloud type: %s." % (cloud_type))

class CloudConnection(object):

    def __init__(self, cloud_config):
        self.config = cloud_config

    def list_instances(self):
        """
        Lists the instances related to a service. Note that this list should be 
        returned in order of oldest instance to youngest.
        """
        return []

    def start_instance(self):
        """
        Starts a new instance in the cloud using the service
        """
        pass

    def delete_instance(self, instance_id):
        """
        Remove the instance from the cloud
        """
        pass
