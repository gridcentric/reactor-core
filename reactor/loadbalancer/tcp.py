import os
import socket
import re
import time
import threading
import random
import select

from reactor.config import SubConfig
from reactor.loadbalancer.connection import LoadBalancerConnection
from reactor.loadbalancer.netstat import connection_count

def close_fds(except_fds=[]):
    try:
        maxfd = os.sysconf("SC_OPEN_MAX")
    except (AttributeError, ValueError):
        maxfd = 1024
        for fd in range(0, maxfd):
            if not(fd in except_fds):
                os.close(fd)

def fork_and_exec(cmd, child_fds=[]):
    # Close all file descriptors, except
    # for those we have been specified to keep.
    # These file descriptors are closed in the
    # parent post fork.

    pid = os.fork()
    if pid != 0:
        # Wait for the child to exit.
        while True:
            (pid, status) = os.waitpid(pid, 0)
            if pid == pid:
                return

        # Close the child FDs.
        for fd in child_fds:
            os.close(fd)

        # Finish up here.
        return

    # Close off all parent FDs.
    close_fds(except_fds=child_fds)

    # Fork again.
    pid = os.fork()
    if pid != 0:
        os._exit(0)

    # Exec the given command.
    os.execvp(cmd[0], cmd)

class Accept:
    def __init__(self, sock):
        (client, address) = sock.accept()
        self.sock = client
        self.src  = address
        self.dst  = sock.getsockname()

    def drop(self):
        self.sock.close()

    def redirect(self, host, port):
        cmd = ["socat", "fd:%d" % self.sock.fileno(), "tcp-connect:%s:%d" % (host, port)]
        return fork_and_exec(cmd, child_fds=self.sock.fileno())

class ConnectionConsumer(threading.Thread):
    def __init__(self, connection, producer, exclusive=True):
        threading.Thread.__init__(self)
        self.execute    = True
        self.connection = connection
        self.producer   = producer
        self.exclusive  = exclusive
        self.ports      = {}
        self.cond       = threading.Condition()

    def set(self, ports):
        self.cond.acquire()
        self.ports = ports
        self.cond.release()

    def stop(self):
        self.execute = False

    def handle(self, connection):
        self.cond.acquire()
        try:
            # Index by the destination port.
            port = connection.dst[1]
            if not(self.ports.has_key(port)):
                self.cond.notifyAll()
                connection.drop()
                return True

            # Create a map of the IPs.
            backends = self.ports[connection.dst[1]]
            ipmap = {}
            ipmap.update(backends)
            ips = ipmap.keys()

            # Find a backend IP (exclusive or not).
            if self.exclusive:
                ip = self.connection._find_unused_ip(ips)
            else:
                ip = ips[random.randint(0, len(ips)-1)]

            # Either redirect or drop the connection.
            if ip:
                self.cond.notifyAll()
                connection.redirect(ip, ipmap[ip])
                return True
            else:
                return False
        finally:
            self.cond.release()

    def flush(self):
        # Attempt to flush all connections.
        while self.producer.has_pending():
            connection = self.producer.next()
            if not(self.handle(connection)):
                self.producer.push(connection)
                break

    def run(self):
        while self.execute:
            connection = self.producer.next()

            self.cond.acquire()
            try:
                if self.handle(connection):
                    # If we can handle this connection,
                    # make sure that the queue is flushed.
                    self.flush()
                else:
                    # If we can't handle this connection right
                    # now, we wait and will try it again on
                    # the next round.
                    self.producer.push(connection)
                    self.cond.wait()
            finally:
                self.cond.release()

class ConnectionProducer(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.execute = True
        self.pending = []
        self.sockets = {}
        self.filemap = {}
        self.portmap = {}
        self.cond    = threading.Condition()
        self.set()

    def stop(self):
        self.cond.acquire()
        self.execute = False
        self.cond.release()

    def set(self, ports=[]):
        # Set the appropriate ports.
        self.cond.acquire()
        try:
            for port in ports:
                if not(self.sockets.has_key(port)):
                    sock = socket.socket()
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    sock.bind(("", port))
                    sock.listen(10)
                    self.sockets[port] = sock
                    self.filemap[sock.fileno()] = sock
                    self.portmap[sock.fileno()] = port
            for port in self.sockets:
                if not(port in ports):
                    sock = self.sockets[port]
                    del self.sockets[port]
                    del self.filemap[sock.fileno()]
                    del self.portmap[sock.fileno()]
            self._update_epoll()
        finally:
            self.cond.release()

    def _update_epoll(self):
        self.epoll = select.epoll()
        for socket in self.sockets.values():
            self.epoll.register(socket.fileno(), select.EPOLLIN)

    def next(self, timeout=None):
        # Pull the next connection.
        self.cond.acquire()
        try:
            while self.execute and \
                  len(self.pending) == 0:
                self.cond.wait(timeout=timeout)
            if self.execute:
                return self.pending.pop(0)
            else:
                return None
        finally:
            self.cond.release()

    def push(self, connection):
        # Push back a connection.
        self.cond.acquire()
        try:
            self.pending.insert(0, connection)
            self.cond.notifyAll()
        finally:
            self.cond.release()

    def has_pending(self):
        # Check for pending connections.
        self.cond.acquire()
        try:
            return self.execute and len(self.pending) > 0
        finally:
            self.cond.release()

    def run(self):
        while True:
            # Poll for events.
            events = self.epoll.poll(1)

            # Scan the events and accept.
            self.cond.acquire()
            for fileno, event in events:
                if not(fileno in self.filemap):
                    # Stale connection.
                    continue

                sock = self.filemap[fileno]
                port = self.portmap[fileno]

                # Create a new connection object.
                connection = Accept(sock)

                # Push it into the queue.
                self.pending.append(connection)
                self.cond.notifyAll()

            # Check if we should continue executing.
            if not(self.execute):
                self.cond.notifyAll()
                self.cond.release()
                break
            else:
                self.cond.release()
                continue

class TcpLoadBalancerConfig(SubConfig):

    def exclusive(self):
        # Whether or not the server is exclusive.
        return self._get("exclusive", "true").lower() == "true"

    def kill(self):
        # Whether or not the server will be killed after use.
        return self._get("kill", "false").lower() == "true"

class Connection(LoadBalancerConnection):

    producer = None
    consumer = None

    def __init__(self, name, scale_manager, config):
        LoadBalancerConnection.__init__(self, name, scale_manager)
        self.portmap = {}
        self.tracked = {}
        self.active = {}
        self.config = TcpLoadBalancerConfig(config)

        self.producer = ConnectionProducer()
        self.producer.start()
        self.consumer = ConnectionConsumer(self, self.producer, self.config.exclusive())
        self.consumer.start()

    def __del__(self):
        if self.producer:
            self.producer.stop()
        if self.consumer:
            self.consumer.stop()

    def clear(self):
        # Remove all mapping and tracking configuration.
        self.portmap = {}
        self.tracked = {}
        self.active = {}

    def redirect(self, url, names, other, manager_ips):
        pass

    def change(self, url, names, public_ips, manager_ips, private_ips):
        # We are doing passthrough to the backend, so we mix public and private.
        ips = public_ips + private_ips

        # Parse the url, we expect a form tcp://port and nothing else.
        m = re.match("tcp://(\d*)$", url)
        if not(m):
            return
        listen = int(m.group(1))

        # Clear existing data.
        if self.portmap.has_key(listen):
            del self.portmap[listen]
        self.tracked[url] = []

        # Check for a removal / unsupported redirect.
        if len(ips) == 0:
            return

        # Update the portmap.
        self.portmap[listen] = []
        for backend in ips:
            if not(backend.port):
                port = listen
            else:
                port = backend.port
            self.portmap[listen].append((backend.ip, port))
            self.tracked[url].append((backend.ip, port))

    def save(self):
        self.producer.set(self.portmap.keys())
        self.consumer.set(self.portmap)
        self.consumer.flush()

    def metrics(self):
        records = {}

        # Grab the active connections.
        active_connections = connection_count()
        stale_active = []
        locked_ips = self._list_ips() or []

        for connection_list in self.tracked.values():

            for (ip, port) in connection_list:
                active = active_connections.get((ip, port), 0)
                records[ip] = { "active" : (1, active) }

                if active:
                    # Record this server as active.
                    self.active[ip] = True
                elif not(active) and (self.active.has_key(ip) or ip in locked_ips):
                    # Record this server as stale.
                    if self.active.has_key(ip):
                        del self.active[ip]
                    stale_active.append(ip)

        # Remove old active connections, and potentially
        # kill off servers that were once active and are
        # now not active.
        if self.config.kill():
            self._scale_manager.unregister_ip(stale_active)
        elif self.config.exclusive():
            for ip in stale_active:
                self._forget_ip(ip)
            self.consumer.flush()

        return records
