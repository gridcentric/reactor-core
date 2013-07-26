import threading
import traceback
import logging
import json

import reactor.zookeeper.config as config
import reactor.zookeeper.paths as paths

import reactor.iptables as iptables
import reactor.ips as ips

from reactor.api import connected
from reactor.api import authorized_admin_only
from reactor.api import ReactorApi
from reactor.api import ReactorApiExtension

from pyramid.response import Response

from reactor.manager import ScaleManager
from reactor.manager import locked

class ClusterScaleManager(ScaleManager):

    def __init__(self, client):
        # Grab the list of global IPs.
        names = ips.find_global()
        ScaleManager.__init__(self, client, names)

    @locked
    def _setup_cloud_connections(self, config):
        # We automatically insert the address into all available
        # cloud configurations. This absolutely requires the cloud
        # configuration to support an address key for the manager,
        # but we can address that on a case-by-case basis for now.
        ScaleManager._setup_cloud_connections(self, config)
        for cloud in self.clouds.values():
            config = cloud._manager_config()
            if hasattr(config, 'reactor'):
                config.reactor = ips.find_global()[0]

class ClusterApi(ReactorApiExtension):

    def __init__(self, api):
        ReactorApiExtension.__init__(self, api)

        # Save our manager state.
        self.manager = None
        self.manager_running = False
        self.manager_thread = None

        # Add route for changing the API servers.
        api.config.add_route('api-servers', '/api_servers')
        api.config.add_view(self.set_api_servers, route_name='api-servers')

        # Check that everything is up and running.
        self.check_zookeeper(api.client.zk_servers)
        self.check_manager(api.client.zk_servers)

    @connected
    @authorized_admin_only
    def set_api_servers(self, context, request):
        """
        Updates the list of API servers in the system.
        """
        if request.method == 'POST':
            # Change the used set of API servers.
            logging.info("Updating API Servers.")
            api_servers = json.loads(request.body)['api_servers']
            self.check_zookeeper(api_servers)
            self.api.client._reconnect(api_servers)
            self.check_manager(api_servers)
            return Response()

        elif request.method == 'GET':
            # Return the current set of API servers.
            return Response(body=json.dumps({ "api_servers" : self.api.client.zk_servers }))

        else:
            return Response(status=403)

    def start_manager(self, zk_servers):
        if self.manager:
            zk_servers.sort()
            self.manager.client.zk_servers.sort()
            if self.manager.client.zk_servers != zk_servers:
                # If we've changed Zookeeper servers, then
                # we have to stop the manager and restart
                # to ensure that it's using the full cluster.
                self.stop_manager()

        def manager_run():
            try:
                self.manager.run()
            except:
                error = traceback.format_exc()
                logging.error("An unrecoverable error occurred: %s" % error)

        if not(self.manager_running):
            self.manager = ClusterScaleManager(self.api.client.zk_servers)
            self.manager_thread = threading.Thread(target=manager_run)
            self.manager_thread.daemon = True
            self.manager_thread.start()
            self.manager_running = True

    def stop_manager(self):
        if self.manager_running:
            self.manager.clean_stop()
            self.manager_thread.join()
            self.manager_running = False

    def setup_iptables(self, managers, zk_servers=None):
        if zk_servers is None:
            # Use the currently active zookeeper servers.
            zk_servers = self.api.client.zk_servers
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

    def check_manager(self, zk_servers):
        # We need to start listening for changes to the available
        # manager. If the user creates a new configuration for manager
        # that is not inside the cluster, we have to respond by opening
        # up iptables rules appropriately so that it can connect.
        self.setup_iptables(
            self.api.client.zk_conn.watch_children(
                paths.manager_configs(), self.setup_iptables),
            zk_servers=zk_servers)

        # NOTE: We now *always* start the manager. We rely on the user to
        # actually deactivate it or set the number of keys appropriately when
        # they do not want it to be used to power endpoints.
        self.start_manager(zk_servers)
