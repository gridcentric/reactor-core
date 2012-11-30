
from reactor.cloud.osapi import BaseOsConfig
from reactor.cloud.osapi import BaseOsConnection

class OsVmsConfig(BaseOsConfig):

    def instance_id(self):
        return self._get("instance_id", "0")

    def target(self):
        return self._get("target", "0")

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
        return self._novaclient().gridcentric.list_launched(self.config.instance_id())

    def _start_instance(self, params={}):
        launch_params = { 'target' : self.config.target(), 'guest' : params }
        self._novaclient().gridcentric.launch(self.config.instance_id(),
                                              target=self.config.target(),
                                              guest_params=params)
