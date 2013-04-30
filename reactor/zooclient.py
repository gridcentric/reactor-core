import json

from reactor.endpoint import EndpointConfig
from reactor.zookeeper.connection import ZookeeperConnection
import reactor.zookeeper.paths as paths

class ReactorClient(object):

    def __init__(self, zk_servers):
        self.zk_conn = ZookeeperConnection(zk_servers)

    def __del__(self):
        self.close()

    def close(self):
        self.zk_conn.close()

    def list_managed_endpoints(self):
        return self.zk_conn.list_children(paths.endpoints())

    def get_managers_active(self, full=False):
        ips = self.zk_conn.list_children(paths.manager_ips())
        if full:
            managers = {}
            for ip in ips:
                managers[ip] = self.get_manager_key(ip)
            return managers
        else:
            return ips

    def get_manager_key(self, manager):
        return self.zk_conn.read(paths.manager_ip(manager))

    def get_manager_log(self, manager):
        return self.zk_conn.read(paths.manager_log(manager))

    def list_managers_configured(self):
        return self.zk_conn.list_children(paths.manager_configs())

    def manage_endpoint(self, endpoint_name, config):
        self.zk_conn.write(paths.endpoint(endpoint_name), config)

    def unmanage_endpoint(self, endpoint_name):
        self.zk_conn.delete(paths.endpoint(endpoint_name))

    def update_endpoint(self, endpoint_name, config):
        self.zk_conn.write(paths.endpoint(endpoint_name), json.dumps(config))

    def set_endpoint_metrics(self, endpoint_name, metrics, endpoint_ip=None):
        if endpoint_ip:
            self.zk_conn.write(
                paths.endpoint_ip_metrics(endpoint_name, endpoint_ip),
                json.dumps(metrics))
        else:
            self.zk_conn.write(
                paths.endpoint_custom_metrics(endpoint_name),
                json.dumps(metrics))

    def get_endpoint_metrics(self, endpoint_name):
        blob = self.zk_conn.read(paths.endpoint_live_metrics(endpoint_name))
        if blob:
            return json.loads(blob)
        else:
            blob = self.zk_conn.read(paths.endpoint_custom_metrics(endpoint_name))
            if blob:
                return json.loads(blob)
            else:
                return blob

    def get_endpoint_active(self, endpoint_name):
        blob = self.zk_conn.read(paths.endpoint_live_active(endpoint_name))
        if blob:
            return json.loads(blob)
        else:
            return blob

    def set_endpoint_state(self, endpoint_name, state):
        self.zk_conn.write(paths.endpoint_state(endpoint_name), state)

    def get_endpoint_state(self, endpoint_name):
        return self.zk_conn.read(paths.endpoint_state(endpoint_name))

    def get_endpoint_manager(self, endpoint_name):
        return self.zk_conn.read(paths.endpoint_manager(endpoint_name))

    def get_endpoint_config(self, endpoint_name):
        try:
            return json.loads(self.zk_conn.read(paths.endpoint(endpoint_name)))
        except:
            return {}

    def update_manager_config(self, manager, config):
        self.zk_conn.write(paths.manager_config(manager), json.dumps(config))

    def get_manager_config(self, manager):
        try:
            return json.loads(self.zk_conn.read(paths.manager_config(manager)))
        except:
            return {}

    def remove_manager_config(self, manager):
        return self.zk_conn.delete(paths.manager_config(manager))

    def get_endpoint_ip_addresses(self, endpoint_name):
        """
        Returns all the IP addresses (confirmed or explicitly configured)
        associated with the endpoint.
        """
        ip_addresses = []
        confirmed_ips = self.zk_conn.list_children(\
            paths.confirmed_ips(endpoint_name))
        if confirmed_ips != None:
            ip_addresses += confirmed_ips

        # Read any static IPs that may have been configured.
        endpoint_config = EndpointConfig(values=self.get_endpoint_config(endpoint_name))
        configured_ips = endpoint_config._static_ips()
        if configured_ips != None:
            ip_addresses += configured_ips

        return ip_addresses

    def record_new_ip_address(self, ip_address):
        self.zk_conn.delete(paths.new_ip(ip_address))
        self.zk_conn.write(paths.new_ip(ip_address), "")

    def drop_ip_address(self, ip_address):
        self.zk_conn.write(paths.drop_ip(ip_address), "")

    def get_ip_address_endpoint(self, ip_address):
        """
        Returns the endpoint name associated with this ip address.
        """
        return self.zk_conn.read(paths.ip_address(ip_address))

    def auth_hash(self):
        return self.zk_conn.read(paths.auth_hash())

    def set_auth_hash(self, auth_hash):
        if auth_hash:
            self.zk_conn.write(paths.auth_hash(), auth_hash)
        else:
            self.zk_conn.delete(paths.auth_hash())

    def domain(self):
        return self.zk_conn.read(paths.domain())

    def set_domain(self, domain):
        self.zk_conn.write(paths.domain(), domain)
