"""
The generic cloud connection interface.
"""

import logging
import traceback

from reactor import utils
from reactor.config import Connection

def get_connection(name, config=None):
    if not name:
        return CloudConnection(name, config)

    try:
        cloud_class = "reactor.cloud.%s.connection.Connection" % name
        cloud_conn_class = utils.import_class(cloud_class)
        return cloud_conn_class(name, config)
    except Exception:
        logging.error("Unable to load cloud: %s", traceback.format_exc())
        return CloudConnection(name, config)

class CloudConnection(Connection):

    """ No cloud """

    def __init__(self, name, config=None):
        super(CloudConnection, self).__init__(
            object_class="cloud", name=name, config=config)

    def list_instances(self, config, instance_id=None):
        """
        Lists the instances related to a endpoint. Note that this list should be
        returned in order of oldest instance to youngest.
        """
        return []

    def start_instance(self, config, params=None):
        """
        Starts a new instance in the cloud using the endpoint.
        """
        raise NotImplementedError()

    def delete_instance(self, config, instance_id):
        """
        Remove the instance from the cloud.
        """
        raise NotImplementedError()
