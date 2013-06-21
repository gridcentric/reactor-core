import os
import logging

from reactor.manager import ManagerConfig
from reactor.manager import ScaleManager
from reactor.manager import locked
import reactor.zookeeper.paths as paths

from reactor.server.endpoint import APIEndpoint
import reactor.server.iptables as iptables
import reactor.server.ips as ips
from reactor.submodules import cloud_submodules, loadbalancer_submodules

class ReactorScaleManager(ScaleManager):
    def __init__(self, zk_servers):
        # Grab the list of global IPs.
        names = ips.find_global()
        ScaleManager.__init__(self, zk_servers, names)

        # The implicit API endpoint.
        self.api_endpoint = None

    def start_params(self, endpoint=None):
        # Pass a parameter pointed back to this instance.
        params = super(ReactorScaleManager, self).start_params(endpoint=endpoint)
        params["reactor"] = ips.find_global()[0]

        return params

    @locked
    def setup_iptables(self, managers=[]):
        hosts = []
        hosts.extend(managers)
        for host in self.zk_servers:
            if not(host) in hosts:
                hosts.append(host)
        iptables.setup(hosts, extra_ports=[8080])

    def manager_register(self, config=None):
        manager_config = ManagerConfig(values=config)
        manager_config.loadbalancers = loadbalancer_submodules()
        manager_config.clouds = cloud_submodules()
        super(ReactorScaleManager, self).manager_register(manager_config._values())

    def serve(self):
        # Perform normal setup.
        super(ReactorScaleManager, self).serve()

        # Make sure we've got our IPtables rocking.
        self.setup_iptables(self.zk_conn.watch_children(
            paths.manager_configs(), self.setup_iptables))

        # Ensure it is being served.
        if not("api" in self.endpoints):
            self.create_endpoint("api")

    def create_endpoint(self, endpoint_name):
        if endpoint_name == "api":
            # Create the API endpoint.
            if not(self.api_endpoint):
                self.api_endpoint = APIEndpoint(self)

            logging.info("API endpoint found.")
            self.add_endpoint(self.api_endpoint)
        else:
            # Create the standard endpoint.
            super(ReactorScaleManager, self).create_endpoint(endpoint_name)

    def remove_endpoint(self, endpoint_name, unmanage=False):
        if endpoint_name == "api" and unmanage:
            # Recreate, we always have an API endpoint.
            self.create_endpoint(endpoint_name)
        else:
            super(ReactorScaleManager, self).remove_endpoint(endpoint_name, unmanage=unmanage)
