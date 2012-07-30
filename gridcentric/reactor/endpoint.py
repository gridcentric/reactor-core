#!/usr/bin/env python 

from gridcentric.pancake.config import EndpointConfig
from gridcentric.pancake.endpoint import Endpoint
import gridcentric.pancake.zookeeper.paths as paths

class APIEndpoint(Endpoint):
    def __init__(self, scale_manager):
        self.scale_manager = scale_manager
        Endpoint.__init__(self, "api", self.api_config(), scale_manager)

    def api_config(self, config=None):
        # Read the configuration.
        api_path = paths.endpoint("api")
        if config == None:
            config = EndpointConfig(self.scale_manager.zk_conn.read(api_path))
        api_config = EndpointConfig(str(config))

        # Update basic information.
        url = "http://api.%s" % self.scale_manager.domain
        api_config._set("endpoint", "url", url)
        api_config._set("endpoint", "port", "8080")
        api_config._set("scaling", "url", url)

        # Update the static IPs in the configuration.
        addresses = self.scale_manager.zk_conn.list_children(paths.manager_ips())
        addresses.sort()
        address_str = ",".join(addresses)
        api_config._set("endpoint", "static_instances", address_str)

        if not(api_config._is_clean()):
            # Save the config if it was changed.
            self.scale_manager.zk_conn.write(paths.endpoint("api"), str(api_config))

        return api_config

    def update_config(self, config_str):
        new_config = EndpointConfig(config_str)
        Endpoint.update_config(self, str(self.api_config(new_config)))
