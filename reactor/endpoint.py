import hashlib
import logging
import traceback
import socket
import sys
import copy

from reactor.binlog import BinaryLog, BinaryLogRecord
from reactor.config import Config
from reactor.submodules import cloud_options, loadbalancer_options
from reactor.utils import inet_ntoa, inet_aton
import reactor.cloud.connection as cloud_connection
import reactor.loadbalancer.connection as lb_connection
import reactor.metrics.calculator as metric_calculator

def compute_key(url):
    return hashlib.md5(url).hexdigest()

class State:
    running = "RUNNING"
    stopped = "STOPPED"
    paused  = "PAUSED"
    default = stopped

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

class EndpointConfig(Config):

    def __init__(self, **kwargs):
        Config.__init__(self, section="endpoint", **kwargs)

    url = Config.string(label="Endpoint URL", order=0,
        description="The URL for this endpoint.")

    port = Config.integer(label="Backend Port", order=1,
        validate=lambda self: self.port >= 0 or \
            Config.error("Port must be non-negative."),
        description="The backend port for this service.")

    redirect = Config.string(label="Fallback URL", order=1,
        description="A redirect URL for when no instances are available.")

    weight = Config.integer(label="Weight", default=1, order=1,
        validate=lambda self: self.weight >= 0 or \
            Config.error("Weight must be non-negative."),
        description="Relative weight (if more than one endpoint exists for this URL).")

    cloud = Config.select(label="Cloud Driver", order=2,
        options=cloud_options(),
        description="The cloud platform used by this endpoint.")

    loadbalancer = Config.select(label="Loadbalancer Driver", order=2,
        options=loadbalancer_options(),
        description="The loadbalancer for this endpoint.")

    auth_hash = Config.string(label="Auth Hash Token", default=None, order=3,
        description="The authentication token for this endpoint.")

    auth_salt = Config.string(label="Auth Hash Salt", default="", order=3,
        description="The salt used for computing authentication tokens.")

    auth_algo = Config.string(label="Auth Hash Algorithm", default="sha1", order=3,
        validate=lambda self: hashlib.new(self.auth_algo, ''),
        description="The algorithm used for computing authentication tokens.")

    def _get_endpoint_auth(self):
        return (self.auth_hash, self.auth_salt, self.auth_algo)

    static_instances = Config.list(label="Static Backends", order=1,
        validate=lambda self: self._static_ips(validate=True),
        description="Static hosts for the endpoint.")

    def _static_ips(self, validate=False):
        """ Returns a list of static ips associated with the configured static instances. """
        static_instances = self.static_instances

        # (dscannell) The static instances can be specified either as IP
        # addresses or hostname.  If its an IP address then we are done. If its
        # a hostname then we need to do a lookup to determine its IP address.
        ip_addresses = []
        for static_instance in static_instances:
            try:
                if static_instance != '':
                    ip_addresses += [socket.gethostbyname(static_instance)]
            except:
                logging.warn("Failed to determine the ip address "
                             "for the static instance %s." % static_instance)
                if validate:
                    raise
        return ip_addresses

class ScalingConfig(Config):

    def __init__(self, **kwargs):
        Config.__init__(self, "scaling", **kwargs)

    min_instances = Config.integer(label="Minimum Instances", default=1, order=0,
        validate=lambda self: (self.min_instances >= 1 or \
            Config.error("Min instances must be at least one.")) and \
            (self.max_instances >= self.min_instances or \
            Config.error("Min instances (%d) must be less than Max instances (%d)" % \
                (self.min_instances, self.max_instances))),
        description="Lower limit on dynamic instances.")

    max_instances = Config.integer(label="Maximum Instances", default=1, order=1,
        validate=lambda self: (self.max_instances >= 1 or \
            Config.error("Max instances must be at least one.")) and \
            (self.max_instances >= self.min_instances or \
            Config.error("Min instances (%d) must be less than Max instances (%d)" % \
                (self.min_instances, self.max_instances))),
        description="Upper limit on dynamic instances.")

    rules = Config.list(label="Scaling Rules", order=1,
        validate=lambda self: \
            [metric_calculator.EndpointCriteria.validate(x) for x in self.rules],
        description="List of scaling rules (e.g. 0.5<active<0.8).")

    ramp_limit = Config.integer(label="Ramp Limit", default=5, order=2,
        validate=lambda self: self.ramp_limit > 0 or \
            Config.error("Ramp limit must be positive."),
        description="The maximum operations (start and stop instances) per round.")

    url = Config.string(label="Metrics URL", order=3,
        description="The source url for metrics.")

class EndpointLog(BinaryLog):
    # Log entry types.
    ENDPOINT_STARTED        = BinaryLogRecord(lambda args: "Endpoint marked as Started")
    ENDPOINT_STOPPED        = BinaryLogRecord(lambda args: "Endpoint marked as Stopped")
    ENDPOINT_PAUSED         = BinaryLogRecord(lambda args: "Endpoint marked as Paused")
    SCALE_UPDATE            = BinaryLogRecord(lambda args: "Target number of instances has changed: %d => %d" % (args[0], args[1]))
    METRICS_CONFLICT        = BinaryLogRecord(lambda args: "Scaling rules conflict detected")
    CONFIG_UPDATED          = BinaryLogRecord(lambda args: "Configuration reloaded")
    RECOMMISSION_INSTANCE   = BinaryLogRecord(lambda args: "Recommissioning formerly decommissioned instance")
    DECOMMISION_INSTANCE    = BinaryLogRecord(lambda args: "Decommissioning instance")
    LAUNCH_INSTANCE         = BinaryLogRecord(lambda args: "Launching instance")
    LAUNCH_FAULURE          = BinaryLogRecord(lambda args: "Failure launching instance")
    DELETE_INSTANCE         = BinaryLogRecord(lambda args: "Deleting instance")
    CONFIRM_IP              = BinaryLogRecord(lambda args: "Confirmed instance with IP %s" % (inet_ntoa(args[0])))
    DROP_IP                 = BinaryLogRecord(lambda args: "Dropped instance with IP %s" % (inet_ntoa(args[0])))

    def __init__(self, store_cb=None, retrieve_cb=None):
        # Note: if adding new log entry types, they must be added above
        # as well as in the array below, and must be added to the end
        # of the array, or else older binary logs may become unreadable.
        record_types = [
            EndpointLog.ENDPOINT_STARTED,
            EndpointLog.ENDPOINT_STOPPED,
            EndpointLog.ENDPOINT_PAUSED,
            EndpointLog.SCALE_UPDATE,
            EndpointLog.METRICS_CONFLICT,
            EndpointLog.CONFIG_UPDATED,
            EndpointLog.RECOMMISSION_INSTANCE,
            EndpointLog.DECOMMISION_INSTANCE,
            EndpointLog.LAUNCH_INSTANCE,
            EndpointLog.LAUNCH_FAULURE,
            EndpointLog.DELETE_INSTANCE,
            EndpointLog.CONFIRM_IP,
            EndpointLog.DROP_IP
        ]

        # Zookeeper objects are limited to 1MB in size. Since we write
        # the log out every time we log something (an unfortunate
        # necessity until we put in some sort of caching mechanism)
        # we limit the size of the log to 16kB, which we then double
        # by converting to a hex string before storing. At the current
        # log record size, this gives enough room for 1024 log entries.
        BinaryLog.__init__(self, size=(16*1024), record_types=record_types,
                store_cb=store_cb, retrieve_cb=retrieve_cb)

class Endpoint(object):

    def __init__(self, name, scale_manager):
        self.name = name
        self.scale_manager = scale_manager

        # Initialize endpoint-specific logging
        self.logging = EndpointLog(
                store_cb=lambda data: self.scale_manager.endpoint_log_save(self.name, data),
                retrieve_cb=lambda: self.scale_manager.endpoint_log_load(self.name))

        # Initialize (currently empty) configurations.
        self.config = EndpointConfig()
        self.scaling = ScalingConfig()

        # Endpoint state.
        self.state = State.default
        self.decommissioned_instances = []

        # Default to no cloud connection.
        self.cloud_conn = scale_manager._find_cloud_connection()

        # Default to no load balancer.
        self.lb_conn = scale_manager._find_loadbalancer_connection()

    def key(self):
        return compute_key(self.url())

    def url(self):
        return self.config.url or "none://%s" % self.name

    def port(self):
        return self.config.port

    def redirect(self):
        return self.config.redirect

    def weight(self):
        return self.config.weight

    def source_key(self):
        source_url = self.scaling.url
        if source_url:
            return compute_key(source_url)
        else:
            return None

    def manage(self):
        # Load the configuration and configure the endpoint.
        logging.info("Managing endpoint %s" % (self.name))
        self.decommissioned_instances = self.scale_manager.decommissioned_instances(self.name)

    def unmanage(self):
        # Do nothing.
        logging.info("Unmanaging endpoint %s" % (self.name))

    def update(self, reconfigure=True, metrics={}, metric_instances=None, active_ips=[]):
        try:
            self._update(reconfigure, metrics, metric_instances, active_ips)
        except:
            logging.error("Error updating endpoint %s: %s" % \
                (self.name, traceback.format_exc()))

    def _determine_target_instances_range(self, metrics, num_instances):
        """
        Determine the range of instances that we need to scale to. A tuple of the
        form (min_instances, max_instances) is returned.
        """

        # Evaluate the metrics on these instances and get the ideal bounds on the number
        # of servers that should exist.
        ideal_min, ideal_max = metric_calculator.calculate_ideal_uniform(\
                self.scaling.rules, metrics, num_instances)
        logging.debug("Metrics for endpoint %s: ideal_servers=%s (%s)" % \
                (self.name, (ideal_min, ideal_max), metrics))

        if ideal_max < ideal_min:
            # Either the metrics are undefined or have conflicting answers. We simply
            # return this conflicting result.
            if metrics != []:
                # Only log the warning if there were values for the metrics provided. In other words
                # only if the metrics could have made a difference.
                self.logging.warn(self.logging.METRICS_CONFLICT)
                logging.warn("The metrics defined for endpoint %s have resulted in a "
                             "conflicting result. (endpoint metrics: %s)"
                             % (self.name, str(self.scaling.rules)))
            return (ideal_min, ideal_max)

        # Grab the allowable bounds of the number of servers that should exist.
        config_min = self.scaling.min_instances
        config_max = self.scaling.max_instances

        # Determine the intersecting bounds between the ideal and the configured.
        target_min = max(ideal_min, config_min)
        target_max = min(ideal_max, config_max)

        if target_max < target_min:
            # The ideal number of instances falls completely outside the allowable
            # range. This can mean 2 different things:
            if ideal_min > config_max:
                # a. More instances are required than our maximum allowance
                target_min = config_max
                target_max = config_max
            else:
                # b. Less instances are required than our minimum allowance
                target_min = config_min
                target_max = config_min

        return (target_min, target_max)

    def _instance_is_active(self, instance, active_ips):
        for ip in self.cloud_conn.addresses(self.config, instance):
            if ip in active_ips:
                return True
        return False

    def _update(self, reconfigure, metrics, metric_instances, active_ips):
        if self.state == State.paused:
            # Do nothing while paused, this will keep the current
            # instances alive and continue to process requests.
            return

        instances = self.instances()
        num_instances = len(instances)
        ramp_limit = self.scaling.ramp_limit

        if self.state == State.running:
            # If this is a config change update,
            if reconfigure:
                # Just make sure the number of instances is within range.
                target = max(num_instances, self.scaling.min_instances)
                target = min(target, self.scaling.max_instances)
            # Else this is a health check, so make use of the passed metrics.
            else:
                (target_min, target_max) = \
                    self._determine_target_instances_range(metrics, metric_instances)

                if (num_instances >= target_min and num_instances <= target_max) \
                    or (target_min > target_max):
                    # Either the number of instances we currently have is within the
                    # ideal range or we have no information to base changing the number
                    # of instances. In either case we just keep the instances the same.
                    target = num_instances
                else:
                    # we need to either scale up or scale down. Our target will be the
                    # midpoint in the target range.
                    target = (target_min + target_max) / 2

        elif self.state == State.stopped:
            target = 0
            ramp_limit = sys.maxint

        else:
            logging.error("Unknown state '%s' ?!?" % self.state)
            return

        if target != num_instances:
            self.logging.info(self.logging.SCALE_UPDATE, num_instances, target)
            logging.info("Target number of instances for endpoint %s determined to be %s (current: %s)"
                          % (self.name, target, num_instances))

        # Perform only 'ramp' actions per iterations.
        action_count = 0

        # Launch instances until we reach the min setting value.
        if num_instances < target:
            # First, recommission instances that have been decommissioned.
            if len(self.decommissioned_instances) > 0:
                self.recommission_instances(target - num_instances,
                    "bringing instance total up to target %s" % target)
                instances = self.instances()
                num_instances = len(instances)

            # Then, launch new instances.
            while num_instances < target and action_count < ramp_limit:
                self._launch_instance("bringing instance total up to target %s" % target)
                num_instances += 1
                action_count += 1

        # Delete instances until we reach the max setting value.
        elif target < num_instances:
            instances_to_delete = []
            inactive_instances = \
                filter(lambda x: not self._instance_is_active(x, active_ips),
                        instances)
            to_do = min(len(inactive_instances), ramp_limit, 
                                        (num_instances - target))
            for i in range(to_do):
                instances_to_delete.append(inactive_instances.pop(0))

            self.decommission_instances(instances_to_delete,
                "bringing instance total down to target %s" % target)

    def update_sessions(self, sessions, dropped_sessions, authoritative):
        # Drop any sessions indicated by manager
        for backend in dropped_sessions:
            for client in dropped_sessions[backend]:
                self.lb_conn.drop_session(backend, client)
                if authoritative:
                    self.scale_manager.session_dropped(self.name, client)

    def update_state(self, state):
        self.state = state or State.default
        if self.state == State.running:
            self.logging.info(self.logging.ENDPOINT_STARTED)
        elif self.state == State.paused:
            self.logging.info(self.logging.ENDPOINT_PAUSED)
        elif self.state == State.stopped:
            self.logging.info(self.logging.ENDPOINT_STOPPED)

    @staticmethod
    def spec_config(config):
        # Just interpret the configurations appropriately.
        # NOTE: This will have the side-effect of building
        # the specification for the endpoint and scaling rules
        # into this configuration object (hence spec_config).
        EndpointConfig(obj=config)
        ScalingConfig(obj=config)

    def validate_config(self, config, clouds, loadbalancers):
        config = EndpointConfig(obj=config)
        scaling = ScalingConfig(obj=config)
        config._validate()
        scaling._validate()

        # Ensure that this cloud is available.
        if config.cloud:
            if not config.cloud in clouds:
                # Add a message indicating the available clouds.
                config._add_error("cloud", "Available clouds: %s" % ",".join(clouds))
            else:
                # Ensure the cloud configuration is correct.
                cloud = clouds[config.cloud]
                cloud._endpoint_config(config=config)._validate()

        # Ensure the loadbalancer is available.
        if config.loadbalancer:
            if not config.loadbalancer in loadbalancers:
                # Add a message indicating the available loadbalancers.
                config._add_error("loadbalancer", "Available load balancers: %s" % ",".join(loadbalancers))
            else:
                # Ensure the cloud configuration is correct.
                loadbalancer = loadbalancers[config.loadbalancer]
                loadbalancer._endpoint_config(config=config)._validate()

    def update_config(self, config):
        # Check if our configuration is about to change.
        old_url = self.config.url
        old_static_addresses = self.config._static_ips()
        old_port = self.config.port
        old_weight = self.config.weight
        old_redirect = self.config.redirect
        old_lb = self.config.loadbalancer

        new_config = EndpointConfig(obj=config)
        new_scaling = ScalingConfig(obj=config)

        new_url = new_config.url
        new_static_addresses = new_config._static_ips()
        new_port = new_config.port
        new_weight = new_config.weight
        new_redirect = new_config.redirect
        new_lb = new_config.loadbalancer

        # Drop all removed static addresses.
        for ip in old_static_addresses:
            if not(ip in new_static_addresses):
                self.scale_manager.drop_ip(self.name, ip)

        # Remove all old instances from loadbalancer,
        # (Only necessary if we've changed the endpoint URL).
        if old_url != new_url:
            self.scale_manager.remove_endpoint(self.name)

        # Reload the configuration.
        self.config = new_config
        self.scaling = new_scaling

        # Reconnect to the cloud controller (always).
        self.cloud_conn = self.scale_manager._find_cloud_connection(new_config.cloud)

        # Update loadbalancer.
        if old_lb != new_lb:
            # Get a new loadbalancer connection.
            self.lb_conn = self.scale_manager._find_loadbalancer_connection(new_lb)

        # Do a referesh (to capture the new endpoint).
        if old_url != new_url:
            self.scale_manager.add_endpoint(self)

        # Update the load balancer.
        elif old_static_addresses != new_static_addresses or \
             old_port != new_port or \
             old_weight != new_weight or \
             old_redirect != new_redirect:
            self.update_loadbalancer()

        self.logging.info(self.logging.CONFIG_UPDATED)

    def recommission_instances(self, num_instances, reason):
        """
        Recommission formerly decommissioned instances. Note: a reason
        should be given for why the instances are being recommissioned.
        """
        while num_instances > 0 and len(self.decommissioned_instances) > 0:
            self.logging.info(self.logging.RECOMMISSION_INSTANCE)
            instance_id = self.decommissioned_instances.pop()
            logging.info("Recommissioning instance %s for server %s (reason: %s)" %
                    (instance_id, self.name, reason))
            self.scale_manager.recommission_instance(self.name, instance_id)
            num_instances -= 1

        # Update the load balancer.
        self.update_loadbalancer()

    def decommission_instances(self, instances, reason):
        """
        Drop the instances from the system. Note: a reason should be given
        for why the instances are being dropped.
        """
        # It might be good to wait a little bit for the servers to clear out
        # any requests they are currently serving.
        for instance in instances:
            self.logging.info(self.logging.DECOMMISION_INSTANCE)
            instance_id = self.cloud_conn.id(self.config, instance)
            logging.info("Decommissioning instance %s for server %s (reason: %s)" %
                    (instance_id, self.name, reason))
            self.scale_manager.decommission_instance(\
                self.name, instance_id,
                self.cloud_conn.addresses(self.config, instance))
            if not(instance_id in self.decommissioned_instances):
                self.decommissioned_instances += [instance_id]

        # update the load balancer. This can be done after decommissioning
        # because these instances will stay alive as long as there is an active
        # connection.
        if len(instances) > 0:
            self.update_loadbalancer()

    def _delete_instance(self, instance):
        instance_id = self.cloud_conn.id(self.config, instance)
        instance_name = self.cloud_conn.name(self.config, instance)

        # Delete the instance from the cloud.
        self.logging.info(self.logging.DELETE_INSTANCE)
        logging.info("Deleting instance %s for server %s" % (instance_id, self.name))
        self.scale_manager.delete_endpoint_instance(self.name, instance_name)
        self.scale_manager.drop_decommissioned_instance(self.name, instance_id)
        if instance_id in self.decommissioned_instances:
            self.decommissioned_instances.remove(instance_id)
        self.cloud_conn.delete_instance(self.config, instance_id)

        # Cleanup any loadbalancer artifacts
        self.lb_conn.cleanup(self.config, instance_name)

    def _launch_instance(self, reason):
        # Launch the instance.
        self.logging.info(self.logging.LAUNCH_INSTANCE)
        logging.info(("Launching new instance for server %s " +
                     "(reason: %s)") %
                     (self.name, reason))
        start_params = self.scale_manager.start_params(self)
        start_params.update(self.lb_conn.start_params(self.config))
        try:
            instance = self.cloud_conn.start_instance(self.config,
                                                         params=start_params)
        except:
            self.logging.error(self.logging.LAUNCH_FAULURE)
            logging.error("Error launching instance for server %s: %s" % \
                (self.name, traceback.format_exc()))
            self.lb_conn.cleanup_start_params(self.config, start_params)
            self.scale_manager.cleanup_start_params(self, start_params)
        self.scale_manager.add_endpoint_instance(self.name,
                self.cloud_conn.id(self.config, instance),
                self.cloud_conn.name(self.config, instance))

    def static_addresses(self):
        return self.config._static_ips()

    def instances(self, filter=True):
        cloud_instances = self.cloud_conn.list_instances(self.config)
        endpoint_instances = self.scale_manager.endpoint_instances(self.name)
        instances = []
        for instance in cloud_instances:
            if self.cloud_conn.id(self.config, instance) in endpoint_instances:
                instances.append(instance)

        if filter:
            # Filter out the decommissioned instances from the returned list.
            all_instances = instances
            instances = []
            for instance in all_instances:
                if not(self.cloud_conn.id(self.config, instance) \
                    in self.decommissioned_instances):
                    instances.append(instance)
        return instances

    def orphaned_instances(self):
        cloud_instances = self.cloud_conn.list_instances(self.config)
        endpoint_instances = self.scale_manager.endpoint_instances(self.name)
        instance_ids = []
        for instance in cloud_instances:
            instance_id = self.cloud_conn.id(self.config, instance)
            if instance_id in endpoint_instances:
                instance_ids.append(instance_id)
        return list(set(endpoint_instances) - set(instance_ids))

    def addresses(self):
        try:
            all_addresses = set()
            for instance in self.instances():
                all_addresses.update( \
                    self.cloud_conn.addresses(self.config, instance))
            return list(all_addresses)
        except:
            logging.error("Error querying endpoint %s addresses: %s" % \
                (self.name, traceback.format_exc()))
            return []

    def instance_by_id(self, instances, instance_id):
        instance_list = filter( \
            lambda x: self.cloud_conn.id(self.config, x) == instance_id, instances)
        if len(instance_list) == 1:
            return instance_list[0]
        raise KeyError('instance with id %s not found' % (instance_id))

    def update_loadbalancer(self, remove=False):
        (ips, redirects) = self.scale_manager.collect_endpoint(self)

        if len(ips) > 0 or len(redirects) == 0:
            self.lb_conn.change(self.url(), [self.name], ips,
                    config=self.config)
        else:
            self.lb_conn.redirect(self.url(), [self.name], redirects[0],
                    config=self.config)


        self.lb_conn.save()

    def health_check(self, active_ips):
        instances = self.instances(filter=False)
        instance_ids = map(lambda x: self.cloud_conn.id(self.config, x), instances)

        # Mark sure that the manager does not contain any scale data, which
        # may result in some false metric data and clogging up Zookeeper.
        for instance_id in self.scale_manager.marked_instances(self.name):
            if not(instance_id in instance_ids):
                self.scale_manager.drop_marked_instance(self.name, instance_id)
        for instance_id in self.scale_manager.decommissioned_instances(self.name):
            if not(instance_id in instance_ids):
                self.scale_manager.drop_decommissioned_instance(self.name, instance_id)

        # Check if any expected machines have failed to come up and confirm their IP address.
        confirmed_ips = set(self.scale_manager.confirmed_ips(self.name))

        # There are the confirmed ips that are actually associated with an
        # instance. Other confirmed ones will need to be dropped because the
        # instances they refer to no longer exists.
        associated_confirmed_ips = set()
        inactive_instance_ids = []
        for instance in instances:
            instance_id = self.cloud_conn.id(self.config, instance)
            expected_ips = set(self.cloud_conn.addresses(self.config, instance))
            # As long as there is one expected_ip in the confirmed_ip,
            # everything is good. Otherwise This instance has not checked in.
            # We need to mark it, and it if has enough marks it will be
            # destroyed.
            logging.info("expected ips=%s, confirmed ips=%s" % (expected_ips, confirmed_ips))
            instance_confirmed_ips = confirmed_ips.intersection(expected_ips)
            if len(instance_confirmed_ips) == 0 and \
               not instance_id in self.decommissioned_instances:
                # The expected ips do no intersect with the confirmed ips.
                # This instance should be marked.
                if self.scale_manager.mark_instance(self.name, instance_id, 'unregistered'):
                    # This instance has been deemed to be dead and should be cleaned up.
                    # We don't decomission it because we have never heard from it in the
                    # first place. So there's no sense in decomissioning it.
                    self._delete_instance(instance)
            else:
                associated_confirmed_ips = associated_confirmed_ips.union(instance_confirmed_ips)

            # Check if any of these expected_ips are not in our active set. If
            # so that this instance is currently considered inactive.
            if len(expected_ips.intersection(active_ips)) == 0:
                inactive_instance_ids += [instance_id]

        # TODO(dscannell) We also need to ensure that the confirmed IPs are
        # still valid. In other words, we have a running instance for it.
        orphaned_confirmed_ips = confirmed_ips.difference(associated_confirmed_ips)
        if len(orphaned_confirmed_ips) > 0:
            # There are orphaned ip addresses. We need to drop them and then
            # update the load balancer because there is no actual instance
            # backing them.
            logging.info("Dropping ips %s for endpoint %s because they do not have"
                         " backing instances." % (orphaned_confirmed_ips, self.name))
            for orphaned_address in orphaned_confirmed_ips:
                self.scale_manager.drop_ip(self.name, orphaned_address)
            self.update_loadbalancer()

        # Clean up any instances which don't exist any more.
        for instance_id in self.orphaned_instances():
            logging.info("Cleaning up disappeared instance %s" % instance_id)
            instance_name = self.scale_manager.get_endpoint_instance(self.name, instance_id)
            if instance_name:
                self.lb_conn.cleanup(self.config, instance_name)
            self.scale_manager.delete_endpoint_instance(self.name, instance_id)

        # See if there are any decommissioned instances that are now inactive.
        decommissioned_instance_ids = copy.copy(self.decommissioned_instances)
        logging.debug("Active instances: %s:%s:%s" % \
            (active_ips, inactive_instance_ids, decommissioned_instance_ids))

        for inactive_instance_id in inactive_instance_ids:
            if inactive_instance_id in decommissioned_instance_ids:
                if self.scale_manager.mark_instance(self.name,
                                                    inactive_instance_id,
                                                    'decommissioned'):
                        instance = self.instance_by_id(instances, inactive_instance_id)
                        self._delete_instance(instance)

    # The following two methods are for advisory purposes only.
    def ip_confirmed(self, ip):
        self.logging.info(self.logging.CONFIRM_IP, inet_aton(ip))

    def ip_dropped(self, ip):
        self.logging.info(self.logging.DROP_IP, inet_aton(ip))
