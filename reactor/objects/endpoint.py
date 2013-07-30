from reactor.zookeeper.objects import JSONObject
from reactor.zookeeper.objects import BinObject
from reactor.zookeeper.objects import RawObject
from reactor.zookeeper.objects import DatalessObject
from reactor.zookeeper.objects import attr

from . ip_address import IPAddresses
from . instance import Instances
from . session import Sessions
from . config import ConfigObject

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

# The current sessions.
SESSIONS = "sessions"

class Endpoints(DatalessObject):

    def get(self, name):
        return self._get_child(name, clazz=Endpoint)

    def list(self, **kwargs):
        return self._list_children(**kwargs)

    def unmanage(self, name):
        self._get_child(name)._delete()

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

class Log(BinObject):

    def store(self, data):
        self._set_data(data)

    def retrieve(self):
        return self._get_data()

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
        return self._get_child(LOG, clazz=Log)

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

    def marked_instances(self):
        return self._get_child(MARKED_INSTANCES, clazz=Instances)

    def sessions(self):
        return self._get_child(SESSIONS, clazz=Sessions)
