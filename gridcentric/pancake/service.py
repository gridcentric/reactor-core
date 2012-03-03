#!/usr/bin/env python

import hashlib
import logging
import os
import traceback

from httplib import HTTPException
from gridcentric.nova.client.client import NovaClient
from gridcentric.pancake.config import ServiceConfig

class Service(object):
    
    def __init__(self, name, service_config, scale_manager):
        self.name = name
        self.config = service_config
        self.scale_manager = scale_manager
        self.novaclient = None
        self.instance_cache = None
        self.confirmed_addresses = {}
        self.url = self.config.url()

    def key(self):
        return hashlib.md5(self.url).hexdigest()

    def manage(self):
        # Load the configuration and configure the service.
        logging.info("Managing service %s" % (self.name))
        self._configure()
        
        # We need to ensure that the instance is blessed. This is simply done by
        # sending the bless command.
        try:
            logging.info("Blessing instance id=%s for service %s" %
                         (self.config.instance_id(), self.name))
            self.novaclient.bless_instance(self.config.instance_id())

        except Exception, e:
            # There is a chance that this instance was already blessed. This is not
            # an issue, so we just need to ignore. There is also a chance that we could
            # not connected to nova, or there is some error. In any event, we can't do much
            # so let's log a warning.
            logging.warn("Failed to bless a service instance (service=%s, instances_id=%s). "
                         "Error=%s" % (self.name, self.config.instance_id(), e) )

    def unmanage(self):
        # Delete all the launched instances, and unbless the instance. Essentially, return it
        # back to the unmanaged.
        logging.info("Unmanaging service %s" % (self.name))
        self._configure()
        
        # Delete all the launched instances.
        for instance in self.instances():
            self.drop_instances(self.instances(), "service is becoming unmanaged")

        logging.info("Unblessing instance id=%s for service %s" %
                (self.config.instance_id(), self.name))
        self.novaclient.unbless_instance(self.config.instance_id()) 

    def update(self, reconfigure=True, metrics=[]):
        try:
            self._update(reconfigure, metrics)
        except Exception, e:
            traceback.print_exc()
            logging.error("Error updating service %s: %s" % (self.name, str(e)))

    def _update(self, reconfigure, metrics):
        if reconfigure:
            self._configure()

        instances = self.instances()
        num_instances = len(instances)

        # Evaluate the metrics on these instances.
        metric_eval = self.config.metrics()
        metric_total = metric_eval(metrics)

        # Launch instances until we reach the min setting value.
        while num_instances < self.config.min_instances():
            logging.info(("Launching new instance for server %s " +
                         "(reason: bringing minimum instances up to %s)") %
                         (self.name, self.config.min_instances()))
            self._launch_instance()
            metric_total -= 1
            num_instances += 1

        # Bring up instances to satisfy our metrics.
        while metric_total > 0 and \
              num_instances < self.config.max_instances():
            logging.info(("Launching new instance for server %s " +
                         "(reason: metrics need %s new instances)") %
                         (self.name, metric_total))
            self._launch_instance()
            metric_total -= 1
            num_instances += 1

        # Bring down the max according to the metrics.
        max_instances = self.config.max_instances()
        while metric_total < 0 and max_instances > self.config.min_instances():
            max_instances -= 1
            metric_total += 1

        # Delete instances until we reach the max setting value.
        instances_to_delete = instances[max_instances:]
        instances = instances[:max_instances]

        self.drop_instances(instances_to_delete,
            "bringing maximum instance down to %s" % max_instances)

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
            logging.info("Shutting down instance %s for server %s (%s)" %
                    (instance['id'], self.name, reason))
            self._delete_instance(instance)

    def _drop_addresses(self, instances):
        # Drops all the addresses associated with these instances.
        for address in self.extract_addresses_from(instances):
            self.scale_manager.drop_ip(self.name, address)

    def _delete_instance(self, instance):
        # Delete the instance from nova            
        try:
            self.instance_cache = None
            self.novaclient.delete_instance(instance['id'])
        except HTTPException, e:
            traceback.print_exc()
            logging.error("Error deleting instance: %s" % str(e))

    def _launch_instance(self):
        # Launch the instance.
        try:
            self.instance_cache = None
            self.novaclient.launch_instance(self.config.instance_id())
        except HTTPException, e:
            traceback.print_exc()
            logging.error("Error launching instance: %s" % str(e))

    def _configure(self):
        try:
            authparams = self.config.auth_info()
            self.novaclient = NovaClient(authparams[0],
                                         authparams[1],
                                         authparams[2],
                                         authparams[3],
                                         'v1.1')
        except Exception, e:
            traceback.print_exc()
            logging.error("Error creating nova client: %s" % str(e))

    def service_url(self):
        return self.url

    def static_addresses(self):
        return self.config.static_ips()

    def instances(self):
        if self.instance_cache:
            return self.instance_cache
        else:
            try:
                self.instance_cache = \
                    self.novaclient.list_launched_instances(self.config.instance_id())
            except HTTPException:
                return []
        return self.instance_cache

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

        # Launch instances to replace our dead ones.
        for instance in dead_instances:
            self._launch_instance()

        # We assume they're dead, so we can prune them.
        self.drop_instances(dead_instances, "instance has been marked for destruction")
