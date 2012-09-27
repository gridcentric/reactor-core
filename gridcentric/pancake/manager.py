import logging
import threading
import time
import uuid
import hashlib
import bisect
import json
import traceback
import socket
from StringIO import StringIO

from gridcentric.pancake.config import Config
from gridcentric.pancake.config import ConfigView

from gridcentric.pancake.endpoint import Endpoint
from gridcentric.pancake.endpoint import State

import gridcentric.pancake.loadbalancer.connection as lb_connection
from gridcentric.pancake.loadbalancer.connection import BackendIP

from gridcentric.pancake.zookeeper.connection import ZookeeperConnection
from gridcentric.pancake.zookeeper.connection import ZookeeperException
import gridcentric.pancake.zookeeper.paths as paths

from gridcentric.pancake.metrics.calculator import calculate_weighted_averages

# We must always specify some domain for the installation.
# If none is available, we use example.com as it is protected
# under domain name RFC as a reserved name.
NODOMAIN = "example.com"

class ManagerConfig(Config):

    def ips(self):
        """ The IPs on the public interface. """
        return self._getlist("manager", "ips")

    def loadbalancer_names(self):
        """ The name of the loadbalancer. """
        return self._getlist("manager", "loadbalancer")

    def loadbalancer_config(self, name):
        """ The set of keys required to configure the loadbalancer. """
        return ConfigView(self, "loadbalancer:%s" % name)

    def mark_maximum(self, label):
        if label in ['unregistered', 'decommissioned']:
            return self._getint("manager", "%s_wait" % (label), 20)

    def keys(self):
        return self._getint("manager", "keys", 64)

    def health_check(self):
        return self._getint("manager", "health_check", 5)

def locked(fn):
    def wrapped_fn(self, *args, **kwargs):
        try:
            self.cond.acquire()
            return fn(self, *args, **kwargs)
        finally:
            self.cond.release()
    return wrapped_fn

class ScaleManager(object):

    def __init__(self, zk_servers, names=[]):

        self.names      = names
        self.zk_servers = zk_servers
        self.zk_conn    = None
        self.running    = False
        self.config     = ManagerConfig("")
        self.cond       = threading.Condition()

        self.uuid   = str(uuid.uuid4()) # Manager uuid (generated).
        self.domain = NODOMAIN          # Pancake domain.

        self.endpoints = {}        # Endpoint map (name -> endpoint)
        self.key_to_endpoints = {} # Endpoint map (key() -> [names...])
        self.confirmed = {}        # Endpoint map (name -> confirmed IPs)

        self.managers = {}        # Forward map of manager keys.
        self.manager_ips = []     # List of all manager IPs.
        self.registered_ips = []  # List of registered IPs.
        self.manager_keys = []    # Our local manager keys.
        self.key_to_manager = {}  # Reverse map for manager keys.
        self.key_to_owned = {}    # Endpoint to ownership.

        self.load_balancer = None # Load balancer connections.

    @locked
    def serve(self):
        # Create a Zookeeper connection.
        if self.zk_conn:
            self.zk_conn.close()
        self.zk_conn = ZookeeperConnection(self.zk_servers)

        # Load our configuration and register ourselves.
        self.manager_register()

        # Read the domain.
        self.reload_domain(self.zk_conn.watch_contents(\
                                paths.domain(),
                                self.reload_domain,
                                default_value=self.domain))

        # Watch all managers and endpoints.
        self.manager_change(self.zk_conn.watch_children(paths.managers(), self.manager_change))
        self.endpoint_change(self.zk_conn.watch_children(paths.endpoints(), self.endpoint_change))

        # Watch all IPs.
        self.register_ip(self.zk_conn.watch_children(paths.new_ips(), self.register_ip))
        self.unregister_ip(self.zk_conn.watch_children(paths.drop_ips(), self.unregister_ip))

    @locked
    def manager_select(self, endpoint):
        # Remember whether this was previous managed.
        managed = self.endpoint_owned(endpoint)

        # Find the closest key.
        keys = self.key_to_manager.keys()
        if len(keys) == 0:
            logging.error("No scale manager available!")
            manager_key = None
        else:
            keys.sort()
            index = bisect.bisect(keys, endpoint.key())
            key = keys[index % len(self.key_to_manager)]
            manager_key = self.key_to_manager[key]

        # Check if this is us.
        self.key_to_owned[endpoint.key()] = (manager_key == self.uuid)

        logging.info("Endpoint %s owned by %s (%s)." % \
            (endpoint.name, manager_key, \
            self.endpoint_owned(endpoint) and "That's me!" or "Not me!"))

        # Check if it is one of our own.
        # Start the endpoint if necessary (now owned).
        if self.endpoint_owned(endpoint):
            self.zk_conn.write(paths.endpoint_manager(endpoint.name), self.uuid, ephemeral=True)
            if not(managed):
                self.start_endpoint(endpoint)

    @locked
    def manager_remove(self, endpoint):
        if self.key_to_owned.has_key(endpoint.key()):
            del self.key_to_owned[endpoint.key()]

    @locked
    def endpoint_owned(self, endpoint):
        return self.key_to_owned.get(endpoint.key(), False)

    @locked
    def endpoint_change(self, endpoints):
        logging.info("Endpoints have changed: new=%s, existing=%s" %
                     (endpoints, self.endpoints.keys()))

        for endpoint_name in endpoints:
            if endpoint_name not in self.endpoints:
                self.create_endpoint(endpoint_name)

        endpoints_to_remove = []
        for endpoint_name in self.endpoints:
            if endpoint_name not in endpoints:
                self.remove_endpoint(endpoint_name, unmanage=True)
                endpoints_to_remove += [endpoint_name]

        for endpoint in endpoints_to_remove:
            del self.endpoints[endpoint]

    @locked
    def update_config(self, config_str):
        self.manager_register(config_str)
        self.reload_loadbalancer()

    @locked
    def manager_register(self, config_str=''):
        # Figure out our global IPs.
        logging.info("Manager %s has key %s." % (str(self.names), self.uuid))

        # Load our given configuration.
        self.config = ManagerConfig(config_str)

        # Watch for future updates to our configuration, and recall update_config.
        self.zk_conn.clear_watch_fn(self.update_config)
        global_config = self.zk_conn.watch_contents(paths.config(), self.update_config)
        if global_config:
            self.config.reload(global_config)

        # We remove all existing registered IPs.
        for ip in self.registered_ips:
            if self.zk_conn.read(paths.manager_ip(ip)) == self.uuid:
                logging.info("Clearing IP '%s'." % ip)
                self.zk_conn.delete(paths.manager_ip(ip))
        self.registered_ips = []

        # NOTE: We may have multiple global IPs (especially in the case of
        # provisioning a cluster that could have floating IPs that move around.
        # We read in each of the configuration blocks in turn, and hope that
        # they are not somehow mutually incompatible.
        if self.names:
            def load_ip_config(ip):
                # Reload our local config.
                local_config = self.zk_conn.watch_contents(
                                    paths.manager_config(ip),
                                    self.update_config)
                if local_config:
                    self.config.reload(local_config)

            # Read all configured IPs.
            for ip in self.names:
                load_ip_config(ip)
            configured_ips = self.config.ips()
            for ip in configured_ips:
                load_ip_config(ip)

            def register_ip(name):
                try:
                    # Register our IP.
                    ip = socket.gethostbyname(name)
                    self.zk_conn.write(paths.manager_ip(ip), self.uuid, ephemeral=True)
                    logging.info("Registered IP '%s'." % ip)
                    self.registered_ips.append(ip)
                except socket.error:
                    logging.error("Skipping registration of '%s'." % name)

            # Register configured IPs if available.
            if configured_ips:
                for ip in configured_ips:
                    register_ip(ip)
            else:
                for name in self.names:
                    register_ip(name)

        # Generate keys.
        while len(self.manager_keys) < self.config.keys():
            # Generate a random hash key to associate with this manager.
            self.manager_keys.append(hashlib.md5(str(uuid.uuid4())).hexdigest())
        while len(self.manager_keys) > self.config.keys():
            # Drop keys while we're too high.
            del self.manager_keys[len(self.manager_keys) - 1]

        # Write out our associated hash keys as an ephemeral node.
        key_string = ",".join(self.manager_keys)
        self.zk_conn.write(paths.manager_keys(self.uuid), key_string, ephemeral=True)
        logging.info("Generated %d keys." % len(self.manager_keys))

        # If we're not doing initial setup, refresh endpoints.
        for endpoint in self.endpoints.values():
            self.manager_select(endpoint)

        # Create the loadbalancer connections.
        # NOTE: Any old loadbalancer object should be cleaned
        # up automatically (i.e. the objects should implement
        # fairly sensible __del__ methods when necessary).
        self.load_balancer = lb_connection.LoadBalancers()
        for name in self.config.loadbalancer_names():
            self.load_balancer.append(\
                lb_connection.get_connection(\
                    name, self.config.loadbalancer_config(name), self))

    @locked
    def manager_change(self, managers):
        for manager in managers:
            if manager not in self.managers:
                # Read the key and update all mappings.
                keys = self.zk_conn.read(paths.manager_keys(manager)).split(",")
                logging.info("Found manager %s with %d keys." % (manager, len(keys)))
                self.managers[manager] = keys
                for key in keys:
                    self.key_to_manager[key] = manager

        managers_to_remove = []
        for manager in self.managers:
            if manager not in managers:
                # Remove all mappings.
                keys = self.managers[manager]
                logging.info("Removing manager %s with %d keys." % (manager, len(keys)))
                for key in keys:
                    if key in self.key_to_manager:
                        del self.key_to_manager[key]
                managers_to_remove.append(manager)
        for manager in managers_to_remove:
            if manager in self.managers:
                del self.managers[manager]

        # Recompute all endpoint owners.
        for endpoint in self.endpoints.values():
            self.manager_select(endpoint)

        # Reload all managers IPs.
        self.manager_ips = \
            map(lambda x: BackendIP(x),
                self.zk_conn.list_children(paths.manager_ips()))

        # Kick the loadbalancer.
        self.reload_loadbalancer()

    @locked
    def create_endpoint(self, endpoint_name):
        logging.info("New endpoint %s found to be managed." % endpoint_name)

        # Create the object.
        # NOTE: We create all endpoints on this manager with the current
        # manager config. This means that all manager keys will be inherited
        # and you can set some sensible defaults either in the local manager
        # configuration or in the global configuration. 
        # This does mean however, that the ManagerConfig and EndpointConfig
        # should have disjoint sections for the most part.
        endpoint = Endpoint(endpoint_name, str(self.config), self)
        self.add_endpoint(endpoint)

    @locked
    def add_endpoint(self, endpoint):
        self.endpoints[endpoint.name] = endpoint
        endpoint_key = endpoint.key()

        if not(self.key_to_endpoints.has_key(endpoint.key())):
                self.key_to_endpoints[endpoint.key()] = []
        if not(endpoint.name in self.key_to_endpoints[endpoint.key()]):
            self.key_to_endpoints[endpoint.key()].append(endpoint.name)

        def local_lock(fn):
            def wrapped_fn(*args, **kwargs):
                try:
                    self.cond.acquire()
                    return fn(*args, **kwargs)
                finally:
                    self.cond.release()
            return wrapped_fn

        @local_lock
        def update_state(value):
            endpoint.update_state(value)
            if self.endpoint_owned(endpoint):
                endpoint.update()

        @local_lock
        def update_config(value):
            endpoint.update_config(value)
            if self.endpoint_owned(endpoint):
                endpoint.update()

        @local_lock
        def update_confirmed(ips):
            if ips:
                self.confirmed[endpoint.name] = ips
            elif endpoint.name in self.confirmed:
                del self.confirmed[endpoint.name]

            # Kick off a loadbalancer update.
            self.update_loadbalancer(endpoint)

        # Watch the config for this endpoint.
        logging.info("Watching endpoint %s." % (endpoint.name))
        update_state(
            self.zk_conn.watch_contents(paths.endpoint_state(endpoint.name),
                                        update_state, '',
                                        clean=True))
        update_config(
            self.zk_conn.watch_contents(paths.endpoint(endpoint.name),
                                        update_config, '',
                                        clean=True))

        # Select the manager for this endpoint.
        self.manager_select(endpoint)

        # Update the loadbalancer for this endpoint.
        update_confirmed(
            self.zk_conn.watch_children(paths.confirmed_ips(endpoint.name),
                                        update_confirmed,
                                        clean=True))

    @locked
    def start_endpoint(self, endpoint):
        # This endpoint is now being managed by us.
        endpoint.manage()
        endpoint.update()

    @locked
    def remove_endpoint(self, endpoint_name, unmanage=False):
        """
        This removes / unmanages the endpoint.
        """
        logging.info("Removing endpoint %s from manager %s" % (endpoint_name, self.uuid))
        endpoint = self.endpoints.get(endpoint_name, None)

        if endpoint:
            self.zk_conn.clear_watch_path(paths.endpoint_state(endpoint.name))
            self.zk_conn.clear_watch_path(paths.endpoint(endpoint.name))
            self.zk_conn.clear_watch_path(paths.confirmed_ips(endpoint.name))

            # Update the loadbalancer for this endpoint.
            self.update_loadbalancer(endpoint, remove=True)

            logging.info("Unmanaging endpoint %s" % (endpoint_name))
            endpoint_names = self.key_to_endpoints.get(endpoint.key(), [])
            if endpoint_name in endpoint_names:
                endpoint_names.remove(endpoint_name)
                if len(endpoint_names) == 0:
                    del self.key_to_endpoints[endpoint.key()]

            # Perform a full unmanage if this is required.
            if unmanage and self.endpoint_owned(endpoint):
                endpoint.unmanage()

            self.manager_remove(endpoint)

    @locked
    def confirmed_ips(self, endpoint_name):
        """
        Returns a list of all the confirmed ips for the endpoint.
        """
        return self.confirmed.get(endpoint_name, [])

    @locked
    def active_ips(self, endpoint_name):
        """
        Returns all confirmed and static ips for the endpoint.
        """
        ips = self.confirmed.get(endpoint_name, [])
        if endpoint_name in self.endpoints:
            ips += self.endpoints[endpoint_name].static_addresses()

        # Make sure that we return a unique set.
        return list(set(ips))

    @locked
    def drop_ip(self, endpoint_name, ip):
        logging.info("Dropping endpoint %s IP %s" % (endpoint_name, ip))
        self.zk_conn.delete(paths.endpoint_ip_metrics(endpoint_name, ip))
        self.zk_conn.delete(paths.confirmed_ip(endpoint_name, ip))
        self.zk_conn.delete(paths.ip_address(ip))
        for name in self.config.loadbalancer_names():
            self.zk_conn.delete(paths.loadbalancer_ip(name, ip))

    @locked
    def confirm_ip(self, endpoint_name, ip):
        logging.info("Adding endpoint %s IP %s" % (endpoint_name, ip))
        self.zk_conn.write(paths.confirmed_ip(endpoint_name, ip), "")
        self.zk_conn.write(paths.ip_address(ip), endpoint_name)

    @locked
    def update_ips(self, ips, add=True):
        if len(ips) == 0:
            return

        ip_map = {}

        for endpoint in self.endpoints.values():
            endpoint_ips = endpoint.addresses()
            endpoint_ips.extend(endpoint.static_addresses())
            for ip in endpoint_ips:
                ip_map[ip] = endpoint

        for ip in ips:
            endpoint = ip_map.get(ip, None)

            if not(endpoint):
                continue

            if add:
                self.confirm_ip(endpoint.name, ip)
            else:
                self.drop_ip(endpoint.name, ip)

    @locked
    def register_ip(self, ips):
        self.update_ips(ips, add=True)
        for ip in ips:
            self.zk_conn.delete(paths.new_ip(ip))

    @locked
    def unregister_ip(self, ips):
        self.update_ips(ips, add=False)
        for ip in ips:
            self.zk_conn.delete(paths.drop_ip(ip))

    @locked
    def collect_endpoint(self, endpoint, public_ips, private_ips, redirects):
        # Collect all availble IPs.
        for ip in self.active_ips(endpoint.name):
            ip = BackendIP(ip, endpoint.port(), endpoint.weight())
            if endpoint.public():
                public_ips.append(ip)
            else:
                private_ips.append(ip)

        # Collect all available redirects.
        redirect = endpoint.redirect()
        if redirect:
            redirects.append(redirect)

    @locked
    def collect_update_loadbalancer(self, url, names,
                                    public_ips, private_ips, redirects):

        if len(public_ips) > 0 or \
           len(private_ips) > 0 or \
           len(redirects) == 0:
            self.load_balancer.change(url,
                                      names,
                                      public_ips,
                                      self.manager_ips,
                                      private_ips)
        else:
            self.load_balancer.redirect(url,
                                        names,
                                        redirects[0],
                                        self.manager_ips)

    @locked
    def update_loadbalancer(self, endpoint, remove=False):
        public_ips = []
        private_ips = []
        redirects = []
        names = []

        # Go through all endpoints with the same keys.
        for endpoint_name in self.key_to_endpoints.get(endpoint.key(), []):
            if remove and (self.endpoints[endpoint_name] == endpoint):
                continue
            else:
                names.append(endpoint_name)
                self.collect_endpoint(
                    self.endpoints[endpoint_name],
                    public_ips, private_ips, redirects)

        self.collect_update_loadbalancer(endpoint.url(), names,
                                         public_ips, private_ips, redirects)
        self.load_balancer.save()

    @locked
    def reload_loadbalancer(self):
        self.load_balancer.clear()

        for (key, endpoint_names) in self.key_to_endpoints.items():
            public_ips = []
            private_ips = []
            names = []
            redirects = []

            for endpoint in map(lambda x: self.endpoints[x], endpoint_names):
                names.append(endpoint.name)
                self.collect_endpoint(endpoint, public_ips, private_ips, redirects)
            self.collect_update_loadbalancer(endpoint.url(), names,
                                             public_ips, private_ips, redirects)

        self.load_balancer.save()

    @locked
    def reload_domain(self, domain):
        self.domain = domain or NODOMAIN
        self.reload_loadbalancer()

    @locked
    def start_params(self, endpoint=None):
        # FIXME: If the user is running the Pancake server manually, then there
        # is no real way to pass in a valid set of start parameters here. This
        # should be extracted and implemented in a more flexible way at some
        # point down the road.
        return {}

    @locked
    def marked_instances(self, endpoint_name):
        """ Return a list of all the marked instances. """
        marked_instances = self.zk_conn.list_children(paths.marked_instances(endpoint_name))
        if marked_instances == None:
            marked_instances = []
        return marked_instances

    @locked
    def mark_instance(self, endpoint_name, instance_id, label):
        # Increment the mark counter.
        remove_instance = False
        mark_counters = \
                self.zk_conn.read(paths.marked_instance(endpoint_name, instance_id), '{}')
        mark_counters = json.loads(mark_counters)
        mark_counter = mark_counters.get(label, 0)
        mark_counter += 1

        if mark_counter >= self.config.mark_maximum(label):
            # This instance has been marked too many times. There is likely
            # something really wrong with it, so we'll clean it up.
            logging.warning("Instance %s for endpoint %s has been marked too many times and"
                         " will be removed. (count=%s)" % (instance_id, endpoint_name, mark_counter))
            remove_instance = True
            self.zk_conn.delete(paths.marked_instance(endpoint_name, instance_id))

        else:
            # Just save the mark counter.
            logging.info("Instance %s for endpoint %s has been marked (count=%s)" %
                         (instance_id, endpoint_name, mark_counter))
            mark_counters[label] = mark_counter
            self.zk_conn.write(paths.marked_instance(endpoint_name, instance_id),
                               json.dumps(mark_counters))

        return remove_instance

    @locked
    def drop_marked_instance(self, endpoint_name, instance_id):
        """ Delete the marked instance data. """
        self.zk_conn.delete(paths.marked_instance(endpoint_name, instance_id))

    @locked
    def decommission_instance(self, endpoint_name, instance_id, ip_addresses):
        """ Mark the instance id as being decommissioned. """
        for ip_address in ip_addresses:
            self.zk_conn.delete(paths.confirmed_ip(endpoint_name, ip_address))
        self.zk_conn.write(paths.decommissioned_instance(endpoint_name, instance_id),
                           json.dumps(ip_addresses))

    @locked
    def decommissioned_instances(self, endpoint_name):
        """ Return a list of all the decommissioned instances. """
        decommissioned_instances = self.zk_conn.list_children(\
            paths.decommissioned_instances(endpoint_name))
        if decommissioned_instances == None:
            decommissioned_instances = []
        return decommissioned_instances

    @locked
    def decomissioned_instance_ip_addresses(self, endpoint_name, instance_id):
        """ Return the ip address of a decomissioned instance. """
        ip_addresses = self.zk_conn.read(paths.decommissioned_instance(endpoint_name, instance_id))
        if ip_addresses != None:
            ip_addresses = json.loads(ip_addresses)
            if type(ip_addresses) == str:
                ip_addresses = [ip_addresses]
        else:
            ip_addresses = []
        return ip_addresses

    @locked
    def drop_decommissioned_instance(self, endpoint_name, instance_id):
        """ Delete the decommissioned instance """
        ip_addresses = self.decomissioned_instance_ip_addresses(endpoint_name, instance_id)
        for ip_address in ip_addresses:
            self.drop_ip(endpoint_name, ip_address)
        self.zk_conn.delete(paths.decommissioned_instance(endpoint_name, instance_id))

    def metric_indicates_active(self, metrics):
        """ Returns true if the metrics indicate that there are active connections. """
        active_metrics = metrics.get("active", (0, 0))
        try:
            return active_metrics[1] > 0
        except:
            # The active metric is defined but as a bad form.
            logging.warning("Malformed metrics found: %s" % (active_metrics))
            return False

    @locked
    def update_metrics(self):
        """ 
        Collects the metrics from the loadbalancer, updates zookeeper and then collects
        the metrics posted by other managers.
        
        returns a tuple (metrics, active_connections) both of which are dictionaries. Metrics
        is indexed by the endpoint key and active connections is indexed by endpoint name
        """

        # Update all the endpoint metrics from the loadbalancer.
        metrics = self.load_balancer.metrics()
        logging.debug("Load balancer returned metrics: %s" % metrics)

        # The metrics_by_key dictionary maps to a tuple (active, metrics).
        # The active value is a list of all IPs used to generate the metrics.
        # That is to say, if one or more of the value was used in to generate
        # the aggregated metrics that corresponds to that IP then it will be
        # present in the active set.
        metrics_by_key = {}
        active_connections = {}

        for ip in metrics:
            for endpoint in self.endpoints.values():

                if not(endpoint.key() in metrics_by_key):
                    metrics_by_key[endpoint.key()] = ([], [])
                if not(endpoint.name in active_connections):
                    active_connections[endpoint.name] = []

                endpoint_ips = self.active_ips(endpoint.name)
                if ip in endpoint_ips:
                    metrics_by_key[endpoint.key()][0].append(ip)
                    metrics_by_key[endpoint.key()][1].append(metrics[ip])

                    if self.metric_indicates_active(metrics[ip]):
                        active_connections[endpoint.name].append(ip)

        # Stuff all the metrics into Zookeeper.
        self.zk_conn.write(paths.manager_metrics(self.uuid), \
                           json.dumps(metrics_by_key), \
                           ephemeral=True)
        self.zk_conn.write(paths.manager_active_connections(self.uuid), \
                           json.dumps(active_connections), \
                           ephemeral=True)

        # Load all metrics (from other managers).
        all_metrics = {}

        # A listing of all the active connections.
        all_active_connections = {}

        # Read the keys for all other managers.
        for manager in self.managers:
            # Skip re-reading the local metrics.
            if manager == self.uuid:
                manager_metrics = metrics_by_key
                manager_active_connections = active_connections
            else:
                manager_metrics = self.zk_conn.read(paths.manager_metrics(manager), "{}")
                manager_metrics = json.loads(manager_metrics)
                manager_active_connections = \
                        self.zk_conn.read(paths.manager_active_connections(manager), "{}")
                manager_active_connections = json.loads(manager_active_connections)

            # Merge into the all_metrics dictionary.
            for key in manager_metrics:
                if not(key in all_metrics):
                    all_metrics[key] = ([], [])

                all_metrics[key][0].extend(manager_metrics[key][0])
                all_metrics[key][1].extend(manager_metrics[key][1])

            # Merge all the active connection counts.
            for endpoint_name in manager_active_connections:
                if not(endpoint_name in all_active_connections):
                    all_active_connections[endpoint_name] = []

                all_active_connections[endpoint_name].extend(\
                        manager_active_connections[endpoint_name])

        # Return all available global metrics.
        return (all_metrics, all_active_connections)

    @locked
    def load_metrics(self, endpoint, endpoint_metrics={}):
        """ 
        Load the particular metrics for a endpoint and return
        a tuple (metrics, active_connections) where metrics
        are the metrics to use for the endpoint and active_connections
        is a list of ip addresses with active connections.
        """

        # Read any default metrics. We can override the source endpoint for
        # metrics here (so, for example, a backend database server can inheret
        # a set of metrics given for the front server).  This, like many other
        # things, is specified here by the name of the endpoint we are
        # inheriting metrics for. If not given, we default to the current
        # endpoint.
        source_key = endpoint.source_key()
        if source_key:
            (metric_ips, metrics) = endpoint_metrics.get(source_key, ([], []))
        else:
            (metric_ips, metrics) = endpoint_metrics.get(endpoint.key(), ([], []))

        default_metrics = self.zk_conn.read(paths.endpoint_custom_metrics(endpoint.name))
        if default_metrics:
            try:
                # This should be a dictionary { "name" : (weight, value) }
                metrics.append(json.loads(default_metrics))
            except ValueError:
                logging.warn("Invalid custom metrics for %s." % (endpoint.name))

        # Read other metrics for given hosts.
        active_connections = []
        for ip_address in self.active_ips(endpoint.name):
            ip_metrics = self.zk_conn.read(paths.endpoint_ip_metrics(endpoint.name, ip_address))
            if ip_metrics:
                try:
                    # This should be a dictionary { "name" : (weight, value) }
                    ip_metrics = json.loads(ip_metrics)
                    metrics.append(ip_metrics)
                    if not ip_address in metric_ips:
                        metric_ips.append(ip_address)
                    if self.metric_indicates_active(ip_metrics):
                        active_connections.append(ip_address)
                except ValueError:
                    logging.warn("Invalid instance metrics for %s:%s." % \
                                 (endpoint.name, ip_address))

        for instance_id in self.decommissioned_instances(endpoint.name):
            # Also check the metrics of decommissioned instances looking for any active counts.
            for ip_address in self.decomissioned_instance_ip_addresses(endpoint.name, instance_id):
                if ip_address:
                    ip_metrics = self.zk_conn.read(paths.endpoint_ip_metrics(endpoint.name, ip_address))
                    if ip_metrics:
                        try:
                            # As above, this should be a dictionary.
                            ip_metrics = json.loads(ip_metrics)
                            metrics.append(ip_metrics)
                            if not ip_address in metric_ips:
                                metric_ips.append(ip_address)
                            if self.metric_indicates_active(ip_metrics):
                                active_connections.append(ip_address)
                        except ValueError:
                            logging.warn("Invalid instance metrics for %s:%s." % \
                                         (endpoint.name, ip_address))

        # Return the metrics.
        return metrics, list(set(metric_ips)), active_connections

    @locked
    def health_check(self):
        # Save and load the current metrics.
        endpoint_metrics, active_connections = self.update_metrics()

        # Does a health check on all the endpoints that are being managed.
        for endpoint in self.endpoints.values():
            # Do not kick the endpoint if it is not currently owned by us.
            if not(self.endpoint_owned(endpoint)):
                continue

            try:
                metrics, metric_ips, endpoint_connections = \
                    self.load_metrics(endpoint, endpoint_metrics)

                # Compute the active set (including custom metrics, etc.).
                active = active_connections.get(endpoint.name, [])
                active.extend(endpoint_connections)
                active = list(set(active))

                # Compute the globally weighted averages.
                metrics = calculate_weighted_averages(metrics)

                # Update the live metrics and connections.
                logging.debug("Metrics for endpoint %s from %s: %s" % \
                              (endpoint.name, str(metric_ips), metrics))
                self.zk_conn.write(paths.endpoint_live_metrics(endpoint.name), \
                                   json.dumps(metrics), \
                                   ephemeral=True)
                self.zk_conn.write(paths.endpoint_live_active(endpoint.name), \
                                   json.dumps(active), \
                                   ephemeral=True)

                # Run a health check on this endpoint.
                endpoint.health_check(active)

                # Do the endpoint update.
                endpoint.update(reconfigure=False, metrics=metrics, metric_instances=len(metric_ips))
            except:
                error = traceback.format_exc()
                logging.error("Error updating endpoint %s: %s" % (endpoint.name, error))

    def run(self):
        # Note that we are running.
        self.running = True

        while self.running:
            try:
                # Reconnect to the Zookeeper servers.
                self.serve()

                # Perform continuous health checks.
                while self.running:
                    self.health_check()
                    if self.running:
                        time.sleep(self.config.health_check())

            except ZookeeperException:
                # Sleep on ZooKeeper exception and retry.
                error = traceback.format_exc()
                logging.debug("Received ZooKeeper exception, retrying: %s" % (error))
                if self.running:
                    time.sleep(self.config.health_check())

    def clean_stop(self):
        self.running = False
