"""
The generic cloud connection interface.
"""

import logging
import traceback

from reactor import utils
from reactor.config import SubConfig

def get_connection(cloud_type, config):
    if cloud_type == 'none':
        return CloudConnection(config)

    cloud_config = CloudConnectionConfig(config)
    cloud_class = cloud_config.cloud_class()
    if cloud_class == '':
        cloud_class = "reactor.cloud.%s.Connection" % (cloud_type)

    try:
        cloud_conn_class = utils.import_class(cloud_class)
        return cloud_conn_class(config)
    except:
        logging.error("Unable to load cloud: %s" % traceback.format_exc())
        return CloudConnection(config)

class CloudConnectionConfig(SubConfig):

    def cloud_class(self):
        return self._get("class", '')

class CloudConnection(object):

    def __init__(self, config):
        pass

    def id(self, instance):
        """ Return a unique string identifier for this instance. """
        raise NotImplementedError()

    def name(self, instance):
        """ Return the user-given name for this instance. """
        raise NotImplementedError()

    def addresses(self, instance):
        """ Return the set of (string) addresses for this instance. """
        raise NotImplementedError()

    def list_instances(self):
        """
        Lists the instances related to a endpoint. Note that this list should be 
        returned in order of oldest instance to youngest.
        """
        return []

    def start_instance(self, params={}):
        """
        Starts a new instance in the cloud using the endpoint.
        """
        raise NotImplementedError()

    def delete_instance(self, instance_id):
        """
        Remove the instance from the cloud.
        """
        raise NotImplementedError()
