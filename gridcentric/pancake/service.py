import hashlib
import logging
import os
import traceback
import socket

import gridcentric.pancake.cloud.connection as cloud_connection
from gridcentric.pancake.config import ServiceConfig

import gridcentric.pancake.metrics.calculator as metric_calculator

class Service(object):

    def __init__(self, name, service_config, scale_manager, cloud='nova'):
        self.name = name
        self.config = service_config
        self.scale_manager = scale_manager
        self.cloud_conn = cloud_connection.get_connection(cloud)
        self.cloud_conn.connect(self.config.auth_info())

    def key(self):
        return hashlib.md5(self.config.url()).hexdigest()

    def manage(self):
        # Load the configuration and configure the service.
        logging.info("Managing service %s" % (self.name))
        self.decommissioned_instances = self.scale_manager.decommissioned_instances(self.name)

    def unmanage(self):
        try:
            # Delete all the launched instances, and unbless the instance.
            # Essentially, return it back to the unmanaged.
            logging.info("Unmanaging service %s" % (self.name))

            # Delete all the launched instances.
            for instance in self.instances():
                self.decommission_instances(self.instances(),
                                    "service is becoming unmanaged")
        except:
            logging.error("Error unmanaging service %s: %s" % (self.name, traceback.format_exc()))

    def update(self, reconfigure=True, metrics=[]):
        try:
            self._update(reconfigure, metrics)
        except:
            logging.error("Error updating service %s: %s" % (self.name, traceback.format_exc()))

    def _determine_target_instances_range(self, metrics, num_instances):
        """
        Determine the range of instances that we need to scale to. A tuple of the
        form (min_instances, max_instances) is returned.
        """

        # Evaluate the metrics on these instances and get the ideal bounds on the number
        # of servers that should exist.
        ideal_min, ideal_max = metric_calculator.calculate_ideal_uniform(\
                self.config.metrics(), metrics, num_instances)
        logging.debug("Metrics for service %s: ideal_servers=%s (%s)" % \
                (self.name, (ideal_min, ideal_max), metrics))

        if ideal_max < ideal_min:
            # Either the metrics are undefined or have conflicting answers. We simply
            # return this conflicting result.
            if metrics != []:
                # Only log the warning if there were values for the metrics provided. In other words
                # only if the metrics could have made a difference.
                logging.warn("Either no metrics have been defined for service %s or they have "
                             "resulted in a conflicting result. (service metrics: %s)"
                             % (self.name, self.config.metrics()))
            return (ideal_min, ideal_max)

        # Grab the allowable bounds of the number of servers that should exist.
        config_min = self.config.min_instances()
        config_max = self.config.max_instances()

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

    def _update(self, reconfigure, metrics):
        instances = self.instances()
        num_instances = len(instances)
        num_confirmed_instances = len(self.scale_manager.confirmed_ips(self.name))

        (target_min, target_max) = \
                self._determine_target_instances_range(metrics, num_confirmed_instances)

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

        logging.debug("Target number of instances for service %s determined to be %s (current: %s)"
                      % (self.name, target, num_instances))

        # Launch instances until we reach the min setting value.
        while num_instances < target:
            self._launch_instance("bringing instance total up to target %s" % target)
            num_instances += 1

        # Delete instances until we reach the max setting value.
        instances_to_delete = instances[target:]
        instances = instances[:target]

        self.decommission_instances(instances_to_delete,
            "bringing instance total down to target %s" % target)

    def update_config(self, config_str):
        # Check if our configuration is about to change.
        old_url = self.config.url()
        old_static_addresses = self.config.static_ips()
        old_auth_info = self.config.auth_info()
        new_config = ServiceConfig(config_str)
        new_url = new_config.url()
        new_static_addresses = new_config.static_ips()
        new_auth_info = new_config.auth_info()

        # Remove all old instances from loadbalancer.
        if old_url != new_url:
            self.scale_manager.remove_service(self.name)

        # Reload the configuration.
        self.config.reload(config_str)

        # Reconnect to the cloud controller (if necessary).
        if old_auth_info != new_auth_info:
            self.cloud_conn = cloud_connection.get_connection(cloud)
            self.cloud_conn.connect(self.config.auth_info())

        # Do a referesh (to capture the new service).
        if old_url != new_url:
            self.scale_manager.add_service(self)
        elif old_static_addresses != new_static_addresses:
            self._update_loadbalancer()

        # Run a full update.
        self.update()

    def decommission_instances(self, instances, reason):
        """
        Drop the instances from the system. Note: a reason should be given for why
        the instances are being dropped.
        """

        # Update the load balancer before bringing down the instances.
        self._decommission_addresses(instances)
        if len(instances) > 0:
            self._update_loadbalancer()

        # It might be good to wait a little bit for the servers to clear out
        # any requests they are currently serving.
        for instance in instances:
            logging.info("Decommissioning instance %s for server %s (reason: %s)" %
                    (instance['id'], self.name, reason))
            self.scale_manager.decommission_instance(self.name, instance['id'], self.extract_addresses_from([instance]))
            self.decommissioned_instances += [str(instance['id'])]

    def _decommission_addresses(self, instances):
        # Drops all the addresses associated with these instances.
        for address in self.extract_addresses_from(instances):
            self.scale_manager.drop_ip(self.name, address)

    def _delete_instance(self, instance_id):
        # Delete the instance from nova
        logging.info("Deleting instance %s for server %s" % (instance_id, self.name))
        self.cloud_conn.delete_instance(instance_id)
        self.scale_manager.drop_decommissioned_instance(self.name, instance_id)
        try:
            self.decommissioned_instances.remove(instance_id)
        except:
            # An exception is thrown if we are unable to remove it. This is fine because
            # we are trying to remove it anyway.
            pass

    def _launch_instance(self, reason):
        # Launch the instance.
        logging.info(("Launching new instance for server %s " +
                     "(reason: %s)") %
                     (self.name, reason))
        self.cloud_conn.start_instance(self.name, self.config.instance_id())

    def service_url(self):
        return self.config.url()

    def static_addresses(self):
        return self.config.static_ips()

    def instances(self, filter=True):
        instances = self.cloud_conn.list_instances(self.config.instance_id())

        if filter:
            # Filter out the decommissioned instances from the returned list.
            all_instances = instances
            instances = []
            for instance in all_instances:
                if not(str(instance['id']) in self.decommissioned_instances):
                    instances.append(instance)

        return instances

    def addresses(self):
        return self.extract_addresses_from(self.instances())

    def extract_addresses_from(self, instances):
        addresses = []
        for instance in instances:
            for network_addresses in instance.get('addresses', {}).values():
                for network_addrs in network_addresses:
                    addresses.append(network_addrs['addr'])
        return addresses

    def _update_loadbalancer(self, remove=False):
        self.scale_manager.update_loadbalancer(self, remove=remove)

    def health_check(self, active_ips):
        instances = self.instances(filter=False)

        # Check if any expected machines have failed to come up and confirm
        # their IP address.
        confirmed_ips = set(self.scale_manager.confirmed_ips(self.name))

        dead_instances = []

        # There are the confirmed ips that are actually associated with an
        # instance. Other confirmed ones will need to be dropped because the
        # instances they refer to no longer exists.
        associated_confirmed_ips = set()
        inactive_instance_ids = []
        for instance in instances:
            expected_ips = set(self.extract_addresses_from([instance]))
            # As long as there is one expected_ip in the confirmed_ip,
            # everything is good. Otherwise This instance has not checked in.
            # We need to mark it, and it if has enough marks it will be
            # destroyed.
            logging.info("expected ips=%s, confirmed ips=%s" % (expected_ips, confirmed_ips))
            instance_confirmed_ips = confirmed_ips.intersection(expected_ips)
            if len(instance_confirmed_ips) == 0:
                # The expected ips do no intersect with the confirmed ips.
                # This instance should be marked.
                if self.scale_manager.mark_instance(self.name, instance['id']):
                    # This instance has been deemed to be dead and should be cleaned up.
                    dead_instances += [instance]
            else:
                associated_confirmed_ips = associated_confirmed_ips.union(instance_confirmed_ips)

            # Check if any of these expected_ips are not in our active set. If so that this instance
            # is currently considered inactive
            if len(expected_ips.intersection(active_ips)) == 0:
                inactive_instance_ids += [str(instance['id'])]

        # TODO(dscannell) We also need to ensure that the confirmed IPs are
        # still valid. In other words, we have a running instance with the
        # confirmed IP.
        orphaned_confirmed_ips = confirmed_ips.difference(associated_confirmed_ips)

        if len(orphaned_confirmed_ips) > 0:
            # There are orphaned ip addresses. We need to drop them and then
            # update the load balancer because there is no actual instance
            # backing them.
            logging.info("Dropping ip addresses %s for service %s because they do not have"
                         "backing instances." % (orphaned_confirmed_ips, self.name))
            for orphaned_address in orphaned_confirmed_ips:
                self.scale_manager.drop_ip(self.name, orphaned_address)
            self._update_loadbalancer()

        # We assume they're dead, so we can prune them.
        self.decommission_instances(dead_instances, "instance has been marked for destruction")

        # See if there are any decommissioned instances that are now inactive.
        decommissioned_instance_ids = self.decommissioned_instances
        logging.debug("Active instances: %s:%s:%s" % (active_ips, inactive_instance_ids, decommissioned_instance_ids))
        for inactive_instance_id in inactive_instance_ids:
            if inactive_instance_id in decommissioned_instance_ids:
                self._delete_instance(inactive_instance_id)
