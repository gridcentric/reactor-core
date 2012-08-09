import threading
import logging
import json

from pyramid.response import Response

from gridcentric.pancake.api import PancakeApi
from gridcentric.pancake.api import connected
from gridcentric.pancake.api import authorized
from gridcentric.pancake.api import authorized_admin_only

from gridcentric.reactor.manager import ReactorScaleManager
import gridcentric.reactor.ips as ips
import gridcentric.reactor.config as config

class ReactorApi(PancakeApi):
    def __init__(self, zk_servers):
        self.manager_running = False
        PancakeApi.__init__(self, zk_servers)

        self.config.add_route('api-servers', '/reactor/api_servers')
        self.config.add_view(self.set_api_servers, route_name='api-servers')

        # Check the endpoint.
        self.check(zk_servers)

    @connected
    @authorized_admin_only
    def set_api_servers(self, context, request):
        """
        Updates the list of API servers in the system.
        """
        if request.method == 'POST':
            api_servers = json.loads(request.body)['api_servers']
            logging.info("Updating API Servers.")
            self.reconnect(api_servers)
            return Response()
        elif request.method == 'GET':
            return Response(body=json.dumps({ "api_servers" : self.zk_servers }))
        else:
            return Response(status=403)

    def start_manager(self, zk_servers):
        zk_servers.sort()
        self.zk_servers.sort()
        if self.zk_servers != zk_servers:
            self.stop_manager()

        if not(self.manager_running):
            self.manager = ReactorScaleManager(zk_servers)
            self.manager_thread = threading.Thread(target=self.manager.run)
            self.manager_thread.daemon = True
            self.manager_thread.start()
            self.manager_running = True

    def stop_manager(self):
        if self.manager_running:
            self.manager.clean_stop()
            self.manager_thread.join()
            self.manager_running = False

    def check(self, zk_servers):
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

        # NOTE: We now *always* start the manager. We rely on the user to
        # actually deactivate it or set the number of keys appropriately when
        # they do not want it to be used to power endpoints.
        self.start_manager(zk_servers)

    def reconnect(self, zk_servers):
        # Check that we are running correctly.
        self.check(zk_servers)

        # Call the base API to reconnect.
        PancakeApi.reconnect(self, zk_servers)
