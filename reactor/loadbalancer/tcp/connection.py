import os
import socket
import signal
import time
import threading
import Queue
import random
import select
import logging
import netaddr

from reactor.config import Config
from reactor.loadbalancer.connection import LoadBalancerConnection
import reactor.loadbalancer.netstat as netstat

def close_fds(except_fds=None):
    if except_fds is None:
        except_fds = []

    try:
        maxfd = os.sysconf("SC_OPEN_MAX")
    except (AttributeError, ValueError):
        maxfd = 1024
    for fd in range(0, maxfd):
        if not(fd in except_fds):
            try:
                os.close(fd)
            except OSError:
                pass

def fork_and_exec(cmd, child_fds=None):
    if child_fds is None:
        child_fds = []

    # Close all file descriptors, except
    # for those we have been specified to keep.
    # These file descriptors are closed in the
    # parent post fork.
    # Create a pipe to communicate grandchild PID.
    (r, w) = os.pipe()

    # Fork
    pid = os.fork()
    if pid != 0:
        # Close writing end of the pipe.
        os.close(w)
        
        # Wait for the child to exit.
        while True:
            (rpid, status) = os.waitpid(pid, 0)
            if rpid == pid:
                if os.WEXITSTATUS(status) > 0:
                    # Something went wrong, clean up.
                    os.close(r)
                    return None
                else:
                    # Get a file object for the read end.
                    r_obj = os.fdopen(r, "r")

                    # Read grandchild PID from pipe and close it.
                    try:
                        child = int(r_obj.readline())
                        return child
                    except ValueError:
                        return None
                    finally:
                        r_obj.close()

    # Close off all parent FDs.
    close_fds(except_fds=child_fds + [w])

    # Create process group.
    os.setsid()

    # Fork again.
    pid = os.fork()
    if pid != 0:
        # Write grandchild pid to pipe
        w_obj = os.fdopen(w, "w")
        w_obj.write(str(pid) + "\n")
        w_obj.flush()

        # Exit (hard).
        os._exit(0)

    # Close the write end of the pipe
    os.close(w)

    # Exec the given command.
    os.execvp(cmd[0], cmd)

def _as_client(src_ip, src_port):
    return "%s:%d" % (src_ip, src_port)

class Accept(object):

    def __init__(self, sock):
        (client, address) = sock.accept()
        # Ensure that the underlying socket is closed.
        # It's probably crazy pills -- but I saw weird
        # issues with the socket object. This way we only
        # keep around the file descriptor nothing more.
        self.fd = os.dup(client.fileno())
        client._sock.close()
        self.src = address
        self.dst = sock.getsockname()

    def drop(self):
        if self.fd is not None:
            try:
                os.close(self.fd)
            except IOError:
                logging.error("Dropping connection from %s: bad FD %d",
                    _as_client(*(self.src)), self.fd)
            self.fd = None

    def redirect(self, host, port):
        if self.fd is not None:
            cmd = [
                "socat",
                "fd:%d" % self.fd,
                "tcp-connect:%s:%d" % (host, port)
            ]
            child = fork_and_exec(cmd, child_fds=[self.fd])
            if child:
                os.close(self.fd)
                self.fd = None
            return child

class ConnectionConsumer(threading.Thread):

    def __init__(self, locks, producer):
        super(ConnectionConsumer, self).__init__()
        self.daemon = True
        self.execute = True
        self.locks = locks
        self.producer = producer
        self.portmap = {}
        self.children = {}
        self.cond = threading.Condition()

    def set(self, portmap):
        self.cond.acquire()
        self.portmap = portmap
        self.cond.release()

    def stop(self):
        self.execute = False
        self.wakeup()

    def handle(self, connection):
        self.cond.acquire()
        try:
            # Index by the destination port.
            port = connection.dst[1]
            if not(self.portmap.has_key(port)):
                connection.drop()
                return True

            # Create a map of the IPs.
            (exclusive, reconnect, backends, client_subnets) = self.portmap[port]
            ipmap = {}
            ipmap.update(backends)
            ips = ipmap.keys()

            # Check the subnet.
            if client_subnets:
                subnet_okay = False
                for subnet in client_subnets:
                    if netaddr.ip.IPAddress(str(connection.src[0])) in \
                       netaddr.ip.IPNetwork(str(subnet)):
                        subnet_okay = True
                        break
                if not subnet_okay:
                    connection.drop()
                    return True

            # Find a backend IP (exclusive or not).
            ip = None
            if exclusive:
                # See if we have a VM to reconnect to.
                if reconnect > 0:
                    existing = self.locks.find(connection.src[0])
                    if len(existing) > 0:
                        ip = existing[0]
                if not ip:
                    ip = self.locks.lock(ips, value=connection.src[0])
            else:
                ip = ips[random.randint(0, len(ips)-1)]

            if ip:
                # Either redirect or drop the connection.
                child = connection.redirect(ip, ipmap[ip])
                if child:
                    self.children[child] = [ip, connection]
                    return True
            return False
        finally:
            self.cond.release()

    def flush(self):
        # Attempt to flush all connections.
        while True:
            connection = self.producer.next(block=False)
            if not(connection):
                break
            if not(self.handle(connection)):
                self.producer.push(connection)
                break

    def wait(self):
        # Wait for a signal that more backends are
        # available
        self.cond.acquire()
        self.cond.wait()
        self.cond.release()

    def wakeup(self):
        self.cond.acquire()
        self.cond.notify()
        self.cond.release()

    def run(self):
        while self.execute:
            connection = self.producer.next(timeout=1)

            # Service connection, if any.
            if connection:
                if self.handle(connection):
                    # If we can handle this connection,
                    # make sure that the queue is flushed.
                    self.flush()
                else:
                    # If we can't handle this connection right
                    # now, we wait and will try it again on
                    # the next round.
                    self.producer.push(connection)
                    self.wait()

            # Reap dead children.
            self.reap_children()

        # Kill all children.
        for child in self.children.keys():
            try:
                os.kill(child, signal.SIGQUIT)
            except OSError:
                # Process no longer exists.
                pass

    def reap_children(self):
        self.cond.acquire()
        for child in self.children.keys():
            # Check if child is alive
            try:
                os.kill(child, 0)
            except OSError:
                # Not alive - remove from children list.
                del self.children[child]
        self.cond.release()

    def sessions(self):
        session_map = {}
        for (ip, conn) in self.children.values():
            (src_ip, src_port) = conn.src
            # We store clients as ip:port pairs.
            # This matters for below, where we must match
            # in order to drop the session.
            ip_sessions = session_map.get(ip, [])
            ip_sessions.append(_as_client(src_ip, src_port))
            session_map[ip] = ip_sessions
        return session_map

    def drop_session(self, client, backend):
        self.cond.acquire()
        for child in self.children.keys():
            (ip, conn) = self.children[child]
            (src_ip, src_port) = conn.src
            if client == _as_client(src_ip, src_port) and backend == ip:
                try:
                    os.kill(child, signal.SIGTERM)
                except OSError:
                    # The process no longer exists.
                    pass
        self.cond.release()

class ConnectionProducer(threading.Thread):

    def __init__(self):
        super(ConnectionProducer, self).__init__()
        self.daemon = True
        self.execute = True
        self.epoll = None
        self.pending = Queue.Queue()
        self.sockets = {}
        self.filemap = {}
        self.cond = threading.Condition()
        self.set()
        self._update_epoll()

    def stop(self):
        self.execute = False

    def set(self, ports=None):
        if ports is None:
            ports = []

        # Set the appropriate ports.
        self.cond.acquire()
        try:
            for port in ports:
                if not(self.sockets.has_key(port)):
                    sock = socket.socket()
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    try:
                        sock.bind(("", port))
                    except IOError as ioe:
                        # Can't bind this port (likely already in use), so skip it.
                        logging.warning("Can't bind port %d: %s", port, ioe.strerror)
                        continue
                    sock.listen(10)
                    self.sockets[port] = sock
                    self.filemap[sock.fileno()] = sock

            ports_to_delete = []
            for port in self.sockets:
                if not(port in ports):
                    sock = self.sockets[port]
                    del self.filemap[sock.fileno()]
                    sock.close()
                    ports_to_delete.append(port)

            # Clean old ports out after iterating.
            for port in ports_to_delete:
                del self.sockets[port]

            self._update_epoll()
        finally:
            self.cond.release()

    def _update_epoll(self):
        self.epoll = select.epoll()
        for sock in self.sockets.values():
            self.epoll.register(sock.fileno(), select.EPOLLIN)

    def next(self, block=True, timeout=0):
        try:
            # Pull the next connection.
            return self.pending.get(block, timeout)
        except Queue.Empty:
            return None

    def push(self, connection):
        if not connection:
            raise ValueError("Cannot push None")

        # Push back a connection.
        self.pending.put(connection)

    def has_pending(self):
        # Check for pending connections.
        return self.execute and not self.pending.empty()

    def run(self):
        while self.execute:
            try:
                # Poll for events.
                events = self.epoll.poll(1)
            except IOError:
                # Whoops -- could just be an interrupted system call.
                # (To be specific, I see this error when attaching via
                # strace to the process). We just build the descriptor
                # and let it go again..
                self.cond.acquire()
                self._update_epoll()
                self.cond.release()
                continue

            # Scan the events and accept.
            self.cond.acquire()
            for fileno, event in events:
                if not(fileno in self.filemap):
                    # Stale connection. Update epoll.
                    self._update_epoll()
                    continue

                # Check that it's a read event.
                assert (event & select.EPOLLIN) == select.EPOLLIN

                # Create a new connection object.
                sock = self.filemap[fileno]
                connection = Accept(sock)

                # Push it into the queue.
                self.push(connection)

            self.cond.release()

class TcpEndpointConfig(Config):

    exclusive = Config.boolean(label="One VM per connection", default=True,
        description="Each Instance is used exclusively to serve a single connection.")

    reconnect = Config.integer(label="Reconnect Timeout", default=60,
        description="Amount of time a disconnected client has to reconnect before" \
                    + " the VM is returned to the pool.")

    client_subnets = Config.list(label="Client Subnets", order=7,
        description="Only allow connections from these client subnets.")

class Connection(LoadBalancerConnection):
    """ Raw TCP """

    _ENDPOINT_CONFIG_CLASS = TcpEndpointConfig
    _SUPPORTED_URLS = {
        "tcp://([1-9][0-9]*)": lambda m: int(m.group(1))
    }

    producer = None
    consumer = None

    def __init__(self, **kwargs):
        super(Connection, self).__init__(**kwargs)

        self.portmap = {}
        self.active = set()
        self.standby = {}

        self.producer = ConnectionProducer()
        self.producer.start()
        self.consumer = ConnectionConsumer(self.locks, self.producer)
        self.consumer.start()

    def __del__(self):
        self.clear()

    def clear(self):
        # Remove all mapping and tracking configuration.
        self.portmap = {}
        self.active = set()
        self.standby = {}
        if self.producer and self.consumer:
            self.producer.set([])
            self.consumer.set([])
            self.consumer.flush()
            self.producer.stop()
            self.consumer.stop()
        if self.locks:
            self.locks.clear()

    def change(self, url, backends, config=None):
        # Grab the listen port.
        listen = self.url_info(url)

        # Ensure that we can't end up in a loop.
        looping_ips = [backend.ip for backend in backends
            if (backend.port == listen or backend.port == 0)
                and backend.ip.startswith("127.")]

        if len(looping_ips) > 0:
            logging.error("Attempted TCP loop.")
            return

        # Clear existing data.
        if self.portmap.has_key(listen):
            del self.portmap[listen]

        # If no backends, don't queue anything.
        if len(backends) == 0:
            return

        # Build our list of backends.
        config = self._endpoint_config(config)
        portmap_backends = []
        for backend in backends:
            if not(backend.port):
                port = listen
            else:
                port = backend.port
            portmap_backends.append((backend.ip, port))

        # Update the portmap (including exclusive info).
        # NOTE: The reconnect/exclusive/client_subnets parameters
        # control how backends are mapped by the consumer, how machines
        # are cleaned up, etc. See the Consumer class and the metrics()
        # function below to understand the interactions there.
        self.portmap[listen] = (
            config.exclusive,
            config.reconnect,
            portmap_backends,
            config.client_subnets)

    def save(self):
        self.producer.set(self.portmap.keys())
        self.consumer.set(self.portmap)
        self.consumer.wakeup()

    def metrics(self):
        records = {}

        # Grab the active connections.
        active_connections = netstat.connection_count()
        forget_active = []
        locked_ips = self.locks.list() or []
        now = time.time()

        for (exclusive, reconnect, backends, _) in self.portmap.values():
            for (ip, port) in backends:
                active = active_connections.get((ip, port), 0)

                # Cap at 1.0 if we are exclusive
                if exclusive:
                    active = min(active, 1)

                records[ip] = { "active" : (1, active) }

                if active:
                    # Record this server as active.
                    self.active.add(ip)
                    if ip in self.standby:
                        del self.standby[ip]

                elif not(active) and (ip in self.active or ip in locked_ips):
                    # Check the reconnect timer.
                    if exclusive and reconnect > 0:
                        # Add to the standby list if we are not there
                        if ip not in self.standby:
                            self.standby[ip] = now + reconnect

                        # If we've still got time left to wait,
                        if self.standby[ip] > now:
                            # Skip for now.
                            records[ip] = { "active" : (1, 1) }
                            self.active.add(ip)
                            continue
                        # Else delete the entry and fall through
                        else:
                            del self.standby[ip]

                    # Record this server as stale.
                    if ip in self.active:
                        self.active.remove(ip)

                    if exclusive:
                        forget_active.append(ip)

        # Remove old active connections.
        if forget_active:
            for ip in forget_active:
                self.locks.remove(ip)
            self.consumer.wakeup()

        return records

    def sessions(self):
        if self.consumer:
            return self.consumer.sessions()
        return None

    def drop_session(self, client, backend):
        if self.consumer:
            self.consumer.drop_session(client, backend)
