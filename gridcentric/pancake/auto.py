#!/usr/bin/env python

import socket
import threading
import logging

from gridcentric.pancake.api import PancakeApi
from gridcentric.pancake.manager import ScaleManager
import gridcentric.pancake.zookeeper.config as zk_config

def list_local_ips():
    from netifaces import interfaces, ifaddresses, AF_INET
    ip_list = []
    for interface in interfaces():
        addresses = ifaddresses(interface)
        if AF_INET in addresses:
            for link in addresses[AF_INET]:
                ip_list.append(link['addr'])
    return ip_list

def is_local(host):
    remote = socket.gethostbyname(host)
    return remote.startswith("127.") or (remote in list_local_ips())

def any_local(hosts):
    return (True in map(is_local, hosts))

class PancakeAutoApi(PancakeApi):
    def __init__(self, zk_servers):
        self.manager_running = False
        PancakeApi.__init__(self, zk_servers)
        self.config.add_route('api-servers', '/gridcentric/pancake/api_servers')
        self.config.add_view(self.set_api_servers, route_name='api-servers')

    @PancakeApi.authorized
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
        is_local = any_local(zk_servers)

        if not(is_local):
            logging.info("Stopping Zookeeper, starting manager.")

            # Start a manager (no Zookeeper).
            zk_config.ensure_stopped()
            zk_config.check_config(zk_servers)
            self.start_manager(zk_servers)

        else:
            logging.info("Stopping Manager, starting Zookeeper.")

            # Start an API server (w/ Zookeeper).
            self.stop_manager()
            zk_config.check_config(zk_servers)
            zk_config.ensure_started()

        # Call the base API to reconnect.
        PancakeApi.reconnect(self, zk_servers)
