#!/usr/bin/env python

import hashlib
import logging
import os
import traceback

import gridcentric.pancake.cloud.connection as cloud_connection
from gridcentric.pancake.config import ServiceConfig

import gridcentric.pancake.metrics.calculator as metric_calculator

class Service(object):
    
    def __init__(self, name, service_config, scale_manager):
        self.name = name
        self.config = service_config
        self.scale_manager = scale_manager
        self.url = self.config.url()
        self.cloud_conn = cloud_connection.get_connection('nova')
        self.cloud_conn.connect(self.config.auth_info()) 
        
    def key(self):
        return hashlib.md5(self.url).hexdigest()

    def manage(self):
        # Load the configuration and configure the service.
        logging.info("Managing service %s" % (self.name))
        pass
        
    def unmanage(self):
        # Delete all the launched instances, and unbless the instance. Essentially, return it
        # back to the unmanaged.
        logging.info("Unmanaging service %s" % (self.name))

        # Delete all the launched instances.
        for instance in self.instances():
            self.drop_instances(self.instances(), "service is becoming unmanaged") 

    def update(self, reconfigure=True, metrics=[]):
        try:
            self._update(reconfigure, metrics)
        except Exception, e:
            traceback.print_exc()
            logging.error("Error updating service %s: %s" % (self.name, str(e)))

    def _update(self, reconfigure, metrics):

        instances = self.instances()
        num_instances = len(instances)

        # Evaluate the metrics on these instances.
        ideal_num_instances = metric_calculator.caluculate_ideal_uniform(self.config.metrics(), metrics)
        logging.debug("Metrics for service %s: ideal_servers=%s (%s)" % (self.name, ideal_num_instances, metrics))
        
        allowable_num_instances = range(self.config.min_instances(), self.config.max_instances() +1)
        overlap = set(allowable_num_instances) & set(ideal_num_instances)
        if len(overlap) == 0:
            # Basically the ideal number of instances falls completely outside the allowable
            # range. This can mean 2 different things:
            ideal_num_instances.sort()
            if ideal_num_instances[0] > self.config.max_instances():
                # a. More instances are required than our maximum allowance
                overlap = set([self.config.max_instances()])
            else:
                # b. Less instances are required than our minimum allowance                
                overlap = set([self.config.min_instances()])
        
        if num_instances in overlap:
            # The number of instances we currently have is within the ideal range.
            target = num_instances
        else:
            # we need to either scale up or scale down. Our target will be the smallest
            # value in the ideal range.
            overlap = list(overlap)
            overlap.sort()
            target = overlap[len(overlap)/2]
        
        logging.debug("Target number of instances for service %s determined to be %s (current: %s)" 
                      % (self.name, target, num_instances))
        
        # Launch instances until we reach the min setting value.
        while num_instances < target:
            self._launch_instance("bringing instance total up to target %s" % target)
            num_instances += 1

        # Delete instances until we reach the max setting value.
        instances_to_delete = instances[target:]
        instances = instances[:target]

        self.drop_instances(instances_to_delete,
            "bringing instance total down to target %s" % target)
        
    def update_config(self, config_str):
        old_url = self.config.url()
        self.config.reload(config_str)
        if old_url != self.config.url():
            self._update_loadbalancer([])
        self.url = self.config.url()
        self.update()

    def drop_instances(self, instances, reason):
        """
        Drop the instances from the system. Note: a reason should be given for why
        the instances are being dropped.
        """
        
        # Update the load balancer before bringing down the instances.
        self._drop_addresses(instances)
        if len(instances) > 0:
            self._update_loadbalancer()

        # It might be good to wait a little bit for the servers to clear out any requests they
        # are currently serving.
        for instance in instances:
            logging.info("Shutting down instance %s for server %s (reason: %s)" %
                    (instance['id'], self.name, reason))
            self._delete_instance(instance)

    def _drop_addresses(self, instances):
        # Drops all the addresses associated with these instances.
        for address in self.extract_addresses_from(instances):
            self.scale_manager.drop_ip(self.name, address)

    def _delete_instance(self, instance):
        # Delete the instance from nova            
        self.cloud_conn.delete_instance(instance['id'])

    def _launch_instance(self, reason):
        # Launch the instance.
        logging.info(("Launching new instance for server %s " +
                     "(reason: %s)") %
                     (self.name, reason))
        self.cloud_conn.start_instance(self.name, self.config.instance_id())

    def service_url(self):
        return self.url

    def static_addresses(self):
        return self.config.static_ips()

    def instances(self):
        return self.cloud_conn.list_instances(self.config.instance_id())
    
    def addresses(self):
        return self.extract_addresses_from(self.instances())

    def extract_addresses_from(self, instances):
       addresses = []
       for instance in instances:
           for network_addresses in instance.get('addresses', {}).values():
               for network_addrs in network_addresses:
                   addresses.append(network_addrs['addr'])
       return addresses
   
    def _update_loadbalancer(self, addresses = None):
        self.scale_manager.update_loadbalancer(self, addresses)

    def health_check(self):
        instances = self.instances()

        # Check if any expected machines have failed to come up and confirm their IP address.
        confirmed_ips = self.scale_manager.confirmed_ips(self.name)

        dead_instances = []
        for instance in instances:
            expected_ips = self.extract_addresses_from([instance])
            # As long as there is one expected_ip in the confirmed_ip, everything is good. Otherwise
            # This instance has not checked in. We need to mark it, and it if has enough marks
            # it will be destroyed.
            logging.info("expected ips=%s, confirmed ips=%s" % (expected_ips, confirmed_ips))
            if len( set(expected_ips) & set(confirmed_ips) ) == 0:
                # The expected ips do no intersect with the confirmed ips.
                # This instance should be marked.
                if self.scale_manager.mark_instance(self.name, instance['id']):
                    # This instance has been deemed to be dead and should be cleaned up.
                    dead_instances += [instance]

        # We assume they're dead, so we can prune them.
        self.drop_instances(dead_instances, "instance has been marked for destruction")
