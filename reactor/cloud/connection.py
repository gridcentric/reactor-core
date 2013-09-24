"""
The generic cloud connection interface.
"""

import logging
import traceback

from reactor import utils
from reactor.config import Connection

def get_connection(name, **kwargs):
    if not name:
        return CloudConnection(name, **kwargs)

    try:
        cloud_class = "reactor.cloud.%s.connection.Connection" % name
        cloud_conn_class = utils.import_class(cloud_class)
        return cloud_conn_class(name, **kwargs)
    except Exception:
        logging.error("Unable to load cloud: %s", traceback.format_exc())
        return CloudConnection(name, **kwargs)

class CloudConnection(Connection):

    """ No cloud """

    def __init__(self,
        name,
        zkobj=None,
        config=None,
        this_ip=None,
        register_ip=None,
        drop_ip=None):

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
        NOTE: Returns (instance_id, pre_confirmed_ips).
        """
        raise NotImplementedError()

    def delete_instance(self, config, instance_id):
        """
        Remove the instance from the cloud.
        """
        raise NotImplementedError()
