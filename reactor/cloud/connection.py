# Copyright 2013 GridCentric Inc.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

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
    cloud_class = "reactor.cloud.%s.connection.Connection" % name
    cloud_conn_class = utils.import_class(cloud_class)
    return cloud_conn_class(name, **kwargs)

class CloudConnection(Connection):

    """ No cloud """

    def __init__(self,
        name,
        zkobj=None,
        config=None,
        this_ip=None,
        this_url=None,
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
