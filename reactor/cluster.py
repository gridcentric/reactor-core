# Copyright 2013 GridCentric Inc.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import threading
import traceback
import logging
import json
import time

from pyramid.response import Response

from . import iptables
from . import ips
from . api import connected
from . api import authorized
from . api import ReactorApiExtension
from . manager import ScaleManager
from . zookeeper import config

class CleanerThread(threading.Thread):

    def __init__(self):
        super(CleanerThread, self).__init__()
        self.daemon = True
        self.running = True

    def run(self):
        while self.running:
            # Without pruning, the zookeeper snapshots
            # and log files can grow unbounded. It's the
            # admin's responsibility to prune these logs
            # according to whatever policy they have in
            # place. Instead of relying on a cron job or
            # other external configs, we call the built-in
            # helper to prune these logs as frequently
            # we reasonably can.
            time.sleep(60.0)
            config.clean_logs()

    def stop(self):
        self.running = False

class Cluster(ReactorApiExtension):

    def __init__(self, api, *args, **kwargs):
        super(Cluster, self).__init__(api, *args, **kwargs)

        # Save our manager state.
        self._managers = None
        self._manager = None
        self._manager_running = False
        self._manager_thread = None

        # Add a Zookeeper cleaner.
        self._cleaner_thread = CleanerThread()
        self._cleaner_thread.start()

        # Add route for changing the API servers.
        api.config.add_route('api-servers', '/zk_servers')
        api.config.add_view(self.set_zk_servers, route_name='api-servers')

        # Check that everything is up and running.
        self.check_zookeeper(api.client.servers())
        self.check_manager(api.client.servers())
        logging.info("Cluster ready.")

    def __del__(self):
        self.stop_manager()
        self._cleaner_thread.stop()

    @connected
    @authorized()
    def set_zk_servers(self, context, request):
        """
        Updates the list of API servers in the system.
        """
        if request.method == 'POST':
            # Change the used set of API servers.
            logging.info("Updating API Servers.")
            zk_servers = json.loads(request.body)['zk_servers']
            if len(zk_servers) == 0:
                return Respone(status=403)

            self.check_zookeeper(zk_servers)
            self.api.client.reconnect(zk_servers)
            self.check_manager(zk_servers)
            return Response()

        elif request.method == 'GET':
            # Return the current set of API servers.
            return Response(body=json.dumps(
                { "zk_servers" : self.api.client.servers() }))

        else:
            return Response(status=403)

    def start_manager(self, zk_servers):
        # If we've changed Zookeeper servers, then
        # we have to stop the manager and restart
        # to ensure that it's using the full cluster.
        self.stop_manager()

        def manager_run():
            try:
                logging.info("Manager started.")
                self._manager.run()
                logging.info("Manager stopped.")
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
        iptables.setup(hosts)

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
        return Response()
