import socket
import threading
import logging
import json

from pyramid.response import Response

from gridcentric.pancake.api import PancakeApi
from gridcentric.pancake.api import connected
from gridcentric.pancake.api import authorized
from gridcentric.pancake.manager import ScaleManager
import gridcentric.pancake.ips as ips
import gridcentric.pancake.zookeeper.config as zk_config

class PancakeAutoApi(PancakeApi):
    def __init__(self, zk_servers):
        self.manager_running = False
        PancakeApi.__init__(self, zk_servers)

        self.config.add_route('api-servers', '/gridcentric/pancake/api_servers')
        self.config.add_view(self.set_api_servers, route_name='api-servers')

    @connected
    @authorized
    def set_api_servers(self, context, request):
        """
        Updates the list of API servers in the system.
        """
        if request.method == 'POST':
            api_servers = json.loads(request.body)['api_servers']
            logging.info("Updating API Servers.")
            self.reconnect(api_servers)

        return Response()

    def start_manager(self, zk_servers):
        if not(self.manager_running):
            self.manager = ScaleManager(zk_servers)
            self.manager_thread = threading.Thread(target=self.manager.run)
            self.manager_thread.daemon = True
            self.manager_thread.start()
            self.manager_running = True

    def stop_manager(self):
        if self.manager_running:
            self.manager.clean_stop()
            self.manager_thread.join()
            self.manager_running = False

    # Check to see if this is an API server or a scaling server.
    # We use the simple heuristic that scaling managers run on 
    # servers that are not specified in the list of API servers.
    # In the end, it doesn't really matter, as long as you have
    # at least one 'non-API' server.
    def reconnect(self, zk_servers):
        is_local = ips.any_local(zk_servers)

        if not(is_local):
            # Ensure that Zookeeper is stopped.
            logging.info("Stopping Zookeeper; starting manager.")
            zk_config.ensure_stopped()
            zk_config.check_config(zk_servers)
            self.start_manager(zk_servers)

        else:
            # Ensure that Zookeeper is started.
            logging.info("Starting Zookeeper; stopping manager.")
            self.stop_manager()
            zk_config.check_config(zk_servers)
            zk_config.ensure_started()

        # Call the base API to reconnect.
        PancakeApi.reconnect(self, zk_servers)
