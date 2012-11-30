from reactor.endpoint import EndpointConfig
from reactor.endpoint import Endpoint
from reactor.endpoint import State
import reactor.zookeeper.paths as paths

class APIEndpoint(Endpoint):
    def __init__(self, scale_manager):
        self.scale_manager = scale_manager
        Endpoint.__init__(self, "api", self.api_config(), scale_manager)
        # Make sure that this service is running.
        self.update_state(None)

    def api_config(self, config=None):
        # Read the configuration.
        api_path = paths.endpoint("api")
        if config == None:
            config = self.scale_manager.zk_conn.read(api_path) or ''

        # Update basic information.
        api_config = EndpointConfig(str(config))
        url = "http://api.%s" % self.scale_manager.domain
        api_config._set("endpoint", "url", url)
        api_config._set("scaling",  "url", url)
        api_config._set("endpoint", "port", "8080")
        api_config._set("endpoint", "public", "false")
        api_config._set("endpoint", "enabled", "true")

        # Update the static IPs in the configuration.
        addresses = self.scale_manager.zk_servers
        addresses.sort()
        address_str = ",".join(addresses)
        api_config._set("endpoint", "static_instances", address_str)

        if not(api_config._is_clean()):
            # Save the config if it was changed.
            self.scale_manager.zk_conn.write(paths.endpoint("api"), str(api_config))

        return api_config

    def update_state(self, state):
        if state != State.running:
            # Always make sure that the latest action reflects our state.
            self.scale_manager.zk_conn.write(paths.endpoint_state("api"), State.running)

    def update_config(self, config_str):
        new_config = EndpointConfig(config_str)
        Endpoint.update_config(self, str(self.api_config(new_config)))
