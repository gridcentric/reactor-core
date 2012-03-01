#!/usr/bin/env python

import hashlib
import logging
import os
import traceback

from gridcentric.nova.client.client import NovaClient
from gridcentric.pancake.config import ServiceConfig

class Service(object):
    
    def __init__(self, name, service_config, scale_manager):
        self.name = name
        self.config = service_config
        self.scale_manager = scale_manager
        self.novaclient = None
        self.confirmed_addresses = {}
    
    def key(self):
        return hashlib.md5(self.config.get("service","url")).hexdigest()
    
    def manage(self):
        # Load the configuration and configure the service.
        logging.info("Managing service %s" % (self.name))
        self._configure()
        
        # We need to ensure that the instance is blessed. This is simply done by
        # sending the bless command.
        try:
            logging.info("Blessing instance id=%s for service %s" % (self.config.get("nova","instance_id"), self.name))
            self.novaclient.bless_instance(self.config.get("nova","instance_id"))
        except Exception, e:
            # There is a chance that this instance was already blessed. This is not
            # an issue, so we just need to ignore. There is also a chance that we could
            # not connected to nova, or there is some error. In any event, we can't do much
            # so let's log a warning.
            logging.warn("Failed to bless a service instance (service=%s, instances_id=%s). Error=%s" 
                         % (self.name, self.config.get("nova","instance_id"), e) )

    def unmanage(self):
        # Delete all the launched instances, and unbless the instance. Essentially, return it
        # back to the unmanaged.
        logging.info("Unmanaging service %s" % (self.name))
        self._configure()
        
        # Delete all the launched instances.
        for instance in self.instances():
            self.drop_instances(self.instances(), "service is becoming unmanaged")
        
        logging.info("Unblessing instance id=%s for service %s" %
                (self.config.get("nova","instance_id"), self.name))
        self.novaclient.unbless_instance(self.config.get("nova","instance_id")) 

    def update(self, reconfigure=True):
        try:
            self._update(reconfigure)
        except Exception, e:
            traceback.print_exc()
            logging.error("Error updating service %s: %s" % (self.name, str(e)))

    def _update(self, reconfigure):
        if reconfigure:
            self._configure()

        instances = self.instances()
        num_instances = len(instances)

        # Launch instances until we reach the min setting value.
        while num_instances < int(self.config.get("scaling","min_instances")):
            logging.info(("Launching new instance for server %s " +
                         "(reason: bringing minimum instances up to %s)") %
                         (self.name, self.config.get("scaling","min_instances")))
            self._launch_instance()
            num_instances += 1

        # Delete instances until we reach the max setting value.
        instances_to_delete = instances[int(self.config.get("scaling","max_instances")):]
        instances = instances[:int(self.config.get("scaling","max_instances"))]
        
        self.drop_instances(instances_to_delete,
            "bringing maximum instance down to %s" % self.config.get("scaling","max_instances"))

    def update_config(self, config_str):
        self.config.reload(config_str)
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
        self.novaclient.delete_instance(instance['id'])
        
    def _launch_instance(self):
        # Launch the instance.
        self.novaclient.launch_instance(self.config.get("nova","instance_id"))
        
    
    def _configure(self):
        try:
            self.novaclient = NovaClient(self.config.get("nova","authurl"), \
                                         self.config.get("nova","user"), \
                                         self.config.get("nova","apikey"),
                                         self.config.get("nova","project"), 'v1.1')
        except Exception, e:
            traceback.print_exc()
            logging.error("Error creating nova client: %s" % str(e))

    def service_url(self):
        return self.config.get("service","url")
    
    def static_addresses(self):
        return self.config.get("service","static_instances").split(",")
    
    def instances(self):
        return self.novaclient.list_launched_instances(self.config.get("nova","instance_id"))

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
        # Check if any expected machines have failed to come up and confirm their IP address.
        instances = self.instances()
        confirmed_ips = self.scale_manager.confirmed_ips(self.name)
        
        dead_instances = []
        for instance in instances:
            expected_ips = self.extract_addresses_from([instance])
            # As long as there is one expected_ip in the confirmed_ip, everything is good. Otherwise
            # This instance has not checked in. We need to mark it, and it if has enough marks
            # it will be destroyed.
            logging.info("expected ips=%s, confirmed ips=%s" % (expected_ips, confirmed_ips))
            if len( set(expected_ips) & set(confirmed_ips) ) == 0:
                # The expected ips do no intersect with the confirmed ips. This instance should
                # be marked.
                if self.scale_manager.mark_instance(self.name, instance['id']):
                    #This instance has been deemed to be dead and should be cleaned up.
                    dead_instances += [instance]
        self.drop_instances(dead_instances, "instance has been marked for destruction.")
        


