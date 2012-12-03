
from reactor.cloud.osapi import BaseOsConfig
from reactor.cloud.osapi import BaseOsConnection

class OsVmsConfig(BaseOsConfig):

    def instance_id(self):
        return self._get("instance_id", "0")

class Connection(BaseOsConnection):
    """ Connects to a nova cloud that has the Gridcentric VMS extension enabled. """

    def __init__(self, config):
        super(Connection, self).__init__(config)

    def create_config(self, config):
        return OsVmsConfig(config)

    def _list_instances(self):
        """ 
        Returns a list of instances from the endpoint.
        """
        server = self._novaclient().gridcentric.get(self.config.instance_id())
        return server.list_launched()

    def _start_instance(self, params={}):
        launch_params = { 'guest' : params }
        server = self._novaclient().gridcentric.get(self.config.instance_id())
        server.launch(guest_params=params)
