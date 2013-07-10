import os
import logging

from reactor.manager import ManagerConfig
from reactor.manager import ScaleManager
from reactor.manager import locked
import reactor.zookeeper.paths as paths

from reactor.server.endpoint import APIEndpointConfig
import reactor.server.iptables as iptables
import reactor.server.ips as ips
from reactor.submodules import cloud_submodules, loadbalancer_submodules

class ReactorScaleManager(ScaleManager):
    def __init__(self, zk_servers):
        # Grab the list of global IPs.
        names = ips.find_global()
        ScaleManager.__init__(self, zk_servers, names)

    def start_params(self, endpoint=None):
        # Pass a parameter pointed back to this instance.
        params = super(ReactorScaleManager, self).start_params(endpoint=endpoint)
        if "api" in self.endpoints:
            api = self.endpoints["api"]
            params["reactor"] = api.url() + ips.find_global()[0]

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

        # Make sure we have an API endpoint.
        if not("api" in self.endpoints):
            # Push the endpoint config
            self.zk_conn.write(paths.endpoint("api"), APIEndpointConfig)
