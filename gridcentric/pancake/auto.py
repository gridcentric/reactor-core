import socket
import threading
import logging
import json

from pyramid.response import Response

from gridcentric.pancake.service import Service

from gridcentric.pancake.manager import ScaleManager
from gridcentric.pancake.manager import locked

from gridcentric.pancake.config import ServiceConfig
from gridcentric.pancake.api import PancakeApi
from gridcentric.pancake.api import connected
from gridcentric.pancake.api import authorized

import gridcentric.pancake.ips as ips
import gridcentric.pancake.zookeeper.config as zk_config
import gridcentric.pancake.zookeeper.paths as paths

class APIService(Service):
    def __init__(self, scale_manager):

        class APIServiceConfig(ServiceConfig):
            def __init__(self, scale_manager):
                self.scale_manager = scale_manager
            def _load(self, config_str):
                pass
            def reload(self, config_str):
                pass

            def url(self):
                return "http://%s/" % self.scale_manager.domain
            def port(self):
                return 8080
            def instance_id(self):
                return 0
            def min_instances(self):
                return 0
            def max_instances(self):
                return 0
            def metrics(self):
                return ""
            def source(self):
                return None
            def get_service_auth(self):
                return (None, None, None)
            def auth_info(self):
                return None
            def static_ips(self):
                ip_addresses = []
                for server in self.scale_manager.zk_servers:
                    try:
                        ip_addresses += [socket.gethostbyname(server)]
                    except:
                        logging.warn("Failed to determine the ip address for %s." % server)
                return ip_addresses

            def __str__(self):
                return ""

        # Create an API service that will automatically reload.
        super(APIService, self).__init__("api",
                                         APIServiceConfig(scale_manager),
                                         scale_manager,
                                         cloud='none')

class AutoScaleManager(ScaleManager):
    def __init__(self, zk_servers):
        ScaleManager.__init__(self, zk_servers)
        self.api_service = None # The implicit API service.

    @locked
    def serve(self):
        ScaleManager.serve(self)

        # Create the API service.
        if not(self.api_service):
            self.api_service = APIService(self)

        # Ensure it is being served.
        if not(self.api_service.name in self.services):
            self.create_service(self.api_service.name)

    @locked
    def create_service(self, service_name):
        if service_name == "api":
            logging.info("API service found.")

            # Create the API service object.
            service = APIService(self)
            self.add_service(service, service_path=paths.service(service.name))
        else:
            # Create the standard service.
            super(AutoScaleManager, self).create_service(service_name)

    @locked
    def reload_domain(self, domain):
        super(AutoScaleManager, self).reload_domain(domain)

        # Reload the implicit service.
        if self.api_service:
            self.remove_service(self.api_service.name)
            self.add_service(self.api_service)

class PancakeAutoApi(PancakeApi):
    def __init__(self, zk_servers):
        self.manager_running = False
        PancakeApi.__init__(self, zk_servers)

        self.config.add_route('api-servers', '/gridcentric/pancake/api_servers')
        self.config.add_view(self.set_api_servers, route_name='api-servers')

        # Check the service.
        self.check_service(zk_servers)

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
        zk_servers.sort()
        self.zk_servers.sort()
        if self.zk_servers != zk_servers:
            self.stop_manager()

        if not(self.manager_running):
            self.manager = AutoScaleManager(zk_servers)
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
    def check_service(self, zk_servers):
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

    def reconnect(self, zk_servers):
        # Check that we are running correctly.
        self.check_service(zk_servers)

        # Call the base API to reconnect.
        PancakeApi.reconnect(self, zk_servers)
