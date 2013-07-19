import binascii
import json
import array

from reactor.endpoint import EndpointConfig
from reactor.zookeeper.connection import ZookeeperConnection
from reactor.config import fromstr
import reactor.zookeeper.paths as paths

class ReactorClient(object):

    def __init__(self, zk_servers):
        self.zk_conn = None
        self.zk_servers = zk_servers
        self._connect()

    def __del__(self):
        self._disconnect()

    def _connect(self, zk_servers=None):
        if zk_servers is None:
            zk_servers = self.zk_servers
        else:
            self.zk_servers = zk_servers
        self.zk_conn = ZookeeperConnection(zk_servers)

    def _disconnect(self):
        if self.zk_conn:
            self.zk_conn.close()
            self.zk_conn = None

    def _connected(self):
        return self.zk_conn != None

    def _reconnect(self, zk_servers=None):
        self._disconnect()
        self._connect(zk_servers=zk_servers)

    def managers_list(self):
        return self.zk_conn.list_children(paths.manager_configs())

    def managers_active(self, full=False):
        ips = self.zk_conn.list_children(paths.manager_ips())
        if full:
            managers = {}
            for ip in ips:
                managers[ip] = self.manager_key(ip)
            return managers
        else:
            return ips

    def manager_key(self, manager):
        return self.zk_conn.read(paths.manager_ip(manager))

    def endpoint_list(self):
        return self.zk_conn.list_children(paths.endpoints())

    def endpoint_manage(self, endpoint_name, config):
        self.zk_conn.write(paths.endpoint(endpoint_name), config)

    def endpoint_unmanage(self, endpoint_name):
        self.zk_conn.delete(paths.endpoint(endpoint_name))

    def endpoint_update(self, endpoint_name, config):
        self.zk_conn.write(paths.endpoint(endpoint_name), json.dumps(config))

    def endpoint_metrics(self, endpoint_name):
        blob = self.zk_conn.read(paths.endpoint_live_metrics(endpoint_name))
        if blob:
            return json.loads(blob)
        else:
            blob = self.zk_conn.read(paths.endpoint_custom_metrics(endpoint_name))
            if blob:
                return json.loads(blob)
            else:
                return blob

    def endpoint_metrics_set(self, endpoint_name, metrics, endpoint_ip=None):
        if endpoint_ip:
            self.zk_conn.write(
                paths.endpoint_ip_metrics(endpoint_name, endpoint_ip),
                json.dumps(metrics))
        else:
            self.zk_conn.write(
                paths.endpoint_custom_metrics(endpoint_name),
                json.dumps(metrics))

    def endpoint_active(self, endpoint_name):
        blob = self.zk_conn.read(paths.endpoint_live_active(endpoint_name))
        if blob:
            return json.loads(blob)
        else:
            return blob

    def endpoint_state(self, endpoint_name):
        return self.zk_conn.read(paths.endpoint_state(endpoint_name))

    def endpoint_state_set(self, endpoint_name, state):
        self.zk_conn.write(paths.endpoint_state(endpoint_name), state)

    def endpoint_manager(self, endpoint_name):
        return self.zk_conn.read(paths.endpoint_manager(endpoint_name))

    def endpoint_config(self, endpoint_name):
        return fromstr(self.zk_conn.read(paths.endpoint(endpoint_name)))

    def manager_update(self, manager, config):
        self.zk_conn.write(paths.manager_config(manager), json.dumps(config))

    def manager_config(self, manager):
        try:
            return json.loads(self.zk_conn.read(paths.manager_config(manager)))
        except:
            return {}

    def manager_reset(self, manager):
        return self.zk_conn.delete(paths.manager_config(manager))

    def endpoint_ip_addresses(self, endpoint_name):
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
        endpoint_config = EndpointConfig(values=self.endpoint_config(endpoint_name))
        configured_ips = endpoint_config._static_ips()
        if configured_ips != None:
            ip_addresses += configured_ips

        return ip_addresses

    def endpoint_log_load(self, endpoint_name):
        data = self.zk_conn.read(paths.endpoint_log(endpoint_name))
        if data:
            try:
                data = array.array('b', binascii.unhexlify(data))
            except:
                data = None
        return data

    def endpoint_log_save(self, endpoint_name, data):
        self.zk_conn.write(paths.endpoint_log(endpoint_name),
                           binascii.hexlify(data))

    def ip_address_record(self, ip_address):
        self.zk_conn.delete(paths.new_ip(ip_address))
        self.zk_conn.write(paths.new_ip(ip_address), "")

    def ip_address_drop(self, ip_address):
        self.zk_conn.write(paths.drop_ip(ip_address), "")

    def ip_address_endpoint(self, ip_address):
        """
        Returns the endpoint name associated with this ip address.
        """
        return self.zk_conn.read(paths.ip_address(ip_address))

    def auth_hash(self):
        return self.zk_conn.read(paths.auth_hash())

    def auth_hash_set(self, auth_hash):
        if auth_hash:
            self.zk_conn.write(paths.auth_hash(), auth_hash)
        else:
            self.zk_conn.delete(paths.auth_hash())

    def session_list(self, endpoint_name):
        """ Return a mapping of endpoint sessions. """
        clients = self.zk_conn.list_children(paths.sessions(endpoint_name))
        if not clients:
            return []
        return clients

    def session_backend(self, endpoint_name, client):
        return self.zk_conn.read(paths.session(endpoint_name, client))

    # An indication that a session has been opened.
    def session_opened(self, endpoint_name, client, backend):
        self.zk_conn.write(paths.session(endpoint_name, client), backend,
                           ephemeral=True)

    # An indication that a session has been closed.
    def session_closed(self, endpoint_name, client):
        self.zk_conn.delete(paths.session(endpoint_name, client))

    # An indication that a session has been dropped.
    def session_dropped(self, endpoint_name, client):
        self.zk_conn.delete(paths.session(endpoint_name, client))
        self.session_closed(endpoint_name, client)

    # Indicate to the endpoint that a session should be dropped.
    def session_drop(self, endpoint_name, client):
        backend = self.session_backend(endpoint_name, client)
        if backend:
            self.zk_conn.write(paths.session_dropped(endpoint_name, client), backend)

    def sessions_dropped(self, endpoint_name):
        return self.zk_conn.list_children(paths.sessions_dropped(endpoint_name))
