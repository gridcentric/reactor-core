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

import hashlib
import socket
import sys
import traceback
import math

from . atomic import Atomic
from . config import Config
from . submodules import cloud_submodules, cloud_options
from . submodules import loadbalancer_submodules, loadbalancer_options
from . eventlog import EventLog, Event
from . utils import sha_hash
from . cloud import connection as cloud_connection
from . cloud import instance as cloud_instance
from . loadbalancer import connection as lb_connection
from . loadbalancer import backend as lb_backend
from . metrics import calculator as metric_calculator
from . objects.endpoint import State
from . zookeeper.cache import Cache

class EndpointConfig(Config):

    def __init__(self, **kwargs):
        super(EndpointConfig, self).__init__(
            section="endpoint", **kwargs)

    url = Config.string(label="Endpoint URL", order=0,
        description="The URL for this endpoint.")

    port = Config.integer(label="Backend Port", order=1,
        validate=lambda self: self.port >= 0 or \
            Config.error("Port must not be negative."),
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

    error_marks = Config.integer(label="Maximum Errors",
        default=1, order=2,
        validate=lambda self: self.error_marks >= 0 or \
            Config.error("Errors must be non-negative."),
        description="Maximum error count for active VMs.")

    unregistered_timeout = Config.integer(label="Unregistered Timeout (s)",
        default=36, order=2,
        validate=lambda self: self.unregistered_timeout > 0 or \
            Config.error("Timeout must be positive."),
        description="Timeout for unregistered VMs.")

    decommissioned_timeout = Config.integer(label="Decommissioned Timeout (s)",
        default=18, order=2,
        validate=lambda self: self.decommissioned_timeout > 0 or \
            Config.error("Timeout must be positive."),
        description="Timeout for decomissioned VMs.")

    auth_hash = Config.string(label="Auth Hash Token", default=None, order=3,
        description="The authentication token for this endpoint.")

    auth_salt = Config.string(label="Auth Hash Salt", default="", order=3,
        description="The salt used for computing authentication tokens.")

    auth_algo = Config.string(label="Auth Hash Algorithm", default="sha1", order=3,
        validate=lambda self: hashlib.new(self.auth_algo, ''),
        description="The algorithm used for computing authentication tokens.")

    def endpoint_auth(self):
        return (self.auth_hash, self.auth_salt, self.auth_algo)

    static_instances = Config.list(label="Static Backends", order=1,
        validate=lambda self: self.static_ips(validate=True),
        description="Static hosts for the endpoint.")

    def static_ips(self, validate=False):
        """
        Returns a list of static ips associated with the endpoint.
        """
        static_instances = self.static_instances

        # (dscannell) The static instances can be specified either as IP
        # addresses or hostname.  If its an IP address then we are done. If its
        # a hostname then we need to do a lookup to determine its IP address.
        ip_addresses = []
        for static_instance in static_instances:
            try:
                if static_instance != '':
                    ip_addresses += [socket.gethostbyname(static_instance)]
            except Exception:
                if validate:
                    raise
        return ip_addresses

    def spec(self):
        ScalingConfig(obj=self)
        for name in loadbalancer_submodules():
            lb_connection.get_connection(name)._endpoint_config(self)
        for name in cloud_submodules():
            cloud_connection.get_connection(name)._endpoint_config(self)
        return super(EndpointConfig, self).spec()

    def validate(self):
        # NOTE: We do the validation here without a proper manager config.
        # it is quite possible that the available manager does not support
        # those clouds and / or load balancers, or that it is configured in
        # such a way that it may fail elsewhere. Unfortunately, there isn't
        # much we can really do at this point without making the architecture
        # overly complex.
        errors = super(EndpointConfig, self).validate()
        errors.update(ScalingConfig(obj=self).validate())
        if self.loadbalancer:
            if not self.loadbalancer in loadbalancer_submodules():
                self._add_error('loadbalancer', 'Unknown loadbalancer.')
            else:
                try:
                    # Validate our URL with the loadbalancer.
                    lb_connection.get_connection(
                        self.loadbalancer).url_info(self.url)
                except Exception, e:
                    self._add_error('url', str(e))
                # Validate any loadbalancer configuration.
                errors.update(lb_connection.get_connection(
                    self.loadbalancer)._endpoint_config(self).validate())
        if self.cloud:
            if not self.cloud in cloud_submodules():
                self._add_error('cloud', 'Unknown cloud.')
            else:
                # Validate any cloud configuration.
                errors.update(cloud_connection.get_connection(
                    self.cloud)._endpoint_config(self).validate())
        errors.update(self._get_errors())
        return errors

class ScalingConfig(Config):

    def __init__(self, **kwargs):
        super(ScalingConfig, self).__init__(
            "scaling", **kwargs)

    min_instances = Config.integer(label="Minimum Instances", default=1, order=0,
        validate=lambda self: (self.min_instances >= 0 or \
            Config.error("Min instances must be zero or greater.")) and \
            (self.max_instances >= self.min_instances or \
            Config.error("Min instances (%d) must be less than Max instances (%d)" % \
                (self.min_instances, self.max_instances))),
        description="Lower limit on dynamic instances.")

    max_instances = Config.integer(label="Maximum Instances", default=1, order=1,
        validate=lambda self: (self.max_instances >= 0 or \
            Config.error("Max instances must be zero or greater.")) and \
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

def _as_ip(ips):
    if isinstance(ips, list):
        return len(ips) > 0 and ips[0] or "unknown"
    else:
        return ips

class EndpointLog(EventLog):

    # The log size (# of entries).
    LOG_SIZE = 100

    # Log entry types.
    ENDPOINT_STARTED = Event(
        lambda args: "Endpoint marked as Started")
    ENDPOINT_STOPPED = Event(
        lambda args: "Endpoint marked as Stopped")
    ENDPOINT_PAUSED = Event(
        lambda args: "Endpoint marked as Paused")
    INSTANCE_UPDATE = Event(
        lambda args: "Instance states: %s" % args[0])
    SCALE_UPDATE = Event(
        lambda args: "Target number of instances has changed: %d => %d" % (args[0], args[1]))
    METRICS_CONFLICT = Event(
        lambda args: "Scaling rules conflict detected")
    CONFIG_UPDATED = Event(
        lambda args: "Configuration reloaded")
    RECOMMISSION_INSTANCE = Event(
        lambda args: "Recommissioning instance with IP %s" % _as_ip(args[0]))
    DECOMMISSION_INSTANCE = Event(
        lambda args: "Decommissioning instance with IP %s" % _as_ip(args[0]))
    CLEAN_INSTANCE = Event(
        lambda args: "Cleaning instance data for %s" % args[0])
    LAUNCH_INSTANCE = Event(
        lambda args: "Launching instance")
    LAUNCH_SUCCESS = Event(
        lambda args: "Launched instance %s" % args[0])
    LAUNCH_FAILURE = Event(
        lambda args: "Failure launching instance: %s" % args[0])
    DELETE_INSTANCE = Event(
        lambda args: "Deleting instance with IP %s" % _as_ip(args[0]))
    DELETE_FAILURE = Event(
        lambda args: "Failure deleting instance with IP %s" % _as_ip(args[0]))
    CONFIRM_IP = Event(
        lambda args: "Confirmed instance with IP %s (%s)" %
            (_as_ip(args[0]), len(args) > 1 and args[1] or "unknown"))
    DROP_IP = Event(
        lambda args: "Dropped instance with IP %s (%s)" %
            (_as_ip(args[0]), len(args) > 1 and args[1] or "unknown"))
    ERROR_IP = Event(
        lambda args: "Errors on instance with IP %s" % _as_ip(args[0]))
    ERROR_INSTANCE = Event(
        lambda args: "Errors on instance %s" % args[0])
    UPDATE_ERROR = Event(
        lambda args: "Error updating endpoint: %s" % args[0])
    RELOADED = Event(
        lambda args: "Loadbalancer updated")

    def __init__(self, *args):
        super(EndpointLog, self).__init__(*args, size=EndpointLog.LOG_SIZE)

class Endpoint(Atomic):

    def __init__(self, zkobj,
                 collect=None,
                 find_cloud_connection=None,
                 find_loadbalancer_connection=None,
                 delete_hook=None):
        super(Endpoint, self).__init__()

        # Our zookeeper object.
        self.zkobj = zkobj

        # Values from our scale manager.
        # NOTE: See the note in endpoint_change() within the
        # manager. Because these callbacks come the manager class,
        # the manager will call break_refs() to ensure that this
        # object will be garbage collected properly.
        self._collect = collect
        self._find_cloud_connection = find_cloud_connection
        self._find_loadbalancer_connection = find_loadbalancer_connection
        self._delete_hook = delete_hook

        # Initialize endpoint-specific logging.
        self.logging = EndpointLog(zkobj.log())

        # Endpoint state.
        self.state = State.default

        # Default to no cloud connection.
        self.cloud_conn = cloud_connection.get_connection(None)

        # Default to no load balancer.
        self.lb_conn = lb_connection.get_connection(None)

        # Initialize configuration.
        self.config = EndpointConfig()
        self.scaling = ScalingConfig()

        # Instances is a cache which maps instances to their names.
        self.instances = Cache(self.zkobj.instances())

        # Instance IPs is a separate cache which maps to the cloud IP address.
        self.instance_ips = Cache(self.zkobj.instances(), populate=self._ips_for_instance)

        # Confirmed IPs map to the instance_id.
        self.confirmed_ips = Cache(self.zkobj.confirmed_ips(), update=self._update_confirmed)

        # Decomissioned instances maps to the instance name (as instances above).
        # NOTE: When we decommission an instance, we remove it from the set of
        # known instances above. The instance name information is persisted here.
        self.decommissioned = Cache(self.zkobj.decommissioned_instances())

        # Errored instances map to the instance name (as instances above).
        # This has the same semantics as decommissioned, except they may not be
        # recommissioned (because they were removed from the pool due to errors).
        self.errored = Cache(self.zkobj.errored_instances())

        # Start watching the configuration.
        self.update_config(self.zkobj.get_config(watch=self.update_config))

        # Start watching our state.
        self.update_state(self.zkobj.state().current(watch=self.update_state))

        # Start watching whether we're being deleted.
        self.deleted = False
        self.check_deleting(self.zkobj.is_deleting(watch=self.check_deleting))

    def __del__(self):
        self.zkobj.unwatch()

    def check_deleting(self, val):
        # If we're deleting, we notify all interested
        # parties. This means that they can stop updating
        # and basically ensure that the delete goes through
        # cleanly without a bunch of trashing.
        if val:
            self.deleted = True
            self.reload(exclude=True)
            if self._delete_hook:
                if self._delete_hook(self):
                    self.break_refs()
                    self.zkobj._delete()
                else:
                    self.break_refs()
            else:
                self.break_refs()

    def break_refs(self):
        # See NOTE above.
        self.zkobj.unwatch()
        if hasattr(self, '_collect'):
            del self._collect
            del self._find_cloud_connection
            del self._find_loadbalancer_connection
            del self._delete_hook

    # This method is a simple method used for populating our
    # instance IP cache. All the cached (decommissioned instances,
    # confirmed ips, instance names) are populated and maintained
    # automatically by the Cache class, but here we need to be able
    # to pass in a bit more data when necessary.
    def _ips_for_instance(self, instance_id):
        instances = self.cloud_conn.list_instances(self.config, instance_id=instance_id)

        # Probably a race condition.
        # We just ignore this and populate() will get
        # recalled or whatever at a more appropriate moment.
        if len(instances) == 0:
            return []

        # Return the current set of IPs. Note that if this
        # is an empty list (which will happen at the beginning)
        # then populate() will be recalled until it is not an
        # empty list.
        return instances[0].ips

    # This method is a hook used to update the loadbalancer when
    # the confirmed cache changes. This will be automatically
    # called by the cache whenever the confirmed IPs change.
    def _update_confirmed(self):
        self.reload()

    @Atomic.sync
    def key(self):
        # Some loadbalancers supported operation with
        # an explicit URL specified. In order to ensure
        # that we don't confuse endpoints that on two
        # different loadbalancers without a URL, we will
        # hash the loadbalancer name if no URL is provided.
        if self.config.url:
            return sha_hash(self.config.url)
        elif self.config.loadbalancer:
            return sha_hash(self.config.loadbalancer)
        else:
            return sha_hash("")

    @Atomic.sync
    def metric_key(self):
        source_url = self.scaling.url
        if source_url:
            return sha_hash(source_url)
        else:
            return self.key()

    def managed(self, uuid):
        # Mark that this is our manager.
        # NOTE: This is really for informational
        # purposes only, we don't make any decisions
        # internally on whether or not we will call
        # update() based on this uuid etc.
        self.zkobj.manager = uuid

    def update(self,
               metrics=None,
               metric_instances=None,
               active_ports=None,
               update_interval=None):
        """
        Update the endpoint based on current metrics and
        active instances. This will launch new instances or
        recomission old ones in response to demand.
        """
        if metrics is None:
            metrics = {}
        if metric_instances is None:
            metric_instances = []
        if active_ports is None:
            active_ports = []

        try:
            # Save the live metrics and active connections
            # to the zookeeper backend. These don't serve
            # any practical purpose, they are simply exposed
            # by the API for debugging purposes, etc.
            self.zkobj.metrics = metrics
            self.zkobj.active = active_ports

            # Grab the current collection of instances.
            # This includes all instances, depending on what
            # you are doing with this list it will be necessary
            # to filter it through decomissioned, etc.
            instances = self.cloud_conn.list_instances(self.config)

            # Run a healthcheck to reap old instances,
            # decomissioned instances, unable to launch, etc.
            (active_ids, inactive_ids) = \
                self._health_check(
                    instances,
                    active_ports,
                    update_interval=update_interval)

            # Run an update to launch new instances.
            return self._update(instances,
                                active_ids=active_ids,
                                inactive_ids=inactive_ids,
                                metrics=metrics,
                                metric_instances=metric_instances)

        except Exception, e:
            traceback.print_exc()
            self.logging.error(self.logging.UPDATE_ERROR, str(e))
            return False

    def _determine_target_instances_range(self, metrics, num_instances):
        """
        Determine the range of instances that we need to scale to. A tuple of the
        form (min_instances, max_instances) is returned.
        """

        # Evaluate the metrics on these instances and get the ideal bounds on
        # the number of servers that should exist.
        ideal_min, ideal_max = metric_calculator.calculate_ideal_uniform(
                self.scaling.rules, metrics, num_instances)
        if ideal_max < ideal_min:
            # Either the metrics are undefined or have conflicting answers. We simply
            # return this conflicting result.
            if metrics != []:
                # Only log the warning if there were values for the metrics
                # provided. In other words only if the metrics could have made
                # a difference.
                self.logging.warn(self.logging.METRICS_CONFLICT)
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

    def _update(self,
                instances,
                active_ids,
                inactive_ids,
                metrics,
                metric_instances):
        """
        Launch new instances, decommission instances, etc.
        """
        # Look only at the current set of instances.
        instances = self._filter_instances(instances, errored=False, decommissioned=False)
        num_instances = len(instances)
        ramp_limit = self.scaling.ramp_limit

        if self.state == State.paused:
            # Do nothing while paused, this will keep the current
            # instances alive and continue to process requests.
            return

        if self.state == State.running:

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
            return

        if target != num_instances:
            self.logging.info(self.logging.SCALE_UPDATE, num_instances, target)

        # Perform only 'ramp' actions per iterations.
        action_count = 0

        # Launch instances until we reach the min setting value.
        if num_instances < target:
            # First, recommission instances that have been decommissioned.
            num_instances += self._recommission_instances(
                target - num_instances,
                "bringing instance total up to target %s" % target)

            # Then, launch new instances.
            while num_instances < target and action_count < ramp_limit:
                self._launch_instance()
                num_instances += 1
                action_count += 1

        # Delete instances until we reach the max setting value.
        elif target < num_instances:

            # Build our list of candidates (favoring those that are not active).
            candidates = list(set(inactive_ids).intersection(instances))
            candidates.extend(list(set(active_ids).intersection(instances)))

            # Take all the instances that we can.
            to_do = min(len(candidates), ramp_limit, num_instances - target)
            self._decommission_instances(candidates[:to_do])

    def session_opened(self, client, backend):
        self.zkobj.sessions().opened(client, backend)

    def session_closed(self, client, backend):
        self.zkobj.sessions().closed(client)

    def drop_sessions(self, authoritative=False):
        for (client, backend) in self.zkobj.sessions().drop_map().items():
            self.lb_conn.drop_session(client, backend)
            if authoritative:
                self.zkobj.sessions().dropped(client)

    @Atomic.sync
    def _update_state(self, state):
        self.state = state or State.default
        return self.state

    def update_state(self, state):
        state = self._update_state(state)
        if state == State.running:
            self.logging.info(self.logging.ENDPOINT_STARTED)
        elif state == State.paused:
            self.logging.info(self.logging.ENDPOINT_PAUSED)
        elif state == State.stopped:
            self.logging.info(self.logging.ENDPOINT_STOPPED)

    @Atomic.sync
    def _update_config(self, config_val):
        """
        Reload the configuration for this endpoint.

        This function will return True if the loadbalancer should
        be updated after return, much like update() and health_check().
        """
        # Check if our configuration is about to change.
        old_url = self.config.url
        old_static_addresses = self.config.static_ips()
        old_port = self.config.port
        old_weight = self.config.weight

        new_config = EndpointConfig(values=config_val)
        new_scaling = ScalingConfig(obj=new_config)

        new_url = new_config.url
        new_static_addresses = new_config.static_ips()
        new_port = new_config.port
        new_weight = new_config.weight

        # NOTE: We used to take action on old static
        # addresses. This is no longer done, because it's
        # an easy attack vector for different endpoints.
        # Now we don't really allow static addresses to
        # influence any actions wrt. to registered IPs.

        # Remove all old instances from loadbalancer,
        # (Only necessary if we've changed the endpoint URL).
        if old_url != new_url:
            self.reload(exclude=True)

        # Reload the configuration.
        self.config = new_config
        self.scaling = new_scaling

        # Reconnect to the cloud controller.
        if self._find_cloud_connection:
            self.cloud_conn = self._find_cloud_connection(
                new_config.cloud)

        # Get a new loadbalancer connection.
        if self._find_loadbalancer_connection:
            self.lb_conn = self._find_loadbalancer_connection(
                new_config.loadbalancer)

        # We can't really know if loadbalancer settings
        # have changed in the backend, so we really need
        # to *always* do a loadbalancer reload.
        self.reload()

    def update_config(self, config_val):
        self._update_config(config_val)
        self.logging.info(self.logging.CONFIG_UPDATED)

    def _recommission_instances(self, num_instances, reason):
        """
        Recommission formerly decommissioned instances. Note: a reason
        should be given for why the instances are being recommissioned.
        """
        recommissioned = 0
        decommissioned = self.decommissioned.list()

        while num_instances > 0 and len(decommissioned) > 0:
            # Grab the old decomission data.
            instance_id = decommissioned.pop()
            ips = self.instance_ips.get(instance_id)

            # Log a message.
            self.logging.info(self.logging.RECOMMISSION_INSTANCE, ips)

            # Drop old decommission state.
            # Here we readd this instance to our regular instances.
            name = self.decommissioned.get(instance_id)
            self.decommissioned.remove(instance_id)
            self.zkobj.marked_instances().remove(instance_id)
            self.instances.add(instance_id, name)

            for ip in self.instance_ips.get(instance_id):
                # Reconfirm all ip addresses.
                self.logging.info(self.logging.CONFIRM_IP, ip, "recommission")
                self.confirmed_ips.add(ip, instance_id)

            recommissioned += 1
            num_instances -= 1

        return recommissioned

    def _decommission_instances(self, instance_ids, errored=False):
        """
        Drop the instances from the system.
        """
        # It might be good to wait a little bit for the servers
        # to clear out any requests they are currently serving.
        for instance_id in instance_ids:
            # Write the instance id to decommission.
            # (NOTE: Our update hooks will take care of the rest).
            name = self.instances.get(instance_id)
            ips = self.instance_ips.get(instance_id)

            # There are no confirmed IPs here.
            # So we don't actually need to decomission this instance.
            # In fact, that will create a bit of a problem, because
            # instances that get decomissioned *have* been active at
            # some point and we know they are good. If this instance
            # is not active and being called here, we know that it's
            # never been active. So we kill it directly.
            if len(set(ips).intersection(set(self.confirmed_ips.list()))) == 0:
                self._delete_instance(instance_id)
                continue

            # Log a message.
            self.logging.info(self.logging.DECOMMISSION_INSTANCE, ips)

            self.instances.remove(instance_id)
            if errored:
                self.errored.add(instance_id, name)
            else:
                self.decommissioned.add(instance_id, name)

            # Unconfirm the address.
            # NOTE: We don't clear out the IP metrics here.
            # If we end up recommissioning this instance, we want
            # the same set of IP metrics to be effect, so they will
            # only be cleared out when the actual instance is deleted.
            for ip in ips:
                self.logging.info(self.logging.DROP_IP, ip, "decomission")
                self.confirmed_ips.remove(ip)

    def _delete_instance(self, instance_id, cloud=True, errored=False, decommissioned=False):
        # NOTE: Because we're going to lose this instance from
        # the cloud, we do our best to populate the caches here.
        # The only real state that we rely on coming from the cloud
        # is the list of IP addresses, and if we've just *restarted*
        # reactor, it's possible that it hasn't been populate yet.
        ips = self.instance_ips.get(instance_id)

        # Log our message.
        self.logging.info(self.logging.DELETE_INSTANCE, ips)

        if cloud:
            try:
                # Try the cloud call first thing.
                self.cloud_conn.delete_instance(self.config, instance_id)
            except Exception:
                # Not much we can do? Log and return.
                # Hopefully at some point the user will
                # intervene and remove the instance.
                traceback.print_exc()
                self.logging.error(self.logging.DELETE_FAILURE, ips)
                return

        # Cleanup the leftover state from the instance.
        self._clean_instance(instance_id, errored=errored, decommissioned=decommissioned)

    def _clean_instance(self, instance_id, errored=False, decommissioned=False):
        self.logging.info(self.logging.CLEAN_INSTANCE, instance_id)
        if errored:
            name = self.errored.get(instance_id)
        elif decommissioned:
            name = self.decommissioned.get(instance_id)
        else:
            name = self.instances.get(instance_id)

        if name:
            # Cleanup any loadbalancer artifacts.
            self.lb_conn.cleanup(self.config, name)

        # Clear out all IP data.
        # NOTE: There may also be decommissioned data
        # and marked data associated with this instance,
        # but we will allow that to be cleaned up naturally
        # by the health_check process (which scrubs old ids).
        ips = self.instance_ips.get(instance_id)
        for ip in ips:
            self.logging.info(self.logging.DROP_IP, ip, "clean")
            self.confirmed_ips.remove(ip)
            self.zkobj.ip_metrics().remove(ip)

        # Drop the basic instance information.
        if errored:
            self.errored.remove(instance_id)
        elif decommissioned:
            self.decommissioned.remove(instance_id)
        else:
            self.instances.remove(instance_id)

    def _launch_instance(self):
        # Launch the instance.
        self.logging.info(self.logging.LAUNCH_INSTANCE)

        # Start with the loadbalancer parameters.
        start_params = self.lb_conn.start_params(self.config)

        try:
            # Try to start the instance via our cloud connection.
            (instance, ips) = \
                self.cloud_conn.start_instance(
                    self.config, params=start_params)

            if ips:
                for ip in ips:
                    # The IP address has been pre-confirmed.
                    self.logging.info(self.logging.CONFIRM_IP, ip, "launch")
                    self.confirmed_ips.add(ip, instance.id)

        except Exception, e:
            self.logging.error(self.logging.LAUNCH_FAILURE, str(e))

            # Cleanup the start params.
            self.lb_conn.cleanup_start_params(self.config, start_params)
            return

        # Save basic instance data.
        self.instances.add(instance.id, instance.name)
        self.logging.info(self.logging.LAUNCH_SUCCESS, instance.id)

    def _filter_instances(self, instances, regular=True, decommissioned=True, errored=True):
        known_instances = self.instances.list()
        decommissioned_instances = self.decommissioned.list()
        errored_instances = self.errored.list()
        return [x.id for x in instances if
             (x.id in known_instances or
             (decommissioned and x.id in decommissioned_instances) or
             (errored and x.id in errored_instances))]

    def _health_check(self, instances, active_ports, update_interval=None):
        """
        Reap instances that are not responding or have been
        decomissioned for a sufficiently long period of time.
        """
        instance_ids = self._filter_instances(instances)
        decommissioned_instances = self.decommissioned.list()
        errored_instances = self.errored.list()
        confirmed_ips = set(self.confirmed_ips.list())
        active_ports = set(active_ports)

        # Check if there's an error indicated by the cloud backend.
        for instance in instances:
            if instance.id in instance_ids and \
               instance.status == cloud_instance.STATUS_ERROR and \
               not instance.id in self.errored.list() and \
               self._mark_instance(instance.id, 'error'):
                self.logging.warn(self.logging.ERROR_INSTANCE, instance.id)
                self._decommission_instances([instance.id], errored=True)

        # Log the state of all instances.
        instance_states = {
            "total": len(instance_ids),
            "active": len(confirmed_ips),
            "decommissioned": len(decommissioned_instances),
            "errored": len(errored_instances),
        }
        self.logging.info(self.logging.INSTANCE_UPDATE, instance_states)

        # Mark sure that the manager does not contain old
        # scale data, which may result in clogging up Zookeeper.
        # (The internet is a series of tubes).
        for instance_id in self.instances.list():
            if not(instance_id in instance_ids):
                self._clean_instance(instance_id)
        for instance_id in self.decommissioned.list():
            if not(instance_id in instance_ids):
                self._clean_instance(instance_id, decommissioned=True)
        for instance_id in self.errored.list():
            if not(instance_id in instance_ids):
                self._clean_instance(instance_id, errored=True)
        for instance_id in self.zkobj.marked_instances().list():
            if not(instance_id in instance_ids):
                self.zkobj.marked_instances().remove(instance_id)

        # There are the confirmed ips that are actually associated with an
        # instance. Other confirmed ones will need to be dropped because the
        # instances they refer to no longer exists.
        associated_confirmed_ips = set()
        active_instance_ids = []
        inactive_instance_ids = []
        for instance_id in instance_ids:
            # As long as there is one expected_ip in the confirmed_ip,
            # everything is good. Otherwise This instance has not checked in.
            # We need to mark it, and it if has enough marks it will be
            # destroyed.
            expected_ips = set(self.instance_ips.get(instance_id))
            instance_confirmed_ips = confirmed_ips.intersection(expected_ips)
            if len(instance_confirmed_ips) == 0 and \
               not instance_id in decommissioned_instances and \
               not instance_id in errored_instances:

                # The expected ips do no intersect with the confirmed ips.
                # This instance should be marked.
                if self._mark_instance(
                    instance_id,
                    'unregistered',
                    marks=update_interval):

                    # This instance has been deemed to be dead and should be
                    # cleaned up.  We don't decomission it because we have
                    # never heard from it in the first place. So there's no
                    # sense in decomissioning it.
                    self._delete_instance(instance_id)

            else:
                associated_confirmed_ips = \
                    associated_confirmed_ips.union(instance_confirmed_ips)

            # Make sure that this is a fully formed hostinfo.
            # This is because the manager will call us with formed
            # host:port pairs in order to reduce backend ambiguity.
            expected_ports = set(map(
                lambda x: x if ":" in x else "%s:%d" % (x, self.config.port),
                expected_ips))

            # Check if any of these expected_ips are not in our active set. If
            # so that this instance is currently considered inactive.
            if len(expected_ports.intersection(active_ports)) == 0:
                inactive_instance_ids += [instance_id]
            else:
                active_instance_ids += [instance_id]

        # TODO(dscannell): We also need to ensure that the confirmed IPs are
        # still valid. In other words, we have a running instance for it.
        orphaned_ips = confirmed_ips.difference(associated_confirmed_ips)
        if len(orphaned_ips) > 0:
            # There are orphaned ip addresses. We need to drop them and then
            # update the load balancer because there is no actual instance
            # backing them.
            for orphaned_address in orphaned_ips:
                self.logging.info(self.logging.DROP_IP, orphaned_address, "orphaned")
                self.confirmed_ips.remove(orphaned_address)

        # This step is done to ensure that the instance remains inactive for at
        # least a small period of time before we destroy it. It's quite
        # possible that it's reporting is out of date and there are some late
        # sessions or connections to this backend.
        for inactive_instance_id in inactive_instance_ids:
            if inactive_instance_id in decommissioned_instances:
                if self._mark_instance(
                    inactive_instance_id,
                    'decommissioned',
                    marks=update_interval):
                    self._delete_instance(inactive_instance_id, decommissioned=True)
            if inactive_instance_id in errored_instances:
                if self._mark_instance(
                    inactive_instance_id,
                    'decommissioned',
                    marks=update_interval):
                    self._delete_instance(inactive_instance_id, errored=True)

        # Return the active instance ids for update().
        return (active_instance_ids, inactive_instance_ids)

    def ip_confirmed(self, ip):
        for instance_id in self.instances.list():
            if ip in self.instance_ips.get(instance_id):
                # NOTE: We only add the IP to the set of confirmed IPs.
                # The reload of the loadbalancer, etc. will be handled
                # out of the band when the confirmed IPs cache is updated.
                self.logging.info(self.logging.CONFIRM_IP, ip, "confirmed")
                self.confirmed_ips.add(ip, instance_id)
                return True
        return False

    def ip_dropped(self, ip):
        if ip in self.confirmed_ips.list():
            # NOTE: We only remove the IP from our set of
            # confirmed IPs. Eventually, the backing machine
            # will fail a health check (marks, etc.) and be
            # purged from the system.
            self.logging.info(self.logging.DROP_IP, ip, "dropped")
            self.confirmed_ips.remove(ip)
            return True
        return False

    def ip_errored(self, ip):
        for instance_id in self.instances.list():
            if ip in self.instance_ips.get(instance_id):
                # If this belongs to an instance of ours,
                # then we call mark_instance appropriately.
                if self._mark_instance(instance_id, 'error'):
                    self.logging.warn(self.logging.ERROR_IP, ip)
                    self._decommission_instances([instance_id], errored=True)
                return True
        return False

    def inactive_ips(self):
        # These IPs belong to decomissioned instances and
        # specifically should not be doing anything. Note,
        # if ever change the decomissioned map to hold something
        # other than the set of IPs (as it is redunent), then
        # we will need to update this code.
        ips = []
        for instance_id in self.decommissioned.list():
            ips.extend(self.instance_ips.get(instance_id))
        for instance_id in self.errored.list():
            ips.extend(self.instance_ips.get(instance_id))
        return ips

    def active_ips(self, include_static=True):
        if include_static:
            # Return the current set of confirm and static IPs.
            return self.confirmed_ips.list() + self.config.static_ips()
        else:
            return self.confirmed_ips.list()

    def endpoint_ips(self):
        return self.active_ips(include_static=False) + self.inactive_ips()

    def backends(self):
        """
        Returns all backends associated with the endpoint.
        """
        def to_backend(ip):
            if ip.find(":") >= 0:
                (ip, port) = ip.split(":", 1)
                return lb_backend.Backend(
                    ip, int(port), self.config.weight)
            else:
                return lb_backend.Backend(
                    ip, self.config.port, self.config.weight)

        return map(to_backend, self.active_ips())

    def _mark_instance(self, instance_id, label, marks=None):
        """ Increments the mark counter. """
        if marks is None:
            marks = 1
        else:
            marks = math.ceil(marks)

        remove_instance = False
        mark_counters = self.zkobj.marked_instances().get(instance_id) or {}
        mark_counter = mark_counters.get(label, 0)
        mark_counter += marks

        max_counter = {
            "unregistered": self.config.unregistered_timeout,
            "decommissioned": self.config.decommissioned_timeout,
            "error": self.config.error_marks,
        }

        # Check that the label is valid.
        # It would be ideal if we could assert this as a
        # compile-time check or at least do some static check.
        if not label in max_counter:
            raise Exception("Unknown mark label: %s" % label)

        if mark_counter >= max_counter.get(label, 0):
            # This instance has been marked too many times. There is likely
            # something really wrong with it, so we'll clean it up.
            remove_instance = True
            self.zkobj.marked_instances().remove(instance_id)

        else:
            # Just save the mark counter.
            mark_counters[label] = mark_counter
            self.zkobj.marked_instances().add(instance_id, mark_counters)

        return remove_instance

    def reload(self, exclude=False):
        # Depending on whether or not we have a collect()
        # available (whether this object was created by a
        # scale manager or not), we will grab the set of ips
        # in different ways. If we have a collect(), then
        # we will it to ensure that all relevant endpoints are
        # included.
        # If not, then we use only our local active IPs to
        # construct a reasonable collection of IPs to send to
        # the loadbalancer.

        if not hasattr(self, '_collect'):
            return
        elif self._collect:
            ips = self._collect(self, exclude=exclude)
        elif exclude:
            ips = []
        else:
            ips = self.backends()

        try:
            self.lb_conn.change(self.config.url, ips, config=self.config)
            self.lb_conn.save()
            self.logging.info(self.logging.RELOADED)
        except NotImplementedError:
            # Oh well, just using the stub.
            pass
