
import logging

from gridcentric.nova.client import NovaClient
from gridcentric.scalemanager.serviceconfig import ServiceConfig

class Service(object):
    
    BASE_PATH="/home/dscannell/projects/gridcentric/cloud/scalemanager/testenv"
    
    def __init__(self, name):
        self.name = name
        self.config = ServiceConfig(self.BASE_PATH + "/" + self.name)
        self.config.listen(self.name, self._update)
        self.novaclient = None
        
        self.config.load()
        
    
    def _update(self):
        self._configure()
        
        instances = self.instances()
        num_instances = len(instances)
        
        # Launch instances until we reach the min setting value.
        while num_instances < int(self.config.min_instances):
            logging.info("Launching new instance for server %s (current server num: %s)" % (self.name, num_instances))
            self.novaclient.launch_instance(self.config.nova_instanceid)
            num_instances += 1
        
        # Delete instances until we reach the max setting value.
        while num_instances > int(self.config.max_instances):
            logging.info("Shutting down instance for server %s (current server num: %s)" % (self.name, num_instances))
            self.novaclient.delete_instance(instances[-1]['id'])
            instances = instances[0:-1]
            num_instances -= 1
    
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