#!/usr/bin/env python

import ConfigParser
import logging
import threading
import time
import uuid
import hashlib
import bisect
from StringIO import StringIO

from gridcentric.pancake.config import ManagerConfig, ServiceConfig
from gridcentric.pancake.service import Service
import gridcentric.pancake.loadbalancer.connection as lb_connection
from gridcentric.pancake.zookeeper.connection import ZookeeperConnection
from gridcentric.pancake.zookeeper.connection import ZookeeperException
import gridcentric.pancake.zookeeper.paths as paths
import gridcentric.pancake.ips as ips

class ScaleManager(object):

    def __init__(self, zk_servers):
        self.running = False
        self.zk_servers = zk_servers
        self.config = ManagerConfig("")

        self.uuid = str(uuid.uuid4()) # Manager uuid (generated).

        self.services = {}        # Service map (name -> service)
        self.key_to_services = {} # Service map (key() -> [services...])

        self.managers = {}        # Forward map of manager keys.
        self.manager_keys = []    # Our local manager keys.
        self.key_to_manager = {}  # Reverse map for manager keys.
        self.key_to_owned = {}    # Service to ownership.

        self.load_balancer = None # Load balancer connection.

    def serve(self):
        # Create a Zookeeper connection.
        self.zk_conn = ZookeeperConnection(self.zk_servers)

        # Register ourselves.
        self.manager_register()

        # Create the loadbalancer connection.
        self.load_balancer = lb_connection.get_connection(self.config.loadbalancer_name(),
                                                          self.config.loadbalancer_config())

        # Watch all IPs.
        self.zk_conn.watch_children(paths.new_ips(), self.register_ip)

        # Watch all managers and services.
        self.manager_change(self.zk_conn.watch_children(paths.managers(), self.manager_change))
        self.service_change(self.zk_conn.watch_children(paths.services(), self.service_change))

    def manager_select(self, service):
        # Remember whether this was previous managed.
        managed = self.service_owned(service)

        # Find the cloest key.
        keys = self.key_to_manager.keys()
        index = bisect.bisect(keys, service.key())
        key = keys[index % len(self.key_to_manager)]
        manager_key = self.key_to_manager[key]

        # Check if this is us.
        self.key_to_owned[service.key()] = (manager_key == self.uuid)

        logging.info("Service %s owned by %s (%s)." % \
            (service.name, manager_key, \
            self.service_owned(service) and "That's me!" or "Not me!"))

        # Check if it is one of our own.
        # Start the service if necessary (now owned).
        if not(managed) and self.service_owned(service):
            self.start_service(service)

    def manager_remove(self, service):
        if self.key_to_owned.has_key(service.key()):
            del self.key_to_owned[service.key()]

    def service_owned(self, service):
        return self.key_to_owned.get(service.key(), False)

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

    def manager_register(self):
        # Figure out our global IPs.
        global_ip = ips.find_global()
        logging.info("Manager %s has key %s." % (global_ip, self.uuid))

        # Reload our config.
        global_config = self.zk_conn.read(paths.config())
        self.config = ManagerConfig(global_config)

        # Register our IP.
        if global_ip:
            local_config = self.zk_conn.read(paths.manager_config(global_ip))
            if local_config:
                self.config.reload(local_config)
            self.zk_conn.write(paths.manager_ip(global_ip), self.uuid, ephemeral=True)

        # Generate keys.
        while len(self.manager_keys) < self.config.keys():
            # Generate a random hash key to associate with this manager.
            self.manager_keys.append(hashlib.md5(str(uuid.uuid4())).hexdigest())
        while len(self.manager_keys) > self.config.keys():
            # Drop keys while we're too high.
            del self.manager_keys[len(self.manager_keys) - 1]

        # Write out our associated hash keys as an ephemeral node.
        key_string = ",".join(self.manager_keys)
        self.zk_conn.write(paths.manager_keys(self.uuid), key_string, ephemeral=True)

    def manager_change(self, managers):
        for manager in managers:
            if manager not in self.managers:
                # Read the key and update all mappings.
                keys = self.zk_conn.read(paths.manager_keys(manager)).split(",")
                logging.info("Found manager %s with %d keys." % (manager, len(keys)))
                self.managers[manager] = keys
                for key in keys:
                    self.key_to_manager[key] = manager

        managers_to_remove = []
        for manager in self.managers:
            if manager not in managers:
                # Remove all mappings.
                keys = self.managers[manager]
                logging.info("Removing manager %s with %d keys." % (manager, len(keys)))
                for key in keys:
                    del self.key_to_manager[key]
                managers_to_remove.append(manager)
        for manager in managers_to_remove:
            del self.managers[manager]

        # Recompute all service owners.
        for service in self.services.values():
            self.manager_select(service)

    def create_service(self, service_name):
        logging.info("New service %s found to be managed." % service_name)

        # Create the object.
        service_path = paths.service(service_name)
        service_config = ServiceConfig(self.zk_conn.read(service_path))
        service = Service(service_name, service_config, self)
        self.services[service_name] = service
        service_key = service.key()
        self.key_to_services[service_key] = \
            self.key_to_services.get(service.key(),[]) + [service_name]

        # Watch the config for this service.
        logging.info("Watching service %s." % (service_name))
        self.zk_conn.watch_contents(service_path, service.update_config)

        # Select the manager for this service.
        self.manager_select(service)

    def start_service(self, service):
        # This service is now being managed by us.
        service.manage()
        service.update()

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

            if self.service_owned(service):
                service.unmanage()

            self.manager_remove(service)

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
        self.zk_conn.delete(paths.ip_address(ip_address))

    def register_ip(self, ips):
        def _register_ip(scale_manager, service, ip):
            logging.info("Service %s found for IP %s" % (service.name, ip))
            # We found the service that this IP address belongs. Confirm this
            # IP address and remove it from the new-ip address. Finally update
            # the loadbalancer.
            scale_manager.zk_conn.write(paths.confirmed_ip(service.name, ip), "")
            scale_manager.zk_conn.write(paths.ip_address(ip), service.name)
            scale_manager.zk_conn.delete(paths.new_ip(ip))
            scale_manager.update_loadbalancer(service)

        for ip in ips:
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
        self.load_balancer.save()

    def mark_instance(self, service_name, instance_id):
        # Increment the mark counter.
        remove_instance = False
        mark_counter = int(self.zk_conn.read(paths.marked_instance(service_name, instance_id), '0'))
        mark_counter += 1

        if mark_counter >= self.config.mark_maximum():
            # This instance has been marked too many times. There is likely
            # something really wrong with it, so we'll clean it up.
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
        logging.debug("Load balancer returned metrics: %s" %(metrics))
        metrics_by_key = {}
        service_addresses = {}
        for ip in metrics:
            for service in self.services.values():
                if not service.name in service_addresses:
                    service_addresses[service.name] = service.addresses() + service.static_addresses()
                service_ips = service_addresses[service.name] 
                if not(service.key() in metrics_by_key):
                    metrics_by_key[service.key()] = []
                if ip in service_ips:
                    logging.debug("Metrics for ip %s belong to service %s" %(ip, service.name))
                    metrics_by_key[service.key()].append(metrics[ip])

        # TODO: Register all loadbalancer metrics in Zookeeper, so that the
        # manager for this service has the opportunity to read data from all
        # loadbalancers, not just their own.

        # Does a health check on all the services that are being managed.
        for service in self.services.values():
            # Do not kick the service if it is not currently owned by us.
            if not(self.service_owned(service)):
                continue

            # Run a health check on this service.
            try:
                service.health_check()
                # Do the service update.
                service.update(reconfigure=False, metrics=metrics_by_key.get(service.key(), []))
            except:
                logging.error("Error updating service %s." %(service.name))

    def run(self):
        # Note that we are running.
        self.running = True

        while self.running:
            try:
                # Reconnect to the Zookeeper servers.
                self.serve()

                # Kick the loadbalancer on startup.
                self.reload_loadbalancer()

                # Perform continuous health checks.
                while self.running:
                    self.health_check()
                    if self.running:
                        time.sleep(self.config.health_check())

            except ZookeeperException:
                # Sleep on ZooKeeper exception and retry.
                logging.debug("Received ZooKeeper exception, retrying.")
                if self.running:
                    time.sleep(self.config.health_check())

    def clean_stop(self):
        self.running = False
