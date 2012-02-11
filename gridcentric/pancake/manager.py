#!/usr/bin/env python

import ConfigParser
import logging
import threading
import time
import uuid
from StringIO import StringIO

from gridcentric.pancake.config import ManagerConfig, ServiceConfig
from gridcentric.pancake.service import Service
from gridcentric.pancake.zookeeper.connection import ZookeeperConnection
import gridcentric.pancake.zookeeper.paths as paths


class pancake(object):
    
    def __init__(self):
        self.uuid = uuid.uuid4()
        self.services = {}
        self.watching_ips ={}
    
    def serve(self, zk_servers):
        # Create a connection to zk_configuration and read
        # in the pancake service config
        
        self.zk_conn = ZookeeperConnection(zk_servers)
        manager_config = self.zk_conn.read(paths.config)
        self.config = ManagerConfig(manager_config)
        
        self.zk_conn.watch_children(paths.new_ips, self.register_ip)
        self.service_change(
                    self.zk_conn.watch_children(paths.services, self.service_change)) 
    
    def service_change(self, services):
        
        logging.info("Services have changed: new=%s, existing=%s" %(services, self.services.keys()))
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
        
        service_path  = paths.service(service_name)
        service_config = ServiceConfig(self.zk_conn.read(service_path))
        service = Service(service_name, service_config, self)
        self.services[service_name] = service
        
        if self.zk_conn.read(paths.service_managed(service_name)) == None:
            logging.info("New service %s found to be managed." %(service_name))
            # This service is currently unmanaged.
            service.manage()
            self.zk_conn.write(paths.service_managed(service_name),"True")
        
        service.update()
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

    def confirmed_ips(self, service_name):
        """
        Returns a list of all the confirmed ips for the the service.
        """
        ips = self.zk_conn.list_children(paths.confirmed_ips(service_name))
        if ips == None:
            ips = []
        return ips

    def drop_ip(self, service_name, ip_address):
        self.zk_conn.delete(paths.confirmed_ip(service_name, ip_address))

    def register_ip(self, ips):
        
        delete_watches = []
        for service in self.services.values():
            service_ips = service.addresses()
            for ip in ips:
                if ip in service_ips:
	            logging.info("service %s found for IP %s" %(service.name, ip))
                    # We found the service that this IP address belongs. Confirm this IP address
                    # and remove it from the new-ip address. Finally update the loadbalancer.
                    self.zk_conn.write(paths.confirmed_ip(service.name, ip), "")
                    self.zk_conn.delete(paths.new_ip(ip))
                    service.update_loadbalancer()

    def mark_instance(self, service_name, instance_id):
        
        remove_instance=False
        mark_counter = int(self.zk_conn.read(paths.marked_instance(service_name, instance_id), '0'))
        # Increment the mark counter
        mark_counter += 1
        if mark_counter >= int(self.config.mark_maximum):
            # This instance has been marked too many times. There is likely something really
            # wrong with it, so we'll clean it up.
            remove_instance=True
        else:
            # Just save the mark counter
            logging.info("Instance %s for servicve %s has been marked (count=%s)" %(instance_id, service_name, mark_counter))
            self.zk_conn.write(paths.marked_instance(service_name, instance_id), str(mark_counter))
        
        return remove_instance

    def health_check(self):
        # Does a health check on all the services that are being managed.
        for service in self.services.values():
            service.health_check()
            service.update(reconfigure=False)

    def run(self):
        while True:
            time.sleep(float(self.config.health_check))
            self.health_check()

