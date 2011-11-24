
import ConfigParser
import logging
from StringIO import StringIO
import threading
import time
import uuid

from gridcentric.scalemanager.config import ManagerConfig, ServiceConfig
from gridcentric.scalemanager.service import Service
from gridcentric.scalemanager.zookeeper.connection import ZookeeperConnection


class ScaleManager(object):
    
    def __init__(self):
        self.uuid = uuid.uuid4()
        self.services = {}
    
    def serve(self, zk_servers):
        # Create a connection to zk_configuration and read
        # in the ScaleManager service config
        
        self.zk_conn = ZookeeperConnection(zk_servers)
        manager_config = self.zk_conn.read("/gridcentric/scalemanager/config")
        self.config = ManagerConfig(manager_config)
        
        self.service_change(
                    self.zk_conn.watch_children("/gridcentric/scalemanager/service", self.service_change)) 
    
    def service_change(self, services):
        for service_name in services:
            if service_name not in self.services:
                self.create_service(service_name)
        
        services_to_remove = []
        for service_name in self.services:
            if service_name not in services:
                self.remove_service(service_name)
                services_to_remove += [service_name]
        
        for service in services_to_remove:
            del self.services[service]

    def create_service(self, service_name):
        
        logging.info("Assigning service %s to manager %s" %(service_name, self.uuid))
        
        service_path  = "/gridcentric/scalemanager/service/%s" % (service_name)
        service_config = ServiceConfig(self.zk_conn.read(service_path))
        service = Service(service_name, service_config)
        self.services[service_name] = service
        
        if self.zk_conn.read("%s/managed" % (service_path)) == None:
            logging.info("New service %s found to be managed." %(service_name))
            # This service is currently unmanaged.
            service.manage()
            self.zk_conn.write("%s/managed" % (service_path),"True")
        
        self.zk_conn.watch_contents(service_path, service.update_config)
            
    
    def remove_service(self, service_name):
        """
        This removes / unmanages the service.
        """
        logging.info("Removing service %s from manager %s" %(service_name, self.uuid))
        service = self.services.get(service_name, None)
        if service:
            logging.info("Unmanaging service %s" %(service_name))
            service.unmanage()

    def run(self):
        while True:
            time.sleep(86400)
        
if __name__ == "__main__":
    manager = ScaleManager(['localhost:2181'])
    manager.start()
    manaager.join()