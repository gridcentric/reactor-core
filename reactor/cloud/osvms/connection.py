import novaclient.exceptions

from reactor.config import Config
from reactor.cloud.osapi.connection import BaseOsEndpointConfig
from reactor.cloud.osapi.connection import BaseOsConnection

class OsVmsEndpointConfig(BaseOsEndpointConfig):

    instance_id = Config.string(label="Live-Image", order=2,
        validate=lambda self: \
            self.novaclient().servers.get(self.instance_id)._info['status'] == 'BLESSED' or \
            Config.error("Server is not in BLESSED state."),
        description="The live-image to use.")

class Connection(BaseOsConnection):
    """ OpenStack + VMS """

    _ENDPOINT_CONFIG_CLASS = OsVmsEndpointConfig

    def _list_instances(self, config, instance_id):
        """
        Returns a list of instances from the endpoint.
        """
        config = self._endpoint_config(config)
        if instance_id is None:
            server = config.novaclient().cobalt.get(config.instance_id)
            return server.list_launched()
        else:
            try:
                return [config.novaclient().servers.get(instance_id)]
            except novaclient.exceptions.NotFound:
                return []

    def _start_instance(self, config, params):
        config = self._endpoint_config(config)
        server = config.novaclient().cobalt.get(config.instance_id)
        if 'name' in params:
            instance = server.launch(name=params['name'],
                              security_groups=config.security_groups,
                              availability_zone=config.availability_zone,
                              guest_params=params)
        else:
            instance = server.launch(security_groups=config.security_groups,
                              availability_zone=config.availability_zone,
                              guest_params=params)
        return instance[0]
