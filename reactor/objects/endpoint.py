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

import os
from uuid import uuid4

from reactor.zookeeper.objects import JSONObject
from reactor.zookeeper.objects import RawObject
from reactor.zookeeper.objects import DatalessObject
from reactor.zookeeper.objects import attr

from . ip_address import IPAddresses
from . instance import Instances
from . metadata import Metadata
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

# User-metadata for the endpoint.
METADATA = "metadata"

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

class EndpointExists(Exception):
    pass

class Endpoints(DatalessObject):

    def __init__(self, *args, **kwargs):
        super(Endpoints, self).__init__(*args, **kwargs)
        self._names = self._get_child(NAMES, clazz=RawObject)
        self._data = self._get_child(DATA, clazz=Endpoint)

    def get(self, name):
        # Get the endpoint object & UUID from the directory.
        uuid = self._names._get_child(name)._get_data()
        if uuid:
            return (self._data._get_child(uuid), uuid)
        else:
            raise EndpointNotFound(name)

    def get_names(self, uuid):
        # Do a reverse lookup to find the name.
        # NOTE: This isn't efficient in the slighest. The user
        # of this interface should use aggressive caching to ensure
        # that this isn't called frequently or in the hot path.
        # (Particularly if you're managing hundreds of thousands
        # of endpoints, this can be a pretty slow operation).
        return [
            name for (name, endpoint_uuid) in
            map(lambda x:
                (x, self._names._get_child(x)._get_data()),
                self._names._list_children())
            if endpoint_uuid == uuid
        ]

    def list(self, **kwargs):
        # List the endpoints as names.
        return self._names._list_children(**kwargs)

    def create(self, name, config):
        # Generate a UUID if one doesn't exist.
        uuid = str(uuid4())
        if not self._names._get_child(name)._set_data(uuid, exclusive=True):
            raise EndpointExists(name)

        # Save the new configuration.
        endpoint = self._data._get_child(uuid)
        endpoint.set_config(config)

    def update(self, name, config):
        # Update the configuration for this endpoint.
        # NOTE: This will throw an error per get() above.
        endpoint, _ = self.get(name)
        endpoint.set_config(config)

    def remove(self, name):
        # Delete the given endpoint.
        self._names._get_child(name)._delete()

    def clean(self):
        uuids = self._data._list_children()
        names = self._names._list_children()

        # Get all the available endpoints.
        active_uuids = map(lambda x:
            self._names._get_child(x)._get_data(),
            names)

        # Ensure there are no unused endpoints.
        for uuid in uuids:
            if not uuid in active_uuids:
                self._data._get_child(uuid)._delete()

    def alias(self, name, new_name):
        # Get the current endpoint UUID.
        uuid = self._names._get_child(name)._get_data()

        if uuid is not None:
            self._names._get_child(new_name)._set_data(uuid, exclusive=True)
            return True
        else:
            return False

    def state_counts(self):
        result = {}
        for name in self.list():
            endpoint, _ = self.get(name)
            state = endpoint.state().current()
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

    def uuid(self):
        return os.path.basename(self._path)

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

    def instance_map(self):
        return {
            "active": self.instances().list(),
            "decommissioned": self.decommissioned_instances().list(),
            "errored": self.errored_instances().list(),
        }

    def associate(self, instance_id):
        if instance_id in self.instances().list():
            # Already an active instance?
            return
        if instance_id in self.decommissioned_instances().list():
            # Already decomissioned?
            return
        if instance_id in self.errored_instances().list():
            # Already errored?
            return

        # Add the instance (no value).
        self.instances().add(instance_id)

    def disassociate(self, instance_id):
        # Remove from all collections.
        self.instances().remove(instance_id)
        self.decommissioned_instances().remove(instance_id)
        self.errored_instances().remove(instance_id)

    def instances(self):
        return self._get_child(INSTANCES, clazz=Instances)

    def metadata(self):
        return self._get_child(METADATA, clazz=Metadata)

    def decommissioned_instances(self):
        return self._get_child(DECOMMISSIONED_INSTANCES, clazz=Instances)

    def errored_instances(self):
        return self._get_child(ERRORED_INSTANCES, clazz=Instances)

    def marked_instances(self):
        return self._get_child(MARKED_INSTANCES, clazz=Instances)

    def sessions(self):
        return self._get_child(SESSIONS, clazz=Sessions)
