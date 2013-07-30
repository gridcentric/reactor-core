import threading
import traceback
import logging
import json

from pyramid.response import Response

from . import iptables
from . import ips
from . api import connected
from . api import authorized
from . api import ReactorApiExtension
from . manager import ScaleManager
from . zookeeper import config

class Cluster(ReactorApiExtension):

    def __init__(self, api, *args, **kwargs):
        super(Cluster, self).__init__(api, *args, **kwargs)

        # Save our manager state.
        self._managers = None
        self._manager = None
        self._manager_running = False
        self._manager_thread = None

        # Add route for changing the API servers.
        api.config.add_route('api-servers', '/api_servers')
        api.config.add_view(self.set_api_servers, route_name='api-servers')

        # Check that everything is up and running.
        self.check_zookeeper(api.client.servers())
        self.check_manager(api.client.servers())

    @connected
    @authorized()
    def set_api_servers(self, context, request):
        """
        Updates the list of API servers in the system.
        """
        if request.method == 'POST':
            # Change the used set of API servers.
            logging.info("Updating API Servers.")
            api_servers = json.loads(request.body)['api_servers']
            self.check_zookeeper(api_servers)
            self.api.client.reconnect(api_servers)
            self.check_manager(api_servers)
            return Response()

        elif request.method == 'GET':
            # Return the current set of API servers.
            return Response(body=json.dumps(
                { "api_servers" : self.api.client.servers() }))

        else:
            return Response(status=403)

    def start_manager(self, zk_servers):
        # If we've changed Zookeeper servers, then
        # we have to stop the manager and restart
        # to ensure that it's using the full cluster.
        self.stop_manager()

        def manager_run():
            try:
                self._manager.run()
            except Exception:
                logging.error("An unrecoverable error occurred: %s",
                    traceback.format_exc())

        if not(self._manager_running):
            self._manager = ScaleManager(zk_servers)
            self._manager_thread = threading.Thread(target=manager_run)
            self._manager_thread.daemon = True
            self._manager_thread.start()
            self._manager_running = True

    def stop_manager(self):
        if self._manager_running:
            self._manager.stop()
            self._manager_thread.join()
            self._manager_running = False

    def setup_iptables(self, managers, zk_servers=None):
        if zk_servers is None:
            zk_servers = self.api.client.servers()
        hosts = list(set(managers + zk_servers))
        iptables.setup(hosts, extra_ports=[8080])

    def check_zookeeper(self, zk_servers):
        is_local = ips.any_local(zk_servers)

        if not(is_local):
            # Ensure that Zookeeper is stopped.
            config.ensure_stopped()
            config.check_config(zk_servers)
        else:
            # Ensure that Zookeeper is started.
            logging.info("Starting Zookeeper.")
            config.check_config(zk_servers)
            config.ensure_started()

    @connected
    def check_manager(self, zk_servers):
        # We need to start listening for changes to the available
        # manager. If the user creates a new configuration for manager
        # that is not inside the cluster, we have to respond by opening
        # up iptables rules appropriately so that it can connect.
        self._managers = self.api.zkobj.managers()
        self.setup_iptables(
            self._managers.list(watch=self.setup_iptables),
            zk_servers=zk_servers)

        # NOTE: We now *always* start the manager. We rely on the user to
        # actually deactivate it or set the number of keys appropriately when
        # they do not want it to be used to power endpoints.
        self.start_manager(zk_servers)
