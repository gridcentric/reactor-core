"""
The generic cloud connection interface.
"""

from reactor import utils
from reactor.config import SubConfig

def get_connection(cloud_type, config):
    if cloud_type == 'none':
        return CloudConnection(config)

    cloud_config = CloudConnectionConfig(config)
    cloud_class = cloud_config.cloud_class()
    if cloud_class == '':
        cloud_class = "reactor.cloud.%s.Connection" % (cloud_type)
    cloud_conn_class = utils.import_class(cloud_class)
    return cloud_conn_class(config)

class CloudConnectionConfig(SubConfig):

    def cloud_class(self):
        return self._get("class", '')

class CloudConnection(object):

    def __init__(self, config):
        pass

    def list_instances(self):
        """
        Lists the instances related to a endpoint. Note that this list should be 
        returned in order of oldest instance to youngest.
        """
        return []

    def start_instance(self, params={}):
        """
        Starts a new instance in the cloud using the endpoint
        """
        pass

    def delete_instance(self, instance_id):
        """
        Remove the instance from the cloud
        """
        pass
