#!/usr/bin/env python 

import logging

from gridcentric.pancake.config import ManagerConfig
from gridcentric.pancake.manager import ScaleManager
from gridcentric.pancake.manager import locked
import gridcentric.pancake.zookeeper.paths as paths

from gridcentric.reactor.endpoint import APIEndpoint
import gridcentric.reactor.iptables as iptables

class ReactorScaleManager(ScaleManager):
    def __init__(self, zk_servers):
        ScaleManager.__init__(self, zk_servers)

        # The implicit API endpoint.
        self.api_endpoint = None

    def start_params(self):
        # Parameters passed to guests launched.
        return {"reactor" : "api.%s" % self.domain}

    @locked
    def setup_iptables(self, managers=[]):
        hosts = []
        hosts.extend(managers)
        for host in self.zk_servers:
            if not(host) in hosts:
                hosts.append(host)
        iptables.setup(hosts, extra_ports=[8080])

    @locked
    def manager_register(self, config_str=''):
        # Ensure that the default loadbalancers are available.
        new_config = ManagerConfig(config_str)
        new_config._set("manager", "loadbalancer", "dnsmasq,nginx")
        ScaleManager.manager_register(self, str(new_config))

    @locked
    def serve(self):
        # Perform normal setup.
        super(ReactorScaleManager, self).serve()

        # Make sure we've got our IPtables rocking.
        self.setup_iptables(self.zk_conn.watch_children(
            paths.manager_configs(), self.setup_iptables))

        # Create the API endpoint.
        if not(self.api_endpoint):
            self.api_endpoint = APIEndpoint(self)

        # Ensure it is being served.
        if not(self.api_endpoint.name in self.endpoints):
            self.create_endpoint(self.api_endpoint.name)

    @locked
    def create_endpoint(self, endpoint_name):
        if endpoint_name == "api":
            logging.info("API endpoint found.")

            # Create the API endpoint object.
            endpoint = APIEndpoint(self)
            self.add_endpoint(endpoint, endpoint_path=paths.endpoint(endpoint.name))
        else:
            # Create the standard endpoint.
            super(ReactorScaleManager, self).create_endpoint(endpoint_name)

    @locked
    def remove_endpoint(self, endpoint_name, unmanage=False):
        super(ReactorScaleManager, self).remove_endpoint(endpoint_name, unmanage=unmanage)

        # We don't allow users to remove the API endpoint,
        # so whenever it's gone it's simply recreated.
        if endpoint_name == "api":
            self.create_endpoint(endpoint_name)

    @locked
    def reload_domain(self, domain):
        super(ReactorScaleManager, self).reload_domain(domain)
        if self.api_endpoint:
            # Make sure that the API endpoint reloads appropriately.
            self.api_endpoint.api_config()
