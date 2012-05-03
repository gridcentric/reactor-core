import json

from gridcentric.pancake.config import ServiceConfig
from gridcentric.pancake.zookeeper.connection import ZookeeperConnection
import gridcentric.pancake.zookeeper.paths as paths

class PancakeClient(object):

    def __init__(self, zk_servers):
        self.zk_conn = ZookeeperConnection(zk_servers)

    def list_managed_services(self):
        return self.zk_conn.list_children(paths.services())

    def list_managers_active(self):
        return self.zk_conn.list_children(paths.manager_ips())

    def list_managers_configured(self):
        return self.zk_conn.list_children(paths.manager_configs())

    def manage_service(self, service_name, config):
        self.zk_conn.write(paths.service(service_name), config)

    def unmanage_service(self, service_name):
        self.zk_conn.delete(paths.service(service_name))

    def update_service(self, service_name, config):
        self.zk_conn.write(paths.service(service_name), config)

    def set_service_metrics(self, service_name, metrics, service_ip=None):
        if service_ip:
            self.zk_conn.write(
                paths.service_ip_metrics(service_name, service_ip),
                json.dumps(metrics))
        else:
            self.zk_conn.write(
                paths.service_custom_metrics(service_name),
                json.dumps(metrics))

    def get_service_metrics(self, service_name):
        blob = self.zk_conn.read(paths.service_live_metrics(service_name))
        if blob:
            return json.loads(blob)
        else:
            return blob

    def get_service_connections(self, service_name):
        blob = self.zk_conn.read(paths.service_live_connections(service_name))
        if blob:
            return json.loads(blob)
        else:
            return blob

    def get_service_config(self, service_name):
        return self.zk_conn.read(paths.service(service_name))

    def update_config(self, config):
        self.zk_conn.write(paths.config(), config)

    def update_manager_config(self, manager, config):
        self.zk_conn.write(paths.manager_config(manager), config)

    def get_config(self):
        return self.zk_conn.read(paths.config())

    def get_manager_config(self, manager):
        return self.zk_conn.read(paths.manager_config(manager))

    def get_service_ip_addresses(self, service_name):
        """
        Returns all the IP addresses (confirmed or explicitly configured)
        associated with the service.
        """
        ip_addresses = []
        confirmed_ips = self.zk_conn.list_children(\
            paths.confirmed_ips(service_name))
        if confirmed_ips != None:
            ip_addresses += confirmed_ips

        configured_ips = ServiceConfig(\
            self.get_service_config(service_name)).static_ips()
        if configured_ips != None:
            ip_addresses += configured_ips

        return ip_addresses

    def record_new_ipaddress(self, ip_address):
        self.zk_conn.delete(paths.new_ip(ip_address))
        self.zk_conn.write(paths.new_ip(ip_address), "")

    def get_ip_address_service(self, ip_address):
        """
        Returns the service name associated with this ip address.
        """
        return self.zk_conn.read(paths.ip_address(ip_address))

    def auth_hash(self):
        return self.zk_conn.read(paths.auth_hash())

    def set_auth_hash(self, auth_hash):
        self.zk_conn.write(paths.auth_hash(), auth_hash)

    def domain(self):
        return self.zk_conn.read(paths.domain())

    def set_domain(self, domain):
        self.zk_conn.write(paths.domain(), domain)
