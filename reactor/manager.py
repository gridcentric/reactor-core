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

import time
import bisect
import traceback
import logging
import uuid

from . import cli
from . import utils
from . import ips as ips_mod
from . import submodules
from . atomic import Atomic
from . atomic import AtomicRunnable
from . config import Config
from . eventlog import EventLog, Event
from . zookeeper.client import ZookeeperClient
from . zookeeper.connection import ZookeeperException
from . zookeeper.cache import Cache
from . objects.root import Reactor
from . objects.endpoint import EndpointNotFound
from . threadpool import Threadpool
from . endpoint import Endpoint
from . metrics.calculator import calculate_weighted_averages
from . loadbalancer import connection as lb_connection
from . cloud import connection as cloud_connection

class ManagerConfig(Config):

    def __init__(self, **kwargs):
        super(ManagerConfig, self).__init__("manager", **kwargs)

    loadbalancers = Config.multiselect(label="Enabled Loadbalancer Drivers", order=1,
        options=submodules.loadbalancer_options(),
        default=submodules.loadbalancer_submodules(include_all=True),
        description="List of supported loadbalancers (e.g. nginx).")

    clouds = Config.multiselect(label="Enabled Cloud Drivers", order=1,
        options=submodules.cloud_options(),
        default=submodules.cloud_submodules(include_all=True),
        description="List of supported clouds (e.g. osapi).")

    interval = Config.integer(label="Health Check Interval (seconds)",
        default=10, order=1,
        validate=lambda self: self.interval > 0 or \
            Config.error("Interval must be positive."),
        alternates=["health_check"],
        description="Period for decomissioning and timing out instances.")

    keys = Config.integer(label="Keys per Manager", default=64, order=2,
        validate=lambda self: self.keys >= 0 or \
            Config.error("Keys must be non-negative."),
        description="Key count for managing services on the ring.")

    def spec(self):
        for name in submodules.loadbalancer_submodules():
            lb_connection.get_connection(name, config=self)._manager_config()
        for name in submodules.cloud_submodules():
            cloud_connection.get_connection(name, config=self)._manager_config()
        return super(ManagerConfig, self).spec()

    def validate(self):
        errors = super(ManagerConfig, self).validate()
        for name in submodules.loadbalancer_submodules():
            errors.update(lb_connection.get_connection(
                name, config=self)._manager_config().validate())
        for name in submodules.cloud_submodules():
            errors.update(cloud_connection.get_connection(
                name, config=self)._manager_config().validate())
        return errors

class ManagerLog(EventLog):

    # The log size (# of entries).
    LOG_SIZE = 200

    # Log entry types.
    NO_MANAGER_AVAILABLE = Event(
        lambda args: "No manager avilable for endpoint %s!" % args[0])
    ENDPOINT_MANAGED = Event(
        lambda args: "Endpoint %s is managed (owned: %s)." % (args[0], args[1]))
    ENDPOINTS_CHANGED = Event(
        lambda args: "Endpoints have changed: %s" % args[0])
    MANAGERS_CHANGED = Event(
        lambda args: "Managers have changed: %s" % args[0])
    REGISTERED = Event(
        lambda args: "Manager registered.")
    MALFORMED_METRICS = Event(
        lambda args: "Found malformed metrics: %s" % args[0])
    LOCAL_METRICS = Event(
        lambda args: "Loaded local metrics: %s" % args[0])
    ALL_METRICS = Event(
        lambda args: "Loaded all metrics: %s" % args[0])
    LOCAL_PENDING = Event(
        lambda args: "Loaded local pending: %s" % args[0])
    ALL_PENDING = Event(
        lambda args: "Loaded all pending: %s" % args[0])
    SESSION_MULTIPLE_MATCH = Event(
        lambda args: "Multiple matches for session %s!" % args[0])
    SESSION_NO_MATCH = Event(
        lambda args: "No match for session %s!" % args[0])
    ENDPOINT_ERROR = Event(
        lambda args: "Error updating endpoint %s: %s" % (args[0], args[1]))
    ENDPOINT_SKIPPED = Event(
        lambda args: "Skipped endpoint %s." % args[0])
    ENDPOINT_UPDATED = Event(
        lambda args: "Updated endpoint %s." % args[0])

    def __init__(self, *args):
        super(ManagerLog, self).__init__(*args, size=ManagerLog.LOG_SIZE)

# IMPORTANT: There is a potential deadlock if the manager is locked when
# setting / clearing a zookeeper watch. Our policy is that the manager cannot
# be locked when it makes a call to one of the zookeeper client's watch
# functions. Note to check the full call chain to ensure that a higher level
# function is not setting the lock.

class ScaleManager(AtomicRunnable):

    def __init__(self, zk_servers, names=None):
        super(ScaleManager, self).__init__()

        # Our thread pool.
        # The threadpool is used to do endpoint updates.
        # This pool will scale automatically to accomodate as
        # many endpoints as we have. Unfortunately, each endpoint
        # will likely require add a thread to the size of the pool,
        # so that will only scale to a few hundred endpoints per
        # manager. At some point, we may have to revisit this and
        # see how we could improve scalability for endpoints.
        self._threadpool = Threadpool()

        # Manager uuid (generated).
        # This doesn't serve any particular purpose other than
        # giving us a unique node to register our information.
        # We save a collection of keys, loadbalancers, clouds, etc.
        self._uuid = str(uuid.uuid4())

        # Manager names.
        # Each manager has a collection of readable names.
        # Basically, this can be used to provide some kind
        # of sensible scheme for configuration, etc.
        # By default, these names are the available non-local
        # IP addresses found on the machine. The name used for
        # registration is the default() IP and should be at
        # least routeable.
        if names is None:
            self._names = ips_mod.find_global()
            self._ip = ips_mod.find_default()
        else:
            self._names = names
            self._ip = len(names) > 0 and names[0]
        if not self._names:
            raise Exception("Manager has no persistent names!")

        # Zookeeper objects.
        self.client = ZookeeperClient(zk_servers)
        self.zkobj = Reactor(self.client)

        # Grab the log.
        # We want the logs to be persistent, but we don't want to
        # store it under our UUID since it is generated each start.
        # The solution to this problem is that we store the logs
        # under the first name, and ensure that we expose our names
        # via the manager info block (see _register() below). This way,
        # clients can look up the right place for each manager.
        self.logging = ManagerLog(self.zkobj.managers().log(self._ip))

        # Ppersistent objects.
        self._url_zkobj = self.zkobj.url()
        self._managers_zkobj = self.zkobj.managers()
        self._endpoints_zkobj = self.zkobj.endpoints()
        self._new_ips_zkobj = self.zkobj.new_ips()
        self._drop_ips_zkobj = self.zkobj.drop_ips()
        self.endpoint_ips = Cache(self.zkobj.endpoint_ips())

        # Our configuration.
        self.config = ManagerConfig()

        # Endpoint maps.
        self._endpoint_names = {}
        self._endpoint_data = {}

        # The ring.
        # In order to minimize disruption and keep services
        # running smoothly, we maintain a ring and use a simple
        # consistent hashing scheme to figure out whether scale
        # manager is response for "owning" a service.

        self._keys = []         # Our local manager keys.
        self._key_to_uuid = {}  # Map of manager key -> uuid.
        self._uuid_to_info = {} # Map of manager uuid -> info.

        # Endpoint to ownership cache.
        self._uuid_to_owned = {}

        # The connections.
        # Each scale manager will auto-discover available
        # connections and attempt to use whatever validates.
        # These will factor into the ring above, because we
        # won't own an endpoint that is not suitable.

        self._loadbalancers = {} # Load balancer connections.
        self._clouds = {}        # Cloud connections.

        # Caches.
        # We persistent some state to zookeeper, but it's
        # very efficiently to only write deltas. We maintain
        # some information here that helps us to reduce writes.
        self._url = None
        self._sessions = {}

    @Atomic.sync
    def _reconnect(self):
        # NOTE: This is done in a locked routine simply
        # to ensure that we're exlusive of any important
        # watches firing, etc.
        self.client.reconnect()

    def serve(self):
        self._reconnect()

        # Load our configuration and register ourselves.
        self._register()

        # Watch all managers and endpoints.
        self.manager_change(self._managers_zkobj.running(watch=self.manager_change))
        self.endpoint_change(self._endpoints_zkobj.list(watch=self.endpoint_change))

    def _watch_ips(self):
        # Watch all IPs.
        # NOTE: This is called after either endpoints or
        # managers change, to ensure that all endpoint IPs
        # have been appropriately confirmed.
        self.register_ip(self._new_ips_zkobj.list(watch=self.register_ip))
        self.drop_ip(self._drop_ips_zkobj.list(watch=self.drop_ip))

    def unserve(self):
        self._managers_zkobj.unregister(self._uuid, self._names)
        self._setup_cloud_connections()
        self._setup_loadbalancer_connections()
        self._threadpool.clear()

    @Atomic.sync
    def _is_owned(self, key, cloud=None, loadbalancer=None):
        # Find the closest key.
        # If there are no keys available, we still go
        # through and track that there is no manager for
        # this endpoint (for whatever reason). This could
        # also happen if they are trying to use a particular
        # loadbalancer or cloud which is no supported etc.
        manager_key = None
        keys = self._key_to_uuid.keys()
        if len(keys) == 0:
            self.logging.error(self.logging.NO_MANAGER_AVAILABLE, key)
        else:
            keys.sort()
            index = bisect.bisect(keys, key)
            orig_index = index

            while True:
                # If this manager can satisfy this endpoint,
                # then it will get the privilenge of owning it.
                key = keys[index % len(keys)]
                this_uuid = self._key_to_uuid[key]
                (clouds, loadbalancers) = self._uuid_to_info[this_uuid]

                if (not cloud or cloud in clouds) and \
                   (not loadbalancer or loadbalancer in loadbalancers):
                    manager_key = this_uuid
                    break

                # Continue on to the next manager.
                # It's quite possible that we are unable to find any
                # manager that is capable of managing this object.
                index = (index+1) % len(keys)
                if index == orig_index:
                    self.logging.error(self.logging.NO_MANAGER_AVAILABLE, key)
                    break

        # Return the found key.
        return (manager_key == self._uuid)

    @Atomic.sync
    def endpoint_owned(self, endpoint):
        # Is it in the cache?
        endpoint_uuid = endpoint.uuid()
        if endpoint_uuid in self._uuid_to_owned:
            return self._uuid_to_owned[endpoint_uuid]

        # Cache whether or not this endpoint is owned by us.
        is_owned = self._is_owned(
            endpoint_uuid,
            cloud=endpoint.config.cloud,
            loadbalancer=endpoint.config.loadbalancer)
        self._uuid_to_owned[endpoint_uuid] = is_owned
        self.logging.info(
            self.logging.ENDPOINT_MANAGED,
            endpoint_uuid,
            is_owned)

        if is_owned:
            # Mark the endpoint as our own.
            endpoint.managed(self._uuid)

        return is_owned

    @Atomic.sync
    def _endpoint_change(self, endpoints):
        # NOTE: We play a little bit of trickery and
        # remove endpoints from our local list (to prevent
        # updates) before they may actually be removed from
        # Zookeeper. So it's possible that we'll have a
        # spurious event fire in this case, and we'd like to
        # avoid doing a bunch of extra work.
        endpoints.sort()
        current_endpoints = self._endpoint_names.keys()
        current_endpoints.sort()

        # Clear out the ownership cache.
        self._uuid_to_owned = {}

        to_add = []
        for endpoint_name in endpoints:
            if endpoint_name not in self._endpoint_names:
                to_add.append(endpoint_name)

        to_remove = []
        for endpoint_name in self._endpoint_names.keys():
            if not endpoint_name in endpoints:
                to_remove.append(endpoint_name)
            else:
                # Check a change in the uuid of the endpoint.
                # This could happen if the user is doing a bunch
                # renaming and a bunch of aliases and we end up
                # missing some watches being fired. We have to
                # teardown the old endpoints and build up new ones.
                _, endpoint_uuid = self._endpoints_zkobj.get(endpoint_name)
                if self._endpoint_names[endpoint_name] != endpoint_uuid:
                    to_remove.append(endpoint_name)
                    to_add.append(endpoint_name)

        for endpoint_name in to_remove:
            endpoint_uuid = self._endpoint_names[endpoint_name]
            del self._endpoint_names[endpoint_name]

            # Remove the endpoint object if there's only one mapping.
            if len(filter(
                lambda x: x == endpoint_uuid,
                self._endpoint_names.values())) == 0:

                # Remove from the loadbalancer.
                self._endpoint_data[endpoint_uuid].reload(exclude=True)
                del self._endpoint_data[endpoint_uuid]

        for endpoint_name in to_add:
            try:
                zkobj, endpoint_uuid = self.zkobj.endpoints().get(endpoint_name)
                if endpoint_uuid not in self._endpoint_data:
                    endpoint = Endpoint(
                        zkobj,
                        collect=self.collect,
                        find_cloud_connection=self._find_cloud_connection,
                        find_loadbalancer_connection=self._find_loadbalancer_connection)
                else:
                    # See below, we don't need to access this
                    # underlying endpoint because it already exists.
                    endpoint = None

            except EndpointNotFound:
                # Perhaps we just caught a race condition,
                # with the endpoint being deleted?
                continue

            except Exception:
                # This isn't expected.
                traceback.print_exc()
                continue

            # The endpoint will generally reload the loadbalancer
            # on startup. But we aren't tracking it yet, so it will
            # be excluded. So after we add it to our collection, we
            # do another reload() to ensure that it's included.
            self._endpoint_names[endpoint_name] = endpoint_uuid
            if endpoint_uuid not in self._endpoint_data:
                self._endpoint_data[endpoint_uuid] = endpoint
                endpoint.reload()

        # Log the change.
        self.logging.info(self.logging.ENDPOINTS_CHANGED, self._endpoint_names)

        # If we've lost endpoints, we need to make sure that
        # we clean up the leftover endpoint IPs. This is done
        # on regular basis, but we know it's likely out of date
        # right at this point.
        self.check_endpoint_ips()

    def endpoint_change(self, endpoints):
        if endpoints is None:
            endpoints = []
        self._endpoint_change(endpoints)
        self._watch_ips()

    def update_config(self, config):
        # If the config changes, then we may no longer
        # be eligible to run specific loadbalancers, etc.
        # We really need to rebuild our entire internal
        # structures, so off we go, starting at the top.
        self._register()

    def update_url(self, url):
        # As per update_config(), we can't really just change
        # this one thing in a safe way. So we trigger a reload
        # of the entire mamajama at this point.
        self._register()

    def _configure(self):
        """
        This setups up the configuration by combining given names.
        """
        config = ManagerConfig()

        # Load our given configuration.
        # This instantiates the manager class and builds the config
        # object. We will augment this configuration once we load the
        # loadbalancers and cloud connections.
        for name in self._names:
            config.update(
                self._managers_zkobj.get_config(name, watch=self.update_config))

        # Load the loadbalancer and cloud connections.
        # NOTE: We do this at this point because these connections
        # are very dependent on the underlying configuration.
        loadbalancers = self._setup_loadbalancer_connections(
            config=config, loadbalancers=config.loadbalancers)
        clouds = self._setup_cloud_connections(
            config=config, clouds=config.clouds)

        # Save our configuration.
        self.config = config

        return (loadbalancers, clouds)

    @Atomic.sync
    def _determine_keys(self, key_num):
        while len(self._keys) < key_num:
            # Generate keys.
            self._keys.append(utils.random_key())
        while len(self._keys) > key_num:
            # Drop keys while we're too high.
            del self._keys[len(self._keys) - 1]
        return self._keys

    @Atomic.sync
    def _setup_loadbalancer_connections(self, config=None, loadbalancers=None):
        if loadbalancers is None:
            loadbalancers = []

        # Create the loadbalancer connections.
        # NOTE: Any old loadbalancer object should be cleaned
        # up automatically (i.e. the objects should implement
        # fairly sensible __del__ methods when necessary).
        self._loadbalancers = {}
        for name in loadbalancers:

            # Skip unavailable loadbalancers.
            if not name in submodules.loadbalancer_submodules():
                continue

            try:
                # Create the loadbalancer connection.
                self._loadbalancers[name] = \
                    lb_connection.get_connection( \
                        name,
                        config=config,
                        zkobj=self.zkobj.loadbalancers().tree(name),
                        this_ip=self._ip,
                        error_notify=self.error_notify)
            except Exception:
                # This isn't expected.
                traceback.print_exc()
                continue

        # Return the set of supported loadbalancers.
        return self._loadbalancers.keys()

    @Atomic.sync
    def _find_loadbalancer_connection(self, name=None):
        # Try to find a matching loadbalancer connection, or return an unconfigured stub.
        return self._loadbalancers.get(name, lb_connection.LoadBalancerConnection(name))

    @Atomic.sync
    def _setup_cloud_connections(self, config=None, clouds=None):
        if clouds is None:
            clouds = []

        # Create the cloud connections.
        for name in clouds:

            # Skip unavailable clouds.
            if not name in submodules.cloud_submodules():
                continue

            try:
                # Create the cloud connection.
                # We automatically insert the address into all available cloud
                # configurations. This is passed in as the this_url parameter,
                # and is constructed from the current IP and the default port,
                # or (ideally) a URL that has been provided by the user.
                default_api = "http://%s:%d" % (self._ip, cli.DEFAULT_PORT)
                self._clouds[name] = \
                    cloud_connection.get_connection( \
                        name,
                        config=config,
                        zkobj=self.zkobj.clouds().tree(name),
                        this_ip=self._ip,
                        this_url=self._url or default_api)
            except Exception:
                # This isn't expected.
                traceback.print_exc()
                continue

        # Return the set of supported clouds.
        return self._clouds.keys()

    @Atomic.sync
    def _find_cloud_connection(self, name=None):
        # Try to find a matching cloud connection, or return an unconfigured stub.
        return self._clouds.get(name, cloud_connection.CloudConnection(name))

    @Atomic.sync
    def _register(self):
        # Read and listen to the global URL.
        # NOTE: We get the config through the update_url mechanism
        # as a convenience, the need the URL prior to running through
        # the full configuration.
        self._url = self._url_zkobj.get(watch=self.update_url)

        # Run our configuration.
        (loadbalancers, clouds) = self._configure()

        # Determine keys and register.
        keys = self._determine_keys(self.config.keys)

        # Write out our information blob.
        self._managers_zkobj.register(
            self._uuid,
            self._names,
            info={
                "names" : self._names,
                "keys": keys,
                "loadbalancers": loadbalancers,
                "clouds": clouds,
            })
        self.logging.info(self.logging.REGISTERED)

    @Atomic.sync
    def _manager_change(self, managers):
        # Clear out the ownership cache.
        self._key_to_uuid = {}
        self._uuid_to_info = {}
        self._uuid_to_owned = {}

        # Rebuild our manager info.
        # NOTE: We should be included in this list ourselves. If
        # we're not -- something is definitely up and the system
        # should catch up shortly.
        # NOTE: We allow the uuid_to_owned cache above to repopulate
        # lazily -- there's no rush to get it all done immediately.
        info_map = self._managers_zkobj.info_map()
        for (manager, info) in info_map.items():
            try:
                keys = info.get("keys", [])
                clouds = info.get("clouds", [])
                loadbalancers = info.get("loadbalancers", [])
            except (ValueError, AttributeError):
                # This is unexpected, old data version?
                continue

            # Save the info for this manager.
            self._uuid_to_info[manager] = (clouds, loadbalancers)
            for key in keys:
                self._key_to_uuid[key] = manager

        # Print our the new managers (with clouds and loadbalancers).
        self.logging.info(self.logging.MANAGERS_CHANGED, self._uuid_to_info)

    def manager_change(self, managers=None):
        if managers is None:
            managers = []
        self._manager_change(managers)
        self._watch_ips()

    @Atomic.sync
    def register_ip(self, ips):
        for ip in ips:
            matching_uuid = None

            # Skip the IP if we don't own it.
            if not self._is_owned(utils.sha_hash(ip)):
                continue

            # Find the owning endpoint for this
            # IP and confirmed it there.
            for (endpoint_uuid, endpoint) in self._endpoint_data.items():
                if endpoint.ip_confirmed(ip):
                    matching_uuid = endpoint_uuid
                    break

            if matching_uuid:
                # Write out the set of matching endpoints.
                self.endpoint_ips.add(ip, matching_uuid)

            # Always remove the IP.
            self._new_ips_zkobj.remove(ip)

    @Atomic.sync
    def drop_ip(self, ips):
        for ip in ips:
            matching_uuid = None

            # Skip the IP if we don't own it.
            if not self._is_owned(utils.sha_hash(ip)):
                continue

            # Find the owning endpoint for this
            # IP and confirmed it there.
            for (endpoint_uuid, endpoint) in self._endpoint_data.items():
                if endpoint.ip_dropped(ip):
                    matching_uuid = endpoint_uuid
                    break

            if matching_uuid:
                # Remove the ip from the ip address set.
                self.endpoint_ips.remove(ip)

            # Give notice to all loadbalancers.
            # They may use this to cleanup any stale state.
            for lb in self._loadbalancers.values():
                lb.dropped(ip)

            # Always remove the IP.
            self._drop_ips_zkobj.remove(ip)

    def error_notify(self, ip):
        # Call into the endpoint to notify of the error.
        for endpoint in self._endpoint_data.values():
            if endpoint.ip_errored(ip):
                return True

        # Check if we need to strip a port.
        if ":" in ip:
            (ip, _) = ip.split(":", 1)
            return self.error_notify(ip)

        return False

    @Atomic.sync
    def collect(self, endpoint, exclude=False):
        # Remap the endpoint if a different instances_source
        # has been specified here. If this is *not* a valid
        # endpoint then we will fall back to using this endpoint.
        if endpoint.config.instances_source:
            endpoint_uuid = self._endpoint_names.get(
                endpoint.config.instances_source)
            if endpoint_uuid is not None:
                endpoint = self._endpoint_data.get(
                    endpoint_uuid, endpoint)

        # Index based on the key.
        key = endpoint.key()

        # Map through all endpoints.
        # Every endpoint that matches the given endpoint
        # key needs to be collected in order to ensure that
        # we have all the backend instances we need.
        ips = []
        for e in self._endpoint_data.values():
            if exclude and endpoint == e:
                continue
            elif e.key() == key:
                ips.extend(e.backends())
        return ips

    def _metric_indicates_active(self, metrics):
        """
        Returns true if the metrics indicate that there are active connections.
        """
        active_metrics = metrics.get("active", (0, 0))
        try:
            return active_metrics[1] > 0
        except Exception:
            # The active metric is defined but as a bad form.
            self.logging.warn(self.logging.MALFORMED_METRICS, active_metrics)
            return False

    @Atomic.sync
    def _collect_metrics(self):
        # Collect all metrics from loadbalancers.
        results = {}
        for lb in self._loadbalancers.values():
            for (port, lb_metrics) in lb.metrics().items():
                if not port in results:
                    results[port] = lb_metrics
                else:
                    results[port].append(lb_metrics)
        return results

    @Atomic.sync
    def _collect_pending(self):
        # Collect all pending metrics from loadbalancers.
        results = {}
        for lb in self._loadbalancers.values():
            for (url, pending_count) in lb.pending().items():
                if not url in results:
                    results[url] = pending_count
                else:
                    results[url] += pending_count
        return results

    @Atomic.sync
    def update_metrics(self):
        """
        Collects the metrics from the loadbalancer, updates zookeeper and
        then collects the metrics posted by other managers.

        Returns a collection of metrics, which is indexed by the endpoint key.
        This is further indexed by the metric IP, which points to a list of
        collected metrics (from any number of different loadbalancers).
        """
        our_metrics = self._collect_metrics()
        self.logging.info(self.logging.LOCAL_METRICS, our_metrics)

        # Stuff all the metrics into Zookeeper.
        self._managers_zkobj.set_metrics(self._uuid, our_metrics)

        # Load all metrics (from other managers).
        all_metrics = {}
        metrics_map = self._managers_zkobj.metrics_map()

        # Read the keys for all managers.
        for (_, manager_metrics) in metrics_map.items():
            if not manager_metrics:
                continue
            for (port, port_metrics) in manager_metrics.items():
                if not port in all_metrics:
                    all_metrics[port] = port_metrics[:]
                else:
                    all_metrics[port].extend(port_metrics)

        self.logging.info(self.logging.ALL_METRICS, all_metrics)
        return all_metrics

    @Atomic.sync
    def update_pending(self):
        """
        Same as metrics, but for pending connections.
        """
        our_pending = self._collect_pending()
        self.logging.info(self.logging.LOCAL_PENDING, our_pending)

        # Stuff all the pending counts into Zookeeper.
        self._managers_zkobj.set_pending(self._uuid, our_pending)

        # Load all pending (from other managers).
        all_pending = {}
        pending_map = self._managers_zkobj.pending_map()

        # Read the keys for all managers.
        for (_, manager_pending) in pending_map.items():
            if not manager_pending:
                continue
            for (url, pending_count) in manager_pending.items():
                if not url in all_pending:
                    all_pending[url] = pending_count
                else:
                    all_pending[url] += pending_count

        self.logging.info(self.logging.ALL_PENDING, all_pending)
        return all_pending

    @Atomic.sync
    def _load_metrics(self, endpoint, all_metrics):
        """
        Load the particular metrics for a endpoint and return
        a tuple (metrics, metric_ports, active_ports) where:

             metrics - the computed metrics (list)
             metric_ports - the IP:port's used to generate the metrics
             active_ports - the collection of IP:port's indicating active
        """
        metrics = []
        metric_ports = set()
        active_ports = set()

        def _ips_to_ports(ips):
            # Return a list that has the configured port added for all entries.
            return map(lambda x: x if ":" in x else "%s:%d" % (x, endpoint.config.port), ips)

        # Remap the endpoint if a different metrics_source
        # has been specified here. If this is *not* a valid
        # endpoint then we will fall back to using this endpoint.
        if endpoint.config.metrics_source:
            endpoint_uuid = self._endpoint_names.get(
                endpoint.config.metrics_source)
            if endpoint_uuid is not None:
                endpoint = self._endpoint_data.get(
                    endpoint_uuid, endpoint)

        endpoint_active_ips = endpoint.active_ips()
        endpoint_inactive_ips = endpoint.inactive_ips()
        endpoint_active_ports = _ips_to_ports(endpoint_active_ips)
        endpoint_inactive_ports = _ips_to_ports(endpoint_inactive_ips)

        def _extract_metrics(port, these_metrics):
            if not port in endpoint_active_ports and \
               not port in endpoint_inactive_ports:
                return
            metrics.extend(these_metrics)
            metric_ports.add(port)
            for metric in these_metrics:
                if self._metric_indicates_active(metric):
                    active_ports.add(port)
                    break

        # Read any default metrics. We can override the source endpoint for
        # metrics here (so, for example, a backend database server can inheret
        # a set of metrics given for the front server).  This, like many other
        # things, is specified here by the name of the endpoint we are
        # inheriting metrics for. If not given, we default to the current
        # endpoint.
        metrics.append(endpoint.zkobj.custom_metrics or {})

        # Read all available ip-specific metrics.
        ip_metrics = endpoint.zkobj.ip_metrics().as_map()
        map(lambda (x, y): _extract_metrics(
            "%s:%d" % (x, endpoint.config.port), [y]),
            ip_metrics.items())

        # Read from all metrics.
        map(lambda (x, y): _extract_metrics(x, y), all_metrics.items())

        # Return the metrics.
        return metrics, list(metric_ports), list(active_ports)

    def _find_endpoint(self, ip):
        # Try looking it up.
        endpoint_uuid = self.endpoint_ips.get(ip)
        if endpoint_uuid is not None:
            return endpoint_uuid

        # If there a port that we should strip?
        if ":" in ip:
            ip = ip.split(":", 1)[0]
            endpoint_uuid = self.endpoint_ips.get(ip)
            if endpoint_uuid is not None:
                return endpoint_uuid

        # Try static addresses.
        # NOTE: This isn't really safe, it's more of
        # a best guess. This is why we return None if
        # we've got multiple matches.
        static_matches = []
        for (endpoint_uuid, endpoint) in self._endpoint_data.items():
            if ip in endpoint.config.static_ips():
                static_matches.append(endpoint_uuid)
        if len(static_matches) == 1:
            return static_matches[0]
        elif len(static_matches) > 1:
            self.logging.warn(self.logging.SESSION_MULTIPLE_MATCH, ip)
            return None

        # Nothing found.
        self.logging.warn(self.logging.SESSION_NO_MATCH, ip)
        return None

    def _collect_sessions(self):
        my_sessions = {}

        for lb in self._loadbalancers.values():
            sessions = lb.sessions() or {}

            # For each session,
            for backend, clients in sessions.items():
                # Look up the endpoint.
                endpoint_uuid = self._find_endpoint(backend)

                # If no endpoint,
                if not endpoint_uuid:
                    continue

                # Match it to all endpoints.
                endpoint_sessions = my_sessions.get(endpoint_uuid, {})
                for client in clients:
                    # Add to the sesssions list.
                    endpoint_sessions[client] = backend
                    my_sessions[endpoint_uuid] = endpoint_sessions

        return my_sessions

    @Atomic.sync
    def update_sessions(self):
        # Collect sessions.
        my_sessions = self._collect_sessions()
        old_sessions = self._sessions

        # Write out our sessions.
        for endpoint_uuid in my_sessions:
            for (client, backend) in my_sessions[endpoint_uuid].items():
                if old_sessions.get(client, None) != backend:
                    endpoint = self._endpoint_data.get(endpoint_uuid)
                    if endpoint:
                        endpoint.session_opened(client, backend)

        # Cull old sessions.
        for endpoint_uuid in old_sessions:
            for (client, backend) in old_sessions[endpoint_uuid].items():
                if my_sessions.get(endpoint_uuid, {}).get(client, None) != backend:
                    endpoint = self._endpoint_data.get(endpoint_uuid)
                    if endpoint:
                        endpoint.session_closed(client, backend)

        # Save the current state.
        self._sessions = my_sessions

    @Atomic.sync
    def check_endpoint_ips(self):
        # Ensure that there are no stale endpoint IPs.
        endpoint_ips = self.endpoint_ips.as_map()
        for (ip, endpoint_uuid) in endpoint_ips.items():
            if not endpoint_uuid in self._endpoint_data or \
               not ip in self._endpoint_data[endpoint_uuid].endpoint_ips():
                self.endpoint_ips.remove(ip)

        # Ensure existing endpoints are correctly represented.
        for (endpoint_uuid, endpoint) in self._endpoint_data.items():
            ips = endpoint.endpoint_ips()
            for ip in ips:
                if not endpoint_ips.get(ip) == endpoint_uuid:
                    self.endpoint_ips.add(ip, endpoint_uuid)

    def update(self, elapsed=None):
        # Update the list of sessions.
        self.update_sessions()

        # Save and load the current metrics.
        # This has the side-effect of dumping all the current metric
        # data into zookeeper for other managers to use. They may have
        # slightly delayed version of the metrics, but only by as much
        # as our healthcheck interval.
        all_metrics = self.update_metrics()
        all_pending = self.update_pending()

        # Run endpoint updates.
        active = self.update_endpoints(all_metrics, all_pending, elapsed=elapsed)
        self._managers_zkobj.set_active(self._uuid, active)

    def update_endpoints(self, all_metrics, all_pending, elapsed=None):
        # List of updates.
        update_jobs = {}
        total_active = 0

        # Does a health check on all the endpoints that are being managed.
        for (endpoint_uuid, endpoint) in self._endpoint_data.items():

            # Check ownership for the healthcheck.
            owned = self.endpoint_owned(endpoint)

            # Drop any sessions indicated by manager.
            endpoint.drop_sessions(authoritative=owned)

            # Grab all names.
            endpoint_names = [
                endpoint_name
                for (endpoint_name, other_uuid)
                in self._endpoint_names.items()
                if endpoint_uuid == other_uuid
            ]

            # Do not kick the endpoint if it is not currently owned by us.
            if not(owned):
                self.logging.info(self.logging.ENDPOINT_SKIPPED, endpoint_names)
                continue

            metrics, metric_ports, active_ports = \
                self._load_metrics(endpoint, all_metrics)

            # Compute the globally weighted averages.
            metrics = calculate_weighted_averages(metrics)
            total_active += metrics.get("active", 0)

            # Add in a count of pending connections.
            if endpoint.config.url in all_pending:
                metrics["pending"] = float(all_pending[endpoint.config.url])
                if len(metric_ports) > 1:
                    # NOTE: We may have no instances with pending connections,
                    # but we still do a best effort attempt to scale this by
                    # the number of available instances. Otherwise, the user
                    # has to treat pending with undue care and attention.
                    metrics["pending"] = metrics["pending"] / len(metric_ports)

            # Do the endpoint update.
            job = self._threadpool.submit(
                endpoint.update,
                metrics=metrics,
                metric_instances=len(metric_ports),
                active_ports=active_ports,
                update_interval=elapsed)
            update_jobs[endpoint_uuid] = (endpoint_names, job)

        # Wait for all updates to finish.
        for (endpoint_uuid, (endpoint_names, job)) in update_jobs.items():
            try:
                job.join()
                self.logging.info(self.logging.ENDPOINT_UPDATED, endpoint_names)
            except Exception:
                error = traceback.format_exc()
                self.logging.warn(self.logging.ENDPOINT_ERROR, endpoint_names, error)

        # Return the total active connections.
        return total_active

    @Atomic.sync
    def sleep_until(self, until):
        while self.is_running():
            cur_time = time.time()
            if cur_time >= until:
                break
            else:
                self._wait(until-cur_time)

    def run(self):
        while self.is_running():
            try:
                # Reconnect to the Zookeeper servers.
                self.serve()

                # Clean out stale endpoints.
                # We do this first thing, to ensure that we
                # don't run any updates on endpoints that have
                # been deleted while we've been offline.
                self._endpoints_zkobj.clean()

                # Perform continuous health checks.
                elapsed = None
                while self.is_running():
                    start_time = time.time()
                    self.check_endpoint_ips()
                    self.update(elapsed=elapsed)
                    self._endpoints_zkobj.clean()

                    # We only sleep for the part of the interval that
                    # we were not active for. This allows us to actually
                    # pace reasonable intervals at the specified time.
                    # I.e., if the health_check interval is 10 seconds,
                    # and we have a few dozens endpoints we could do a
                    # decent job of calling in to each endpoint every ten
                    # seconds.
                    self.sleep_until(start_time + self.config.interval)
                    elapsed = (time.time() - start_time)

            except ZookeeperException:
                # Sleep on ZooKeeper exception and retry.
                error = traceback.format_exc()
                logging.error("Received ZooKeeper exception: %s", error)
                self.sleep_until(time.time() + self.config.interval)

        # If we've stopped, make sure we clear out all endpoints.
        # Since we've passed our methods to those objects on creation,
        # there is currently a reference cycle there.
        self.unserve()
