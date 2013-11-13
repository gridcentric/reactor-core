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

from reactor.atomic import Atomic
from reactor.zookeeper.objects import DatalessObject
from reactor.zookeeper.objects import JSONObject

from . config import ConfigObject
from . ring import Ring

# Manager configuration (by IP).
CONFIGS = "configs"

# Live manager information (keys, loadbalancers, etc.).
KEYS = "keys"

# The metrics for a particular manager.
METRICS = "metrics"

# The pending connections for a particular manager.
PENDING = "pending"

# The total active connections for a particular manager.
ACTIVE = "active"

# The manager logs.
LOGS = "logs"

class Managers(DatalessObject, Atomic):

    def __init__(self, *args, **kwargs):
        super(Managers, self).__init__(*args, **kwargs)
        self._info = self._get_child(KEYS, clazz=JSONObject)
        self._configured = self._get_child(CONFIGS, clazz=JSONObject)

    def list_configs(self, **kwargs):
        # List available configured managers.
        return self._configured._list_children(**kwargs)

    def list_active(self, **kwargs):
        # List running managers.
        return self._info._list_children(**kwargs)

    def get_config(self, name, **kwargs):
        # Return configuration data.
        return self._configured._get_child(name)._get_data(**kwargs)

    def set_config(self, name, config):
        # Set configuration data.
        self._configured._get_child(name, clazz=ConfigObject)._set_data(config)

    def remove_config(self, name):
        # Clear configuration data.
        self._configured._get_child(name)._delete()

    def log(self, name):
        # Get the associated log object.
        return self._get_child(LOGS)._get_child(name, clazz=Ring)

    def set_metrics(self, uuid, value):
        return self._get_child(METRICS)._get_child(
                uuid, clazz=JSONObject)._set_data(value, ephemeral=True)

    def set_pending(self, uuid, value):
        return self._get_child(PENDING)._get_child(
                uuid, clazz=JSONObject)._set_data(value, ephemeral=True)

    def set_active(self, uuid, value):
        return self._get_child(ACTIVE)._get_child(
                uuid, clazz=JSONObject)._set_data(value, ephemeral=True)

    def register(self, uuid, info):
        """
        This method is called by the manager internally.
        It is used to register the given UUID as an active manager.
        """
        self._info._get_child(uuid)._set_data(info, ephemeral=True)

        return self._info._get_child(uuid)._get_data()

    def unregister(self, uuid):
        """
        Remove the given uuid from the list of keys.
        This will be called when the manager is not longer serving
        in a capacity as a scale manager (i.e. is shutting down).
        """
        self._info._get_child(uuid)._delete()

    def info(self, uuid):
        return self._info._get_child(uuid)._get_data()

    def info_map(self):
        """
        This returns a tuple of manager information passed at registration.
        Currently, this includes (keys, loadbalancers, clouds).
        """
        # This is a utility function used by the manager. It shouldn't be used
        # frequently, but can be called when the manager set changes and you
        # need to reload and recompute the ring.
        return dict(map(
            lambda x: (x, self.info(x)),
            self.list_active()))

    def metrics_map(self):
        # This function will be called more frequently than info_map() above,
        # but there's not much that can be done to minimize this cost (it's
        # necessary for information sharing across managers).
        return dict(map(
            lambda x: (x, self._get_child(
                METRICS, clazz=JSONObject)._get_child(x)._get_data()),
            self._get_child(
                METRICS, clazz=JSONObject)._list_children()))

    def pending_map(self):
        # Same as metric_map().
        return dict(map(
            lambda x: (x, self._get_child(
                PENDING, clazz=JSONObject)._get_child(x)._get_data()),
            self._get_child(
                PENDING, clazz=JSONObject)._list_children()))

    def active_count(self):
        # Sums across all active managers to return
        # the total active connections for the system.
        # This is not really practically useful, other
        # than for a big global metric for the entire
        # system (which is exactly what it is used for).
        return sum(map(
            lambda x: self._get_child(
                ACTIVE, clazz=JSONObject)._get_child(x)._get_data() or 0,
            self._get_child(
                ACTIVE, clazz=JSONObject)._list_children()))
