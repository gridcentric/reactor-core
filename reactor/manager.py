import logging
import threading
import time
import uuid
import bisect
import traceback

from . import ips as ips_mod
from . import submodules
from . atomic import Atomic
from . config import Config
from . zookeeper.client import ZookeeperClient
from . zookeeper.connection import ZookeeperException
from . objects.root import Reactor
from . utils import random_key
from . endpoint import Endpoint
from . metrics.calculator import calculate_weighted_averages
from . loadbalancer import connection as lb_connection
from . cloud import connection as cloud_connection

class ManagerConfig(Config):

    def __init__(self, **kwargs):
        super(ManagerConfig, self).__init__("manager", **kwargs)

    loadbalancers = Config.multiselect(label="Enabled Loadbalancer Drivers", order=1,
        options=submodules.loadbalancer_options(),
        default=submodules.loadbalancer_submodules(),
        description="List of supported loadbalancers (e.g. nginx).")

    clouds = Config.multiselect(label="Enabled Cloud Drivers", order=1,
        options=submodules.cloud_options(),
        default=submodules.cloud_submodules(),
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

# IMPORTANT: There is a potential deadlock if the manager is locked when
# setting / clearing a zookeeper watch. Our policy is that the manager cannot
# be locked when it makes a call to one of the zookeeper client's watch
# functions. Note to check the full call chain to ensure that a higher level
# function is not setting the lock.

class ScaleManager(Atomic):

    def __init__(self, zk_servers, names=None):
        super(ScaleManager, self).__init__()
        self.client = ZookeeperClient(zk_servers)
        self.zkobj = Reactor(self.client)

        # Runtime state.
        self._running = True
        self._cond = threading.Condition()

        # Ppersistent objects.
        self._url_zkobj = self.zkobj.url()
        self._managers_zkobj = self.zkobj.managers()
        self._endpoints_zkobj = self.zkobj.endpoints()
        self._new_ips_zkobj = self.zkobj.new_ips()
        self._drop_ips_zkobj = self.zkobj.drop_ips()

        # Manager names.
        # Each manager has a collection of readable names.
        # Basically, this can be used to provide some kind
        # of sensible scheme for configuration, etc.
        # By default, these names are the available non-local
        # IP addresses found on the machine.
        if names is None:
            self._names = ips_mod.find_global()
        else:
            self._names = names

        # Our configuration.
        self.config = ManagerConfig()

        # Manager uuid (generated).
        # This doesn't serve any particular purpose other than
        # giving us a unique node to register our information.
        # We save a collection of keys, loadbalancers, clouds, etc.
        self._uuid = str(uuid.uuid4())

        # Endpoint map.
        self._endpoints = {}

        # The ring.
        # In order to minimize disruption and keep services
        # running smoothly, we maintain a ring and use a simple
        # consistent hashing scheme to figure out whether scale
        # manager is response for "owning" a service.

        self._keys = []         # Our local manager keys.
        self._key_to_uuid = {}  # Map of manager key -> uuid.
        self._key_to_owned = {} # Endpoint to ownership.
        self._uuid_to_info = {} # Map of manager uuid -> info.

        # The connections.
        # Each scale manager will auto-discover available
        # connections and attempt to use whatever validates.
        # These will factor into the ring above, because we
        # won't own an endpoint that is not suitable.

        self.loadbalancers = {} # Load balancer connections.
        self.locks = {}         # Load balancer locks.
        self.clouds = {}        # Cloud connections.

        # Caches.
        # We persistent some state to zookeeper, but it's
        # very efficiently to only write deltas. We maintain
        # some information here that helps us to reduce writes.

        self._url = None
        self._sessions = {}

    def __del__(self):
        self.unserve()
        super(ScaleManager, self).__init__()

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
        self._url_zkobj.unwatch()
        self._managers_zkobj.unwatch()
        self._endpoints_zkobj.unwatch()
        self._new_ips_zkobj.unwatch()
        self._drop_ips_zkobj.unwatch()
        self.zkobj.unwatch()
        self._endpoint_change([])

    @Atomic.sync
    def _manager_select(self, endpoint):
        # Find the closest key.
        # If there are no keys available, we still go
        # through and track that there is no manager for
        # this endpoint (for whatever reason). This could
        # also happen if they are trying to use a particular
        # loadbalancer or cloud which is no supported etc.
        manager_key = None
        keys = self._key_to_uuid.keys()
        if len(keys) == 0:
            logging.error("No scale manager available!")
        else:
            keys.sort()
            index = bisect.bisect(keys, endpoint.key())
            orig_index = index

            while True:
                # If this manager can satisfy this endpoint,
                # then it will get the privilenge of owning it.
                key = keys[index % len(keys)]
                this_uuid = self._key_to_uuid[key]
                (clouds, loadbalancers) = self._uuid_to_info[this_uuid]

                if (not endpoint.config.cloud or \
                    endpoint.config.cloud in clouds) and \
                   (not endpoint.config.loadbalancer or \
                    endpoint.config.loadbalancer in loadbalancers):
                    manager_key = this_uuid
                    break

                # Continue on to the next manager.
                # It's quite possible that we are unable to find
                # any manager that is capable of managing this endpoint.
                index = (index+1) % len(keys)
                if index == orig_index:
                    logging.error("No suitable scale manager available!")
                    break

        # Track whether or not this endpoint is owned by us.
        self._key_to_owned[endpoint.key()] = (manager_key == self._uuid)

        logging.info("Endpoint %s owned by %s (%s).",
            endpoint.key(), manager_key,
            self.endpoint_owned(endpoint) and "That's me!" or "Not me!")

        # Check if it is one of our own.
        # Start the endpoint if necessary (now owned).
        endpoint.managed(self._uuid)

    @Atomic.sync
    def endpoint_owned(self, endpoint):
        if not endpoint.key() in self._key_to_owned:
            self._manager_select(endpoint)
        return self._key_to_owned[endpoint.key()]

    @Atomic.sync
    def _endpoint_change(self, endpoints):
        logging.info("Endpoints have changed: new=%s, existing=%s",
                     endpoints, self._endpoints.keys())

        # Clear out the ownership cache.
        self._key_to_owned = {}

        to_add = []
        for endpoint_name in endpoints:
            if endpoint_name not in self._endpoints:
                to_add.append(endpoint_name)

        to_remove = []
        for endpoint_name in self._endpoints.keys():
            if not endpoint_name in endpoints:
                to_remove.append(endpoint_name)

        for endpoint_name in to_remove:
            self._endpoints[endpoint_name].reload(exclude=True)
            # This trick is necessary to order to break the
            # reference cycle that the endpoint might have.
            # Because we've passed in _find_*_connection()
            # as well as self.collect, the endpoint has a
            # reference to this scale manager that needs to
            # be broken before it will be garbage collected.
            self._endpoints[endpoint_name].break_refs()
            del self._endpoints[endpoint_name]

        for endpoint_name in to_add:
            self._endpoints[endpoint_name] = \
                Endpoint(
                    self.zkobj.endpoints().get(endpoint_name),
                    collect=self.collect,
                    find_cloud_connection=self._find_cloud_connection,
                    find_loadbalancer_connection=self._find_loadbalancer_connection)

            # The endpoint will generally reload the loadbalancer
            # on startup. But we aren't tracking it yet, so it will
            # be excluded. So after we add it to our collection, we
            # do another reload() to ensure that it's included.
            self._endpoints[endpoint_name].reload()

    def endpoint_change(self, endpoints):
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
        loadbalancers = self._setup_loadbalancer_connections(config)
        clouds = self._setup_cloud_connections(config)

        # Save our configuration.
        self.config = config

        return (loadbalancers, clouds)

    @Atomic.sync
    def _determine_keys(self, key_num):
        while len(self._keys) < key_num:
            # Generate keys.
            self._keys.append(random_key())
        while len(self._keys) > key_num:
            # Drop keys while we're too high.
            del self._keys[len(self._keys) - 1]
        return self._keys

    @Atomic.sync
    def _setup_loadbalancer_connections(self, config):
        # Create the loadbalancer connections.
        # NOTE: Any old loadbalancer object should be cleaned
        # up automatically (i.e. the objects should implement
        # fairly sensible __del__ methods when necessary).
        self.loadbalancers = {}
        for name in config.loadbalancers:
            # Ensure that we have locks for this loadbalancer.
            if not name in self.locks:
                self.locks[name] = self.zkobj.loadbalancers().locks(name)

            # Create the load balancer itself.
            self.loadbalancers[name] = \
                lb_connection.get_connection( \
                    name, config=config, locks=self.locks[name])

        # Return the set of supported loadbalancers.
        return self.loadbalancers.keys()

    @Atomic.sync
    def _find_loadbalancer_connection(self, name=None):
        # Try to find a matching loadbalancer connection, or return an unconfigured stub.
        return self.loadbalancers.get(name, lb_connection.LoadBalancerConnection(name))

    @Atomic.sync
    def _setup_cloud_connections(self, config):
        # Create the cloud connections.
        # NOTE: Same restrictions apply to cloud connections.
        self.clouds = {}
        for name in config.clouds:
            self.clouds[name] = \
                cloud_connection.get_connection( \
                    name, config=config)

        # We automatically insert the address into all available
        # cloud configurations. This absolutely requires the cloud
        # configuration to support an address key for the manager,
        # but we can address that on a case-by-case basis for now.
        for cloud in self.clouds.values():
            config = cloud._manager_config()
            if hasattr(config, 'reactor'):
                # We use the URL if it's provided, otherwise
                # it's gonna be a best guess scenario. We set
                # it to the current name and the default port.
                config.reactor = self._url or \
                    "http://%s:8080" % self._names[0]

        # Return the set of supported clouds.
        return self.clouds.keys()

    @Atomic.sync
    def _find_cloud_connection(self, name=None):
        # Try to find a matching cloud connection, or return an unconfigured stub.
        return self.clouds.get(name, cloud_connection.CloudConnection(name))

    @Atomic.sync
    def _register(self):
        # Figure out our global IPs.
        logging.info("Manager %s has key %s.", str(self._names), self._uuid)

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
                "keys": keys,
                "loadbalancers": loadbalancers,
                "clouds": clouds
            })

    @Atomic.sync
    def _manager_change(self, managers):
        # Clear out the ownership cache.
        self._key_to_uuid = {}
        self._key_to_owned = {}
        self._uuid_to_info = {}

        # Rebuild our manager info.
        # NOTE: We should be included in this list ourselves. If
        # we're not -- something is definitely up and the system
        # should catch up shortly.
        # NOTE: We allow the key_to_owned cache above to repopulate
        # lazily -- there's no rush to get it all done immediately.
        info_map = self._managers_zkobj.info_map()
        for (manager, info) in info_map.items():
            try:
                keys = info.get("keys", [])
                clouds = info.get("clouds", [])
                loadbalancers = info.get("loadbalancers", [])
            except (ValueError, AttributeError):
                continue

            # Save the info for this manager.
            self._uuid_to_info[manager] = (clouds, loadbalancers)
            for key in keys:
                self._key_to_uuid[key] = manager

    def manager_change(self, managers):
        self._manager_change(managers)
        self._watch_ips()

    @Atomic.sync
    def register_ip(self, ips):
        for ip in ips:
            endpoint_name = None

            # Find the owning endpoint for this
            # IP and confirmed it there.
            for (name, endpoint) in self._endpoints.items():
                if not self.endpoint_owned(endpoint):
                    continue
                if endpoint.ip_confirmed(ip):
                    endpoint_name = name
                    break

            if endpoint_name:
                # We're done with the IP.
                self._new_ips_zkobj.remove(ip)

                # Write out the set of matching endpoints.
                self.zkobj.endpoint_ips().add(ip, endpoint_name)

    @Atomic.sync
    def drop_ip(self, ips):
        for ip in ips:
            endpoint_name = None

            # Find the owning endpoint for this
            # IP and confirmed it there.
            for (name, endpoint) in self._endpoints.items():
                if not self.endpoint_owned(endpoint):
                    continue
                if endpoint.ip_dropped(ip):
                    endpoint_name = name
                    break

            if endpoint_name:
                # We're done with the IP.
                self._drop_ips_zkobj.remove(ip)

                # Remove the ip from the ip address set.
                self.zkobj.endpoint_ips().remove(ip)

                # Drop it from any locks that may hold it.
                for lock in self.locks.values():
                    lock.remove(ip)
            else:
                # Unknown? Just make sure it's not in new_ips.
                self._new_ips_zkobj.remove(ip)
                self._drop_ips_zkobj.remove(ip)
                self.zkobj.endpoint_ips().remove(ip)

    @Atomic.sync
    def collect(self, endpoint, exclude=False):
        key = endpoint.key()

        # Map through all endpoints.
        # Every endpoint that matches the given endpoint
        # key needs to be collected in order to ensure that
        # we have all the backend instances we need.
        ips = []
        for e in self._endpoints.values():
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
            logging.warning("Malformed metrics found: %s", active_metrics)
            return False

    @Atomic.sync
    def _collect_metrics(self):
        # Collect all metrics from loadbalancers.
        results = {}
        for lb in self.loadbalancers.values():
            for (host, lb_metrics) in lb.metrics().items():
                if not host in results:
                    results[host] = [lb_metrics]
                else:
                    results[host].append(lb_metrics)
        return results

    @Atomic.sync
    def _collect_pending(self):
        # Collect all pending metrics from loadbalancers.
        results = {}
        for lb in self.loadbalancers.values():
            for (url, pending_count) in lb.pending().items():
                if not url in results:
                    results[url] = pending_count
                else:
                    results[url] += pending_count
        return results

    def update_metrics(self):
        """
        Collects the metrics from the loadbalancer, updates zookeeper and
        then collects the metrics posted by other managers.

        Returns a collection of metrics, which is indexed by the endpoint key.
        This is further indexed by the metric IP, which points to a list of
        collected metrics (from any number of different loadbalancers).
        """
        our_metrics = self._collect_metrics()
        logging.debug("Loadbalancers returned metrics: %s", our_metrics)

        # Stuff all the metrics into Zookeeper.
        self._managers_zkobj.set_metrics(self._uuid, our_metrics)

        # Load all metrics (from other managers).
        all_metrics = {}
        metrics_map = self._managers_zkobj.metrics_map()

        # Read the keys for all managers.
        for (_, manager_metrics) in metrics_map.items():
            if not manager_metrics:
                continue
            for (host, host_metrics) in manager_metrics.items():
                if not host in all_metrics:
                    all_metrics[host] = host_metrics[:]
                else:
                    all_metrics[host].extend(host_metrics)

        logging.debug("All metrics: %s", all_metrics)
        return all_metrics

    def update_pending(self):
        """
        Same as metrics, but for pending connections.
        """
        our_pending = self._collect_pending()
        logging.debug("Loadbalancers returned pending: %s", our_pending)

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

        logging.debug("All pending: %s", all_pending)
        return all_pending

    @Atomic.sync
    def _load_metrics(self, endpoint, all_metrics):
        """
        Load the particular metrics for a endpoint and return
        a tuple (metrics, metric_ips, active_ips) where:

             metrics - the computed metrics (list)
             metric_ips - the IPs used to generate the metrics
             active_ips - the collection of IPs indicating active
        """
        metrics = []
        metric_ips = set()
        active_ips = set()

        endpoint_active_ips = endpoint.active_ips()
        endpoint_inactive_ips = endpoint.inactive_ips()
        def _extract_metrics(ip, these_metrics):
            if not ip in endpoint_active_ips and \
               not ip in endpoint_inactive_ips:
                return
            metrics.extend(these_metrics)
            metric_ips.add(ip)
            for metric in these_metrics:
                if self._metric_indicates_active(metric):
                    active_ips.add(ip)
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
        map(lambda (x, y): _extract_metrics(x, [y]), ip_metrics.items())

        # Read from all metrics.
        map(lambda (x, y): _extract_metrics(x, y), all_metrics.items())

        # Return the metrics.
        logging.debug("Endpoint metrics: %s", metrics)
        return metrics, list(metric_ips), list(active_ips)

    def _find_endpoint(self, ip):
        # Try looking it up.
        endpoint_name = self.zkobj.endpoint_ips().get(ip)
        if endpoint_name is not None:
            return endpoint_name

        # Try static addresses.
        # NOTE: This isn't really safe, it's more of
        # a best guess. This is why we return None if
        # we've got multiple matches.
        static_matches = []
        for (name, endpoint) in self._endpoints.items():
            if ip in endpoint.config.static_ips():
                static_matches.append(name) 
        if len(static_matches) == 1:
            return static_matches[0]
        elif len(static_matches) > 1:
            logging.warning("Session with multiple matches: %s", ip)
            return None

        # Nothing found.
        logging.error("Session without endpoint: %s", ip)
        return None

    def _collect_sessions(self):
        my_sessions = {}

        for lb in self.loadbalancers.values():
            sessions = lb.sessions() or {}

            # For each session,
            for backend, clients in sessions.items():
                # Look up the endpoint.
                endpoint_name = self._find_endpoint(backend)

                # If no endpoint,
                if not endpoint_name:
                    continue

                # Match it to all endpoints.
                endpoint_sessions = my_sessions.get(endpoint_name, {})
                for client in clients:
                    # Add to the sesssions list.
                    endpoint_sessions[client] = backend
                    my_sessions[endpoint_name] = endpoint_sessions

        return my_sessions

    def update_sessions(self):
        # Collect sessions.
        my_sessions = self._collect_sessions()
        old_sessions = self._sessions

        # Write out our sessions.
        for endpoint_name in my_sessions:
            for (client, backend) in my_sessions[endpoint_name].items():
                if old_sessions.get(client, None) != backend:
                    endpoint = self._endpoints.get(endpoint_name)
                    if endpoint:
                        endpoint.session_opened(client, backend)

        # Cull old sessions.
        for endpoint_name in old_sessions:
            for (client, backend) in old_sessions[endpoint_name].items():
                if my_sessions.get(endpoint_name, {}).get(client, None) != backend:
                    endpoint = self._endpoints.get(endpoint_name)
                    if endpoint:
                        endpoint.session_closed(client, backend)

        # Save the current state.
        self._sessions = my_sessions

    @Atomic.sync
    def update(self):
        # Update the list of sessions.
        self.update_sessions()

        # Save and load the current metrics.
        # This has the side-effect of dumping all the current metric
        # data into zookeeper for other managers to use. They may have
        # slightly delayed version of the metrics, but only by as much
        # as our healthcheck interval.
        all_metrics = self.update_metrics()
        all_pending = self.update_pending()

        # Does a health check on all the endpoints that are being managed.
        for (name, endpoint) in self._endpoints.items():

            # Check ownership for the healthcheck.
            owned = self.endpoint_owned(endpoint)

            # Drop any sessions indicated by manager.
            endpoint.drop_sessions(authoritative=owned)

            # Do not kick the endpoint if it is not currently owned by us.
            if not(owned):
                continue

            try:
                metrics, metric_ips, active_ips = \
                    self._load_metrics(endpoint, all_metrics)

                # Compute the globally weighted averages.
                metrics = calculate_weighted_averages(metrics)

                # Add in a count of pending connections.
                if endpoint.config.url in all_pending:
                    metrics["pending"] = float(all_pending[endpoint.config.url])
                    if len(metric_ips) > 1:
                        # NOTE: We may have no instances with pending connections,
                        # but we still do a best effort attempt to scale this by
                        # the number of available instances. Otherwise, the user
                        # has to treat pending with undue care and attention.
                        metrics["pending"] = metrics["pending"] / len(metric_ips)

                # Update the live metrics and connections.
                logging.debug("Metrics for endpoint %s from %s: %s",
                              name, str(metric_ips), metrics)

                # Do the endpoint update.
                endpoint.update(metrics=metrics,
                                metric_instances=len(metric_ips),
                                active_ips=active_ips)
            except Exception:
                error = traceback.format_exc()
                logging.error("Error updating endpoint %s: %s", name, error)

    def run(self):
        while self._running:
            try:
                # Reconnect to the Zookeeper servers.
                self.serve()

                # Perform continuous health checks.
                while self._running:
                    self.update()
                    if self._running:
                        time.sleep(self.config.interval)

            except ZookeeperException:
                # Sleep on ZooKeeper exception and retry.
                error = traceback.format_exc()
                logging.debug("Received ZooKeeper exception: %s", error)
                if self._running:
                    time.sleep(self.config.interval)

        # If we've stopped, make sure we clear out all endpoints.
        # Since we've passed our methods to those objects on creation,
        # there is currently a reference cycle there.
        self.unserve()
        self.client.disconnect()

    def stop(self):
        self._running = False
