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

    def start_params(self, endpoint=None):
        # Pass a parameter pointed back to this instance.
        params = super(ClusterScaleManager, self).start_params(endpoint=endpoint)
        params.update({ "reactor": ips.find_global()[0] })
        return params

    @locked
    def setup_iptables(self, managers):
        if managers is None:
            return
        hosts = []
        hosts.extend(managers)
        for host in self.client.zk_servers:
            if not(host) in hosts:
                hosts.append(host)
        iptables.setup(hosts, extra_ports=[8080])

    def serve(self):
        # Perform normal setup.
        super(ClusterScaleManager, self).serve()

        # Make sure we've got our IPtables rocking.
        self.setup_iptables(self.client.zk_conn.watch_children(
            paths.manager_configs(), self.setup_iptables))

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

        # Check the endpoint.
        self.check(api.client.zk_servers)

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
            self.check(api_servers)
            self.api.client._reconnect(api_servers)
            return Response()

        elif request.method == 'GET':
            # Return the current set of API servers.
            return Response(body=json.dumps({ "api_servers" : self.api.client.zk_servers }))

        else:
            return Response(status=403)

    def start_manager(self, zk_servers):
        zk_servers.sort()
        self.api.client.zk_servers.sort()
        if self.api.client.zk_servers != zk_servers:
            self.stop_manager()

        def manager_run():
            try:
                self.manager.run()
            except:
                error = traceback.format_exc()
                logging.error("An unrecoverable error occurred: %s" % error)

        if not(self.manager_running):
            self.manager = ClusterScaleManager(self.api.client)
            self.manager_thread = threading.Thread(target=manager_run)
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
