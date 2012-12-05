import logging

from reactor.manager import ManagerConfig
from reactor.manager import ScaleManager
from reactor.manager import locked
from reactor.config import ConfigView
import reactor.zookeeper.paths as paths

from reactor.server.endpoint import APIEndpoint
import reactor.server.iptables as iptables
import reactor.server.ips as ips

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
        params["reactor"] = "api.%s" % self.domain

        return params

    @locked
    def setup_iptables(self, managers=[]):
        hosts = []
        hosts.extend(managers)
        for host in self.zk_servers:
            if not(host) in hosts:
                hosts.append(host)
        iptables.setup(hosts, extra_ports=[8080])

    def manager_register(self, config_str=''):
        # Ensure that the default loadbalancers are available.
        new_config = ManagerConfig(config_str)
        new_config._set("manager", "loadbalancer", "dnsmasq,nginx,tcp")
        super(ReactorScaleManager, self).manager_register(str(new_config))

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

    def reload_domain(self, domain):
        super(ReactorScaleManager, self).reload_domain(domain)
        if self.api_endpoint:
            # Make sure that the API endpoint reloads appropriately.
            self.api_endpoint.api_config()
