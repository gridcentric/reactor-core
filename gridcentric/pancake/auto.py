#!/usr/bin/env python

import socket
import threading
import logging

from gridcentric.pancake.api import PancakeApi
from gridcentric.pancake.manager import ScaleManager
import gridcentric.pancake.zookeeper.config as config

def list_local_ips():
    return [ip for ip in socket.gethostbyname_ex(socket.gethostname())[2]]

def is_local(host):
    remote = socket.gethostbyname(host)
    return remote.startswith("127.") or (remote in list_local_ips())

def any_local(hosts):
    return (True in map(is_local, hosts))

class PancakeAutoApi(PancakeApi):
    def __init__(self, zk_servers):
        self.manager_running = False
        PancakeApi.__init__(self, zk_servers)

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
            config.ensure_stopped()
            config.check_config(zk_servers)
            self.start_manager(zk_servers)

        else:
            logging.info("Stopping Manager, starting Zookeeper.")

            # Start an API server (w/ Zookeeper).
            self.stop_manager()
            config.check_config(zk_servers)
            config.ensure_started()

        # Call the base API to reconnect.
        PancakeApi.reconnect(self, zk_servers)
