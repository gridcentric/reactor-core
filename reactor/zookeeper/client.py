import threading

from . connection import ZookeeperConnection

class ZookeeperClient(object):

    """ A simple wrapper around connections that allows for reconnection, etc. """

    def __init__(self, zk_servers):
        self._zk_conn = None
        self._zk_servers = zk_servers
        self._lock = threading.Lock()

    def __del__(self):
        self._disconnect()

    def connect(self, zk_servers=None):
        if zk_servers is None:
            zk_servers = self._zk_servers
        else:
            self._zk_servers = zk_servers
        with self._lock:
            if self._zk_conn != None:
                return

        # Attempt the connection, but ensure we
        # aren't holding on the lock during the
        # timeout period. This means we could waste
        # a little bit of effort if multiple attempts
        # are happening simultaneously.
        zk_conn = ZookeeperConnection(zk_servers)
        with self._lock:
            if self._zk_conn is None:
                self._zk_conn = zk_conn

    def disconnect(self):
        with self._lock:
            if self._zk_conn:
                self._zk_conn.close()
                self._zk_conn = None

    def connected(self):
        with self._lock:
            return self._zk_conn != None

    def reconnect(self, zk_servers=None):
        self._disconnect()
        self._connect(zk_servers=zk_servers)

    def get_connection(self):
        while True:
            with self._lock:
                if self._zk_conn != None:
                    return self._zk_conn
            self.connect()
