import json

from reactor.endpoint import Endpoint
from reactor.endpoint import State
import reactor.zookeeper.paths as paths

from reactor.endpoint import EndpointConfig
from reactor.loadbalancer.nginx import NginxEndpointConfig

class APIEndpoint(Endpoint):
    def __init__(self, scale_manager):
        Endpoint.__init__(self, "api", scale_manager)
        # Make sure that this service is running.
        self.update_state(None)

    def api_config(self, config):
        # Whether we require rewriting.
        changed = False

        # Update basic information.
        api_config = EndpointConfig(obj=config)
        new_url = "http://"
        if api_config.url != new_url:
            api_config.url = new_url
            changed = True
        if api_config.port != 8080:
            api_config.port = 8080
            changed = True

        # Clear out the cloud configuration
        if api_config.cloud:
            api_config.cloud = None
            changed = True

        # Make sure we have a loadbalancer configured.
        new_lb = "nginx"
        if not(api_config.loadbalancer):
            api_config.loadbalancer = new_lb
            changed = True

        # Update the static IPs in the configuration.
        api_config.static_instances.sort()
        addresses = self.scale_manager.zk_servers
        addresses.sort()
        if api_config.static_instances != addresses:
            api_config.static_instances = addresses
            changed = True

        # Update SSL information.       
        api_config = NginxEndpointConfig(section='loadbalancer:nginx', obj=config)
        if not api_config.ssl:
            api_config.ssl = True
            changed = True

        # Read the configuration.
        if changed:
            # Save the config if it was changed.
            new_config_str = json.dumps(api_config._values())
            self.scale_manager.zk_conn.write(paths.endpoint("api"), new_config_str)

        # Return our modified config.
        return api_config

    def update_state(self, state):
        if state != State.running:
            # Always make sure that the latest action reflects our state.
            self.scale_manager.zk_conn.write(paths.endpoint_state("api"), State.running)

    def validate_config(self, config, clouds, loadbalancers):
        # Remove unneeded/unwanted config keys before validating
        api_config = EndpointConfig(obj=config)
        api_config.cloud = None
        Endpoint.validate_config(self, api_config, clouds, loadbalancers)

    def update_config(self, config):
        Endpoint.update_config(self, self.api_config(config))
