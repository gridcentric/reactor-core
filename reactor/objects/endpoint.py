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

from uuid import uuid4

from reactor.zookeeper.objects import JSONObject
from reactor.zookeeper.objects import BinObject
from reactor.zookeeper.objects import RawObject
from reactor.zookeeper.objects import DatalessObject
from reactor.zookeeper.objects import attr

from . ip_address import IPAddresses
from . instance import Instances
from . session import Sessions
from . config import ConfigObject
from . ring import Ring

# The endpoint names.
NAMES = "names"

# The endpoint data.
DATA = "data"

# The action for an endpoint.
STATE = "state"

# The manager for this endpoint.
MANAGER = "manager"

# Binary log data for this endpoint.
LOG = "log"

# The custom metrics for a particular host.
IP_METRICS = "ip_metrics"

# The global custom metrics for a endpoint (posted by the API).
CUSTOM_METRICS = "custom_metrics"

# The updated metrics for a particular endpoint (posted by the manager).
LIVE_METRICS = "live_metrics"

# The updated connections for a particular endpoint (posted by the manager).
LIVE_ACTIVE = "live_active"

# The ips that have been confirmed by the system for a particular endpoint.
CONFIRMED_IPS = "confirmed_ips"

# The associated instances.
INSTANCES = "instances"

# The marked instances.
MARKED_INSTANCES = "marked_ip"

# The decommissioned instances.
DECOMMISSIONED_INSTANCES = "decommissioned"

# The errored instances.
ERRORED_INSTANCES = "errored"

# The current sessions.
SESSIONS = "sessions"

class EndpointNotFound(Exception):
    pass

class Endpoints(DatalessObject):

    def get(self, name):
        # Get the endpoint UUID from the names directory.
        uuid = self._get_child(NAMES)._get_child(
            name, clazz=RawObject)._get_data()
        if uuid:
            return self._get_child(DATA)._get_child(
                uuid, clazz=Endpoint)
        else:
            raise EndpointNotFound(name)

    def list(self, **kwargs):
        # List the endpoints as names.
        return self._get_child(NAMES)._list_children(**kwargs)

    def manage(self, name, config):
        # Generate a UUID if one doesn't exist.
        uuid = str(uuid4())
        self._get_child(NAMES)._get_child(
            name, clazz=RawObject)._set_data(uuid, exclusive=True)

        # Set the configuration for this endpoint.
        self.get(name).set_config(config)

    def unmanage(self, name):
        # Delete the given endpoint.
        self._get_child(NAMES)._get_child(name)._delete()

    def clean(self):
        uuids = self._get_child(DATA)._list_children()
        names = self._get_child(NAMES)._list_children()

        # Get all the available endpoints.
        active_uuids = map(lambda x:
            self._get_child(NAMES)._get_child(x, clazz=RawObject)._get_data(),
            names)

        # Ensure there are no unused endpoints.
        for uuid in uuids:
            if not uuid in active_uuids:
                self._get_child(DATA)._get_child(uuid)._delete()

    def alias(self, name, new_name):
        # Get the current endpoint UUID.
        uuid = self._get_child(NAMES)._get_child(
            name, clazz=RawObject)._get_data()

        if uuid is not None:
            self._get_child(NAMES)._get_child(
                new_name, clazz=RawObject)._set_data(uuid)
            return True
        else:
            return False

    def state_counts(self):
        result = {}
        for name in self.list():
            state = self.get(name).state().current()
            if not state in result:
                result[state] = 1
            else:
                result[state] += 1
        return result

class State(RawObject):

    running = "RUNNING"
    stopped = "STOPPED"
    paused = "PAUSED"
    default = paused

    @staticmethod
    def from_action(current, action):
        if action.upper() == "START":
            return State.running
        elif action.upper() == "STOP":
            return State.stopped
        elif action.upper() == "PAUSE":
            return State.paused
        else:
            return current

    def current(self, watch=None):
        return self._get_data(watch=watch) or self.default

    def action(self, action):
        new_state = State.from_action(self.current(), action)
        self._set_data(new_state)
        return new_state

class Endpoint(ConfigObject):

    manager = attr(MANAGER, clazz=RawObject, ephemeral=True)
    metrics = attr(LIVE_METRICS, clazz=JSONObject, ephemeral=True)
    active = attr(LIVE_ACTIVE, clazz=JSONObject, ephemeral=True)
    custom_metrics = attr(CUSTOM_METRICS, clazz=JSONObject)

    def __init__(self, *args, **kwargs):
        super(Endpoint, self).__init__(*args, **kwargs)
        self._state = self._get_child(STATE, clazz=State)

    def unwatch(self):
        self._state.unwatch()
        super(Endpoint, self).unwatch()

    def get_config(self, **kwargs):
        return self._get_data(**kwargs)

    def set_config(self, config):
        return self._set_data(config)

    def log(self):
        return self._get_child(LOG, clazz=Ring)

    def state(self):
        return self._state

    def ip_metrics(self):
        return self._get_child(IP_METRICS, clazz=IPAddresses)

    def confirmed_ips(self):
        return self._get_child(CONFIRMED_IPS, clazz=IPAddresses)

    def instances(self):
        return self._get_child(INSTANCES, clazz=Instances)

    def decommissioned_instances(self):
        return self._get_child(DECOMMISSIONED_INSTANCES, clazz=Instances)

    def errored_instances(self):
        return self._get_child(ERRORED_INSTANCES, clazz=Instances)

    def marked_instances(self):
        return self._get_child(MARKED_INSTANCES, clazz=Instances)

    def sessions(self):
        return self._get_child(SESSIONS, clazz=Sessions)
