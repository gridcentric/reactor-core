#!/usr/bin/env python

import ConfigParser
import logging
import threading
import time
import uuid
from StringIO import StringIO

from gridcentric.pancake.config import ManagerConfig, ServiceConfig
from gridcentric.pancake.service import Service
import gridcentric.pancake.loadbalancer.connection as lb_connection
from gridcentric.pancake.zookeeper.connection import ZookeeperConnection
import gridcentric.pancake.zookeeper.paths as paths

class ScaleManager(object):

    def __init__(self):
        self.uuid = uuid.uuid4()
        self.services = {}
        self.key_to_services = {}
        self.ip_mappings = {}
        self.watching_ips ={}
        self.load_balancer = None

    def serve(self, zk_servers):
        # Create a connection to zk_configuration and read
        # in the pancake service config
        self.zk_conn = ZookeeperConnection(zk_servers)
        manager_config = self.zk_conn.read(paths.config())
        self.config = ManagerConfig(manager_config)
        self.load_balancer = lb_connection.get_connection(self.config.config_path(), self.config.site_path())
        self.zk_conn.watch_children(paths.new_ips(), self.register_ip)
        self.service_change(self.zk_conn.watch_children(paths.services(), self.service_change))
 
    def service_change(self, services):
        logging.info("Services have changed: new=%s, existing=%s" %
                     (services, self.services.keys()))
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
        logging.info("Assigning service %s to manager %s." % (service_name, self.uuid))

        service_path  = paths.service(service_name)
        service_config = ServiceConfig(self.zk_conn.read(service_path))
        service = Service(service_name, service_config, self)
        self.services[service_name] = service
        service_key = service.key()
        self.key_to_services[service_key] = \
            self.key_to_services.get(service.key(),[]) + [service_name]

        if self.zk_conn.read(paths.service_managed(service_name)) == None:
            logging.info("New service %s found to be managed." % (service_name))
            # This service is currently unmanaged.
            service.manage()
            self.zk_conn.write(paths.service_managed(service_name),"True")

        service.update()
        self.update_ip_map(service)

        logging.info("Watching service %s." % (service_name))
        self.zk_conn.watch_contents(service_path, service.update_config)

    def remove_service(self, service_name):
        """
        This removes / unmanages the service.
        """
        logging.info("Removing service %s from manager %s" % (service_name, self.uuid))
        service = self.services.get(service_name, None)
        if service:
            logging.info("Unmanaging service %s" %(service_name))
            service_names = self.key_to_services.get(service.key(), [])
            if service_name in service_names:
                # Remove the service name from the list of services with the same key. If the service
                # name is not in the list, then it is fine because we are just removing it anyway.
                service_names.remove(service_name)
            service.unmanage()

    def update_ip_map(self, service):
        # Update the expected IP mappings.
        for address in service.addresses():
            self.ip_mappings[address] = service
            logging.debug("Assigning ip address %s to service %s" % (address, service.name))
        for address in service.static_addresses():
            self.ip_mappings[address] = service

    def confirmed_ips(self, service_name):
        """
        Returns a list of all the confirmed ips for the service.
        """
        ips = self.zk_conn.list_children(paths.confirmed_ips(service_name))
        if ips == None:
            ips = []
        return ips

    def drop_ip(self, service_name, ip_address):
        self.zk_conn.delete(paths.confirmed_ip(service_name, ip_address))

    def register_ip(self, ips):
        def _register_ip(scale_manager, service, ip):
            logging.info("Service %s found for IP %s" % (service.name, ip))
            # We found the service that this IP address belongs. Confirm this IP address
            # and remove it from the new-ip address. Finally update the loadbalancer.
            scale_manager.zk_conn.write(paths.confirmed_ip(service.name, ip), "")
            scale_manager.zk_conn.delete(paths.new_ip(ip))
            scale_manager.update_loadbalancer(service)

        for ip in ips:
            # Check if we know the mapping.
            if ip in self.ip_mappings:
                _register_ip(self, self.ip_mappings[ip], ip)

            # Look up the mapping dynamically.
            else:
                for service in self.services.values():
                    service_ips = service.addresses()
                    if ip in service_ips:
                        _register_ip(self, service, ip)
                        break

    def update_loadbalancer(self, service, addresses = None):
        if addresses == None:
            addresses = []
            for service_name in self.key_to_services.get(service.key(), []):
                addresses += self.confirmed_ips(service_name)
                addresses += self.services[service_name].static_addresses()
        logging.info("Updating loadbalancer for url %s with addresses %s" %
                     (service.service_url(), addresses))
        self.load_balancer.change(service.service_url(), addresses)
        self.load_balancer.save()

    def reload_loadbalancer(self):
        self.load_balancer.clear()
        for service in self.services.values():
            addresses = []
            for service_name in self.key_to_services.get(service.key(), []):
            	addresses += self.confirmed_ips(service_name)
                addresses += self.services[service_name].static_addresses()
            self.load_balancer.change(service.service_url(), addresses)
            self.update_ip_map(service)
        self.load_balancer.save()

    def mark_instance(self, service_name, instance_id):
        remove_instance = False
        mark_counter = int(self.zk_conn.read(paths.marked_instance(service_name, instance_id), '0'))

        # Increment the mark counter
        mark_counter += 1

        if mark_counter >= self.config.mark_maximum():
            # This instance has been marked too many times. There is likely something really
            # wrong with it, so we'll clean it up.
            remove_instance = True
            self.zk_conn.delete(paths.marked_instance(service_name, instance_id))
        else:
            # Just save the mark counter
            logging.info("Instance %s for service %s has been marked (count=%s)" %
                         (instance_id, service_name, mark_counter))
            self.zk_conn.write(paths.marked_instance(service_name, instance_id), str(mark_counter))

        return remove_instance

    def health_check(self):
        # Update all the service metrics from the loadbalancer.
        metrics = self.load_balancer.metrics()
        metrics_by_key = {}
        for ip in metrics:
            if ip in self.ip_mappings:
                service = self.ip_mappings[ip]
                if not(service.key() in metrics_by_key):
                    metrics_by_key[service.key()] = []
                metrics_by_key[service.key()].append(metrics[ip])

        # Does a health check on all the services that are being managed.
        for service in self.services.values():
            # Run a health check on this service.
            service.health_check()

            # Do the service update.
            service.update(reconfigure=False, metrics=metrics_by_key.get(service.key(), []))
            self.update_ip_map(service)

    def run(self):
        # Kick the loadbalancer on startup.
        self.reload_loadbalancer()

        while True:
            time.sleep(self.config.health_check())
            self.health_check()
