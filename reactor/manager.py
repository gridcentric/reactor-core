import logging
import threading
import time
import uuid
import hashlib
import bisect
import json
import traceback
import socket
import binascii
import array
from StringIO import StringIO

from reactor.config import Config
from reactor.config import fromini

import reactor.submodules as submodules

from reactor.endpoint import Endpoint
from reactor.endpoint import State

import reactor.loadbalancer.connection as lb_connection
from reactor.loadbalancer.connection import BackendIP
import reactor.cloud.connection as cloud_connection

from reactor.zookeeper.connection import ZookeeperConnection
from reactor.zookeeper.connection import ZookeeperException
import reactor.zookeeper.paths as paths

from reactor.metrics.calculator import calculate_weighted_averages

class ManagerConfig(Config):

    def __init__(self, **kwargs):
        Config.__init__(self, "manager", **kwargs)

    ips = Config.list(label="Additional IPs", order=1,
        description="Floating or public IPs.")

    loadbalancers = Config.multiselect(label="Enabled Loadbalancer Drivers", order=1,
        options=submodules.loadbalancer_options(),
        default=submodules.loadbalancer_submodules(),
        description="List of supported loadbalancers (e.g. nginx).")

    clouds = Config.multiselect(label="Enabled Cloud Drivers", order=1,
        options=submodules.cloud_options(),
        default=submodules.cloud_submodules(),
        description="List of supported clouds (e.g. osapi).")

    health_check = Config.integer(label="Health Check Interval (seconds)", default=5, order=1,
        validate=lambda self: self.health_check > 0 or \
            Config.error("Health_check must be positive."),
        description="Period for decomissioning and timing out instances.")

    marks = Config.integer(label="Maximum Failed Health Checks",
        default=36, order=2,
        validate=lambda self: self.marks > 0 or \
            Config.error("Marks must be positive."),
        description="Timeout for unregistered and decomissioned VMs.")

    keys = Config.integer(label="Keys per Manager", default=64, order=2,
        validate=lambda self: self.keys >= 0 or \
            Config.error("Keys must be non-negative."),
        description="Key count for managing services on the ring.")

def locked(fn):
    """
    IMPORTANT: There is a potential deadlock if the manager is locked when setting / clearing
    a zookeeper watch. Our policy is that the manager cannot be locked when it makes a call
    to one of the zookeeper client's watch functions. Note to check the full call chain to
    ensure that a higher level function is not setting the lock.
    """
    def wrapped_fn(self, *args, **kwargs):
        try:
            self.cond.acquire()
            return fn(self, *args, **kwargs)
        finally:
            self.cond.release()
    wrapped_fn.__name__ = fn.__name__
    wrapped_fn.__doc__ = fn.__doc__
    return wrapped_fn

class ScaleManager(object):

    def __init__(self, zk_servers, names=[]):

        self.names      = names
        self.zk_servers = zk_servers
        self.zk_conn    = None
        self.running    = False
        self.cond       = threading.Condition()
        self.uuid       = str(uuid.uuid4()) # Manager uuid (generated).

        self.health_check = 5  # Health check interval.
        self.marks        = 10 # Mark interval.

        self.endpoints = {}        # Endpoint map (name -> endpoint)
        self.key_to_endpoints = {} # Endpoint map (key() -> [names...])
        self.confirmed = {}        # Endpoint map (name -> confirmed IPs)

        self.managers = {}        # Forward map of manager keys.
        self.manager_ips = []     # List of all manager IPs.
        self.registered_ips = []  # List of registered IPs.
        self.manager_keys = []    # Our local manager keys.
        self.key_to_manager = {}  # Reverse map for manager keys.
        self.key_to_owned = {}    # Endpoint to ownership.

        self.loadbalancers = {}   # Load balancer connections.
        self.locks = {}           # Load balancer locks.
        self.clouds = {}          # Cloud connections.

        self.manager_sessions = {} # Client sessions owned by this manager

        # Setup logging.
        self.log = self.setup_logging()

    @locked
    def _connect_to_zookeeper(self):
        # Create a Zookeeper connection.
        if self.zk_conn:
            self.zk_conn.close()
        self.zk_conn = ZookeeperConnection(self.zk_servers)

    @locked
    def setup_logging(self):
        """ Add an in-memory log that can be polled remotely. """
        log_buffer = StringIO()
        logger = logging.getLogger()
        formatter = logging.Formatter('%(asctime)s [%(thread)d] %(levelname)s %(name)s: %(message)s')
        handler = logging.StreamHandler(log_buffer)
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        return log_buffer

    def serve(self):
        self._connect_to_zookeeper()

        # Load our configuration and register ourselves.
        self.manager_register()

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

    def endpoint_change(self, endpoints):
        logging.info("Endpoints have changed: new=%s, existing=%s" %
                     (endpoints, self.endpoints.keys()))

        for endpoint_name in endpoints:
            if endpoint_name not in self.endpoints:
                self.create_endpoint(endpoint_name)

        known_endpoint_names = self.endpoints.keys()
        for endpoint_name in known_endpoint_names:
            if endpoint_name not in endpoints:
                self.remove_endpoint(endpoint_name, unmanage=True)

    def update_config(self, config):
        self.manager_register(config=config)
        for endpoint in self.endpoints.values():
            endpoint.update_loadbalancer()

    def _endpoint_config_spec(self):
        """ Return the specification for a configured endpoint. """
        config = Config()
        Endpoint.spec_config(config)
        for lb in self.loadbalancers.values():
            lb._endpoint_config(config=config)
        for cloud in self.clouds.values():
            cloud._endpoint_config(config=config)
        return config._spec()

    def _endpoint_config_validate(self, name, values):
        """ Validate a given endpoint configuration. """
        config = Config(values=values)
        endpoint = self.endpoints.get(name, None)
        if endpoint:
            endpoint.validate_config(config, self.clouds, self.loadbalancers)
        for lb in self.loadbalancers.values():
            lb._endpoint_config(config=config)._validate()
        return config._validate_errors()

    def _manager_config_spec(self):
        """ Return the specification for a configured manager. """
        config = Config()
        ManagerConfig(obj=config)
        for lb in self.loadbalancers.values():
            lb._manager_config(config=config)
        for cloud in self.clouds.values():
            cloud._manager_config(config=config)
        return config._spec()

    def _manager_config_validate(self, values):
        """ Validate a given manager configuration. """
        config = Config(values=values)
        ManagerConfig(obj=config)._validate()
        for lb in self.loadbalancers.values():
            lb._manager_config(config=config)._validate()
        for cloud in self.clouds.values():
            cloud._manager_config(config=config)._validate()
        return config._validate_errors()

    def _configure(self, config=None):
        """
        This setups up the base manager configuration by combining
        the global configuration and config_str into a single configuration.
        """
        # Clear out the old watch.
        self.zk_conn.clear_watch_fn(self.update_config)

        # Load our given configuration.
        # This instantiates the manager class and builds the config
        # object. We will augment this configuration once we load the
        # loadbalancers and cloud connections.
        spec = self._manager_config_spec()
        manager_config = ManagerConfig(obj=spec, values=config)

        # NOTE: We may have multiple global IPs (especially in the case of
        # provisioning a cluster that could have floating IPs that move around.
        # We read in each of the configuration blocks in turn, and hope that
        # they are not somehow mutually incompatible.
        configured_ips = None
        if self.names:
            def load_ip_config(ip):
                # Reload our local config.
                manager_config._update(self.zk_conn.watch_contents(
                                        paths.manager_config(ip),
                                        self.update_config))

            # Read all configured IPs.
            for ip in self.names:
                load_ip_config(ip)
            configured_ips = manager_config.ips
            for ip in configured_ips:
                load_ip_config(ip)

        # Load the loadbalancer and cloud connections.
        self._setup_loadbalancer_connections(manager_config)
        self._setup_cloud_connections(manager_config)

        return manager_config

    @locked
    def _register_manager_ips(self, configured_ips):
        """
        Register all of the manager's configured ips.
        """
        # We remove all existing registered IPs.
        for ip in self.registered_ips:
            if self.zk_conn.read(paths.manager_ip(ip)) == self.uuid:
                logging.info("Clearing IP '%s'." % ip)
                self.zk_conn.delete(paths.manager_ip(ip))
        self.registered_ips = []

        if self.names:
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

    @locked
    def _determine_manager_keys(self, key_num):
        # Generate keys.
        while len(self.manager_keys) < key_num:
            # Generate a random hash key to associate with this manager.
            self.manager_keys.append(hashlib.md5(str(uuid.uuid4())).hexdigest())
        while len(self.manager_keys) > key_num:
            # Drop keys while we're too high.
            del self.manager_keys[len(self.manager_keys) - 1]

        # Write out our associated hash keys as an ephemeral node.
        key_string = ",".join(self.manager_keys)
        self.zk_conn.write(paths.manager_keys(self.uuid), key_string, ephemeral=True)
        logging.info("Generated %d keys." % len(self.manager_keys))

    @locked
    def _select_endpoints(self):
        # If we're not doing initial setup, refresh endpoints.
        for endpoint in self.endpoints.values():
            self.manager_select(endpoint)

    @locked
    def _setup_loadbalancer_connections(self, config):
        # Create the loadbalancer connections.
        # NOTE: Any old loadbalancer object should be cleaned
        # up automatically (i.e. the objects should implement
        # fairly sensible __del__ methods when necessary).
        self.loadbalancers = {}
        for name in config.loadbalancers:
            # Ensure that we have locks for this loadbalancer.
            if not name in self.locks:
                self.locks[name] = lb_connection.Locks(name, scale_manager=self)

            # Create the load balancer itself.
            self.loadbalancers[name] = \
                lb_connection.get_connection( \
                    name, config=config, locks=self.locks[name])

    @locked
    def _find_loadbalancer_connection(self, name=None):
        # Try to find a matching loadbalancer connection, or return an unconfigured stub.
        return self.loadbalancers.get(name, lb_connection.LoadBalancerConnection(name))

    @locked
    def _setup_cloud_connections(self, config):
        # Create the cloud connections.
        # NOTE: Same restrictions apply to cloud connections.
        self.clouds = {}
        for name in config.clouds:
            self.clouds[name] = \
                cloud_connection.get_connection( \
                    name, config=config)

    @locked
    def _find_cloud_connection(self, name=None):
        # Try to find a matching cloud connection, or return an unconfigured stub.
        return self.clouds.get(name, cloud_connection.CloudConnection(name))

    def manager_register(self, config=None):
        # Figure out our global IPs.
        logging.info("Manager %s has key %s." % (str(self.names), self.uuid))

        # Configure and load connections.
        manager_config = self._configure(config)
        self._register_manager_ips(manager_config.ips)
        self._determine_manager_keys(manager_config.keys)
        self._select_endpoints()

        # Initialize health check variables
        self.marks = manager_config.marks
        self.health_check = manager_config.health_check

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

        # Recompute all endpoint owners and update loadbalancers
        for endpoint in self.endpoints.values():
            self.manager_select(endpoint)
            endpoint.update_loadbalancer()

        # Reload all managers IPs.
        self.manager_ips = \
            map(lambda x: BackendIP(x),
                self.zk_conn.list_children(paths.manager_ips()))

    def create_endpoint(self, endpoint_name):
        logging.info("New endpoint %s found to be managed." % endpoint_name)

        # Create the object.
        # NOTE: We create all endpoints on this manager with the current
        # manager config. This means that all manager keys will be inherited
        # and you can set some sensible defaults either in the local manager
        # configuration or in the global configuration.
        # This does mean however, that the ManagerConfig and EndpointConfig
        # should have disjoint sections for the most part.
        endpoint = Endpoint(endpoint_name, self)
        self.add_endpoint(endpoint)

    @locked
    def _add_endpoint(self, endpoint):
        self.endpoints[endpoint.name] = endpoint
        endpoint_key = endpoint.key()

        if not(self.key_to_endpoints.has_key(endpoint_key)):
                self.key_to_endpoints[endpoint_key] = []

        if not(endpoint.name in self.key_to_endpoints[endpoint_key]):
            self.key_to_endpoints[endpoint_key].append(endpoint.name)

    def add_endpoint(self, endpoint):

        self._add_endpoint(endpoint)

        def local_lock(fn):
            def wrapped_fn(*args, **kwargs):
                try:
                    self.cond.acquire()
                    return fn(*args, **kwargs)
                finally:
                    self.cond.release()
            wrapped_fn.__name__ = fn.__name__
            wrapped_fn.__doc__ = fn.__doc__
            return wrapped_fn

        @local_lock
        def update_state(value):
            endpoint.update_state(value)
            if self.endpoint_owned(endpoint):
                endpoint.update()

        @local_lock
        def update_config(config):
            config = Config(obj=self._endpoint_config_spec(), values=config)
            endpoint.update_config(config)
            if self.endpoint_owned(endpoint):
                endpoint.update()

        @local_lock
        def update_confirmed(ips):
            if ips:
                self.confirmed[endpoint.name] = ips
            elif endpoint.name in self.confirmed:
                del self.confirmed[endpoint.name]

            # Kick off a loadbalancer update.
            endpoint.update_loadbalancer()

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
    def _remove_endpoint(self, endpoint, unmanage):

        endpoint_name = endpoint.name
        logging.info("Unmanaging endpoint %s" % (endpoint_name))
        endpoint_names = self.key_to_endpoints.get(endpoint.key(), [])
        if endpoint_name in endpoint_names:
            endpoint_names.remove(endpoint_name)
            if len(endpoint_names) == 0:
                del self.key_to_endpoints[endpoint.key()]

        # Perform a full unmanage if this is required.
        if unmanage and self.endpoint_owned(endpoint):
            endpoint.unmanage()

        del self.endpoints[endpoint_name]

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
            endpoint.update_loadbalancer(remove=True)
            self._remove_endpoint(endpoint, unmanage)
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
        for lock in self.locks.values():
            lock.forget_ip(ip)
        self.endpoints[endpoint_name].ip_dropped(ip)

    @locked
    def confirm_ip(self, endpoint_name, ip):
        logging.info("Adding endpoint %s IP %s" % (endpoint_name, ip))
        self.zk_conn.write(paths.confirmed_ip(endpoint_name, ip), "")
        self.zk_conn.write(paths.ip_address(ip), endpoint_name)
        self.endpoints[endpoint_name].ip_confirmed(ip)

    def ip_to_endpoint(self, ip):
        return self.zk_conn.read(paths.ip_address(ip))

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
    def collect_endpoint(self, endpoint):
        ips = []
        redirects = []

        # Collect all availble IPs.
        for ip in self.active_ips(endpoint.name):
            ip = BackendIP(ip, endpoint.port(), endpoint.weight())
            ips.append(ip)

        # Collect all available redirects.
        redirect = endpoint.redirect()
        if redirect:
            redirects.append(redirect)

        return (ips, redirects)

    def endpoint_instances(self, endpoint_name):
        """ Return a list of all endpoint instances. """
        instances = self.zk_conn.list_children(paths.endpoint_instances(endpoint_name))
        if instances == None:
            instances = []
        return instances

    def add_endpoint_instance(self, endpoint_name, instance_id, data=''):
        self.zk_conn.write(paths.endpoint_instance(endpoint_name, instance_id), data)

    def get_endpoint_instance(self, endpoint_name, instance_id):
        return self.zk_conn.read(paths.endpoint_instance(endpoint_name, instance_id))

    def delete_endpoint_instance(self, endpoint_name, instance_id):
        self.zk_conn.delete(paths.endpoint_instance(endpoint_name, instance_id))

    def endpoint_sessions(self, endpoint_name):
        """ Return a mapping of endpoint sessions. """
        clients = self.zk_conn.list_children(paths.endpoint_sessions(endpoint_name))
        if not clients:
            return {}
        session_map = {}
        for client in clients:
            backend = self.zk_conn.read(paths.endpoint_session(endpoint_name, client))
            backend_sessions = session_map.get(backend, [])
            backend_sessions.append(client)
            session_map[backend] = backend_sessions
        return session_map

    def endpoint_dropped_sessions(self, endpoint_name):
        """ Return a mapping of dropped endpoint sessions. """
        clients = self.zk_conn.list_children(paths.dropped_sessions(endpoint_name))
        if not clients:
            return {}
        session_map = {}
        for client in clients:
            backend = self.zk_conn.read(paths.dropped_session(endpoint_name, client))
            backend_sessions = session_map.get(backend, [])
            backend_sessions.append(client)
            session_map[backend] = backend_sessions
        return session_map

    # An indication that a session has been opened
    def session_opened(self, endpoint_name, backend, client):
        self.zk_conn.write(paths.endpoint_session(endpoint_name, client), backend)

    # An indication that a session has been closed
    def session_closed(self, endpoint_name, client):
        self.zk_conn.delete(paths.endpoint_session(endpoint_name, client))

    # An indication that a session has been dropped
    def session_dropped(self, endpoint_name, client):
        self.zk_conn.delete(paths.dropped_session(endpoint_name, client))
        self.session_closed(endpoint_name, client)

    # Indicate to the endpoint that a session should be dropped
    def drop_session(self, endpoint_name, backend, client):
        if endpoint_name in self.endpoints:
            self.zk_conn.write(paths.dropped_session(endpoint_name, client), backend)
            return True
        return False

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
        mark_counters = self.zk_conn.read(paths.marked_instance(endpoint_name, instance_id), '{}')
        mark_counters = json.loads(mark_counters)
        mark_counter = mark_counters.get(label, 0)
        mark_counter += 1

        if mark_counter >= self.marks:
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
        self.zk_conn.write(paths.decommissioned_instance(endpoint_name, instance_id),
                           json.dumps(ip_addresses))

    @locked
    def recommission_instance(self, endpoint_name, instance_id):
        """ Mark the instance id as being recommissioned. """
        # Re-register all associated IPs.
        ips = self.decommissioned_instance_ip_addresses(endpoint_name, instance_id)
        self.register_ip(ips)

        # Delete decommissioned instance path and marked data.
        self.zk_conn.delete(paths.decommissioned_instance(endpoint_name,
                            instance_id))
        self.drop_marked_instance(endpoint_name, instance_id)

    @locked
    def decommissioned_instances(self, endpoint_name):
        """ Return a list of all the decommissioned instances. """
        decommissioned_instances = self.zk_conn.list_children(\
            paths.decommissioned_instances(endpoint_name))
        if decommissioned_instances == None:
            decommissioned_instances = []
        return decommissioned_instances

    @locked
    def decommissioned_instance_ip_addresses(self, endpoint_name, instance_id):
        """ Return the ip address of a decommissioned instance. """
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
        """ Delete the decommissioned instance. """
        ip_addresses = self.decommissioned_instance_ip_addresses(endpoint_name, instance_id)
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

    def _collect_metrics(self):
        # This is the only complex metric (that requires multiplexing).  We
        # combine the load balancer metrics by hostname, adding weights where
        # they are not unique.
        results = {}
        for lb in self.loadbalancers.values():
            result = lb.metrics()
            for (host, metrics) in result.items():
                if not(host in results):
                    results[host] = metrics
                    continue

                for key in metrics:
                    (oldweight, oldvalue) = results[host].get(key, (0,0))
                    (newweight, newvalue) = metrics[key]
                    weight = (oldweight + newweight)
                    value  = ((oldvalue * oldweight) + (newvalue * newweight)) / weight
                    results[host][key] = (weight, value)

        return results

    @locked
    def start_params(self, endpoint=None):
        return {}

    @locked
    def cleanup_start_params(self, endpoint, start_params):
        pass

    @locked
    def update_metrics(self):
        """
        Collects the metrics from the loadbalancer, updates zookeeper and then collects
        the metrics posted by other managers.

        returns a tuple (metrics, active_connections) both of which are dictionaries. Metrics
        is indexed by the endpoint key and active connections is indexed by endpoint name.
        """
        metrics = self._collect_metrics()
        logging.debug("Loadbalancers returned metrics: %s" % metrics)

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
            for ip_address in self.decommissioned_instance_ip_addresses(endpoint.name, instance_id):
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

    def _collect_sessions(self):
        all_sessions = {}
        for lb in self.loadbalancers.values():
            sessions = lb.sessions() or {}
            # For each session,
            for backend in sessions:
                # Look up the endpoint
                endpoint_name = self.ip_to_endpoint(backend)
                # If no endpoint,
                if not endpoint_name:
                    # Log and continue
                    logging.error("Found session without endpoint: %s" % backend)
                    continue
                # Add to the sesssions list
                endpoint_sessions = all_sessions.get(endpoint_name, {})
                backend_sessions = endpoint_sessions.get(backend, [])
                for client in sessions[backend]:
                    backend_sessions.append(client)
                endpoint_sessions[backend] = backend_sessions
                all_sessions[endpoint_name] = endpoint_sessions

        return all_sessions

    def update_sessions(self):
        # Collect sessions
        my_sessions = self._collect_sessions()
        old_sessions = self.manager_sessions

        # Write out our sessions
        for endpoint in my_sessions:
            for backend in my_sessions[endpoint]:
                for client in my_sessions[endpoint][backend]:
                    self.session_opened(endpoint, backend, client)

        # Cull old sessions
        for endpoint in old_sessions:
            for backend in old_sessions[endpoint]:
                for client in old_sessions[endpoint][backend]:
                    if client not in my_sessions.get(endpoint, {}).get(backend, []):
                        self.session_closed(endpoint, client)
        self.manager_sessions = my_sessions

        # Read sessions from all managers
        all_sessions = {}
        dropped_sessions = {}
        for endpoint in self.endpoints:
            all_sessions[endpoint] = self.endpoint_sessions(endpoint)
            dropped_sessions[endpoint] = self.endpoint_dropped_sessions(endpoint)

        return (all_sessions, dropped_sessions)

    @locked
    def do_health_check(self):
        # Save and load the current metrics.
        endpoint_metrics, active_connections = self.update_metrics()
        all_sessions, dropped_sessions = self.update_sessions()

        # Does a health check on all the endpoints that are being managed.
        for endpoint in self.endpoints.values():
            # Check ownership
            owned = self.endpoint_owned(endpoint)

            # Update endpoint sessions
            endpoint_sessions = all_sessions[endpoint.name]
            endpoint_dropped_sessions = dropped_sessions[endpoint.name]
            endpoint.update_sessions(endpoint_sessions,
                                     endpoint_dropped_sessions, owned)

            # Do not kick the endpoint if it is not currently owned by us.
            if not(owned):
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
                endpoint.update(reconfigure=False, metrics=metrics,
                                metric_instances=len(metric_ips),
                                active_ips=active)
            except:
                error = traceback.format_exc()
                logging.error("Error updating endpoint %s: %s" % (endpoint.name, error))

        try:
            # Try updating our logs.
            self.zk_conn.write(paths.manager_log(self.uuid), self.log.getvalue(), ephemeral=True)
        except:
            error = traceback.format_exc()
            logging.error("Error saving logs: %s" % error)

        # Reset the buffer.
        self.log.truncate(0)

    def endpoint_log_load(self, endpoint_name):
        data = self.zk_conn.read(paths.endpoint_log(endpoint_name))
        if data:
            try:
                data = array.array('b', binascii.unhexlify(data))
            except:
                data = None
        return data

    def endpoint_log_save(self, endpoint_name, data):
        self.zk_conn.write(paths.endpoint_log(endpoint_name),
                           binascii.hexlify(data))

    def run(self):
        # Note that we are running.
        self.running = True

        while self.running:
            try:
                # Reconnect to the Zookeeper servers.
                self.serve()

                # Perform continuous health checks.
                while self.running:
                    self.do_health_check()
                    if self.running:
                        time.sleep(self.health_check)

            except ZookeeperException:
                # Sleep on ZooKeeper exception and retry.
                error = traceback.format_exc()
                logging.debug("Received ZooKeeper exception, retrying: %s" % (error))
                if self.running:
                    time.sleep(self.health_check)

    def clean_stop(self):
        self.running = False
