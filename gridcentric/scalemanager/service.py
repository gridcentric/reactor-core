
import hashlib
import logging
import os

from gridcentric.nova.client.client import NovaClient
from gridcentric.scalemanager.serviceconfig import ServiceConfig
import gridcentric.scalemanager.loadbalancer.connection as lb_connection

class Service(object):
    
    BASE_PATH="/home/dscannell/projects/gridcentric/cloud/scalemanager/testenv"
    
    def __init__(self, name, service_config, scale_manager):
        self.name = name
        self.config = service_config
        self.scale_manager = scale_manager
        self.novaclient = None
        self.lb_conn = lb_connection.get_connection(os.path.join(self.BASE_PATH, "nginx.conf.d", "%s.conf" %(self.name)))

    def manage(self):
        # Load the configuration and configure the service.
        logging.info("Managing service %s" % (self.name))
        self._configure()
        
        # We need to ensure that the instance is blessed. This is simply done by
        # sending the bless command.
        try:
            logging.info("Blessing instance id=%s for service %s" % (self.config.nova_instanceid, self.name))
            self.novaclient.bless_instance(self.config.nova_instanceid)
        except Exception, e:
            # There is a chance that this instance was already blessed. This is not
            # an issue, so we just need to ignore. There is also a chance that we could
            # not connected to nova, or there is some error. In any event, we can't do much
            # so let's log a warning.
            logging.warn("Failed to bless a service instance (service=%s, instances_id=%s). Error=%s" 
                         % (self.name, self.config.nova_instanceid, e) )

    def unmanage(self):
        # Delete all the launched instances, and unbless the instance. Essentially, return it
        # back to the unmanaged.
        logging.info("Unmanaging service %s" % (self.name))
        self._configure()
        
        # Delete all the launched instances.
        for instance in self.instances():
            logging.info("Deleting launched instance %s (id=%s) for service %s" % (instance['name'],instance['id'], self.name))
            self.novaclient.delete_instance(instance['id'])
        
        logging.info("Unblessing instance id=%s for service %s" % (self.config.nova_instanceid, self.name))
        self.novaclient.unbless_instance(self.config.nova_instanceid) 

    def update(self):
        self._configure()
        
        instances = self.instances()
        num_instances = len(instances)
        
        # Launch instances until we reach the min setting value.
        while num_instances < int(self.config.min_instances):
            logging.info("Launching new instance for server %s (current server num: %s)" % (self.name, num_instances))
            self._launch_instance()
            num_instances += 1
        
        # Delete instances until we reach the max setting value.
        while num_instances > int(self.config.max_instances):
            logging.info("Shutting down instance for server %s (current server num: %s)" % (self.name, num_instances))
            self.novaclient.delete_instance(instances[-1]['id'])
            instances = instances[0:-1]
            num_instances -= 1
    
    def update_config(self, config_str):
        self.config.reload(config_str)
        self.update()
    
    def _launch_instance(self):
        # Notify the ScaleManager that we are launching a new instance, and that we are expecting
        # an IP address to be pinged back.
        
        self.scale_manager.watch_for_new_ip(self)
        # Launch the instance.
        self.novaclient.launch_instance(self.config.nova_instanceid)
        
    
    def _configure(self):
        self.novaclient = NovaClient(self.config.nova_authurl, self.config.nova_user, \
                                     self.config.nova_apikey, self.config.nova_project, 'v1.1')
    def service_url(self):
        return self.config.service_url
    
    def instances(self):
        return self.novaclient.list_launched_instances(self.config.nova_instanceid)
    
    def addresses(self):
        addresses = []
        for instance in self.instances():
            for network_addresses in instance.get('addresses', {}).values():
                for network_addrs in network_addresses:
                    addresses.append(network_addrs['addr'])
        return addresses
   
    def update_loadbalancer(self):
        self.lb_conn.update(self.config.service_url, self.addresses())