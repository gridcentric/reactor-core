import os
import socket
import re
import time
import threading
import random
import select

from reactor.config import Config
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
    def __init__(self, locks, producer):
        threading.Thread.__init__(self)
        self.daemon = True
        self.execute = True
        self.locks = locks
        self.producer = producer
        self.ports = {}
        self.cond = threading.Condition()

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
            (exclusive, backends) = self.ports[connection.dst[1]]
            ipmap = {}
            ipmap.update(backends)
            ips = ipmap.keys()

            # Find a backend IP (exclusive or not).
            if exclusive:
                ip = self.locks.find_unused_ip(ips)
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
            if not(connection):
                break
            if not(self.handle(connection)):
                self.producer.push(connection)
                break

    def run(self):
        while self.execute:
            connection = self.producer.next()

            if not(connection):
                break

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
        self.daemon = True
        self.execute = True
        self.pending = []
        self.sockets = {}
        self.filemap = {}
        self.portmap = {}
        self.cond = threading.Condition()
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
            ports_to_delete = []
            for port in self.sockets:
                if not(port in ports):
                    sock = self.sockets[port]
                    del self.filemap[sock.fileno()]
                    del self.portmap[sock.fileno()]
                    ports_to_delete.append(port)
            # Clean old ports out after iterating.
            for port in ports_to_delete:
                del self.sockets[port]
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

class TcpEndpointConfig(Config):

    exclusive = Config.boolean(label="One VM per connection", default=True,
        description="Whether backends are exclusive.")

    kill = Config.boolean(label="Kill VMs on Disconnect", default=False,
        description="Whether backends should be killed after use.")

class Connection(LoadBalancerConnection):

    _ENDPOINT_CONFIG_CLASS = TcpEndpointConfig

    producer = None
    consumer = None

    def __init__(self, **kwargs):
        LoadBalancerConnection.__init__(self, **kwargs)
        self.portmap = {}
        self.tracked = {}
        self.active = {}

        self.producer = ConnectionProducer()
        self.producer.start()
        self.consumer = ConnectionConsumer(self.locks, self.producer)
        self.consumer.start()

    def description(self):
        return "Raw TCP"

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

    def redirect(self, url, names, other, config=None):
        pass

    def change(self, url, names, ips, config=None):
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
            if listen in self.portmap:
                del self.portmap[listen]
            return

        # Update the portmap (including exclusive info).
        config = self._endpoint_config(config)
        self.portmap[listen] = [config.exclusive, []]
        for backend in ips:
            if not(backend.port):
                port = listen
            else:
                port = backend.port

            # NOTE: We save some extra metadata about these backends in the
            # portmap and in the tracker connections list. These are used to
            # later on cleanup backend machines and correctly assign
            # connections (i.e. either exclusively or not exclusively).
            self.portmap[listen][1].append((backend.ip, port))
            self.tracked[url].append((backend.ip, port, config.exclusive, config.kill))

    def save(self):
        self.producer.set(self.portmap.keys())
        self.consumer.set(self.portmap)
        self.consumer.flush()

    def metrics(self):
        records = {}

        # Grab the active connections.
        active_connections = connection_count()
        kill_active = []
        forget_active = []
        locked_ips = self.locks.list_ips() or []

        for connection_list in self.tracked.values():

            for (ip, port, exclusive, kill) in connection_list:

                active = active_connections.get((ip, port), 0)
                records[ip] = { "active" : (1, active) }

                if active:
                    # Record this server as active.
                    self.active[ip] = True

                elif not(active) and (self.active.has_key(ip) or ip in locked_ips):
                    # Record this server as stale.
                    if self.active.has_key(ip):
                        del self.active[ip]

                    if kill:
                        kill_active.append(ip)
                    elif exclusive:
                        forget_active.append(ip)

        # Remove old active connections, and potentially
        # kill off servers that were once active and are
        # now not active.
        if kill_active:
            self.locks._scale_manager.unregister_ip(kill_active)
        if forget_active:
            for ip in forget_active:
                self.locks.forget_ip(ip)
            self.consumer.flush()

        return records
