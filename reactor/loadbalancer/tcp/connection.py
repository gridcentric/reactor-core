import os
import socket
import signal
import re
import time
import threading
import Queue
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
            try:
                os.close(fd)
            except OSError:
                pass

def fork_and_exec(cmd, child_fds=[]):
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
        
        # Get a file object for the read end.
        r_obj = os.fdopen(r, "r")

        # Wait for the child to exit.
        while True:
            (rpid, status) = os.waitpid(pid, 0)
            if rpid == pid:
                # Read grandchild PID from pipe and close it.
                child = int(r_obj.readline())
                r_obj.close()
                return child

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

        # Exit
        os._exit(0)

    # Close the write end of the pipe
    os.close(w)

    # Exec the given command.
    os.execvp(cmd[0], cmd)

class Accept:
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
            os.close(self.fd)
            self.fd = None

    def redirect(self, host, port):
        if self.fd is not None:
            cmd = [
                "socat",
                "fd:%d" % self.fd,
                "tcp-connect:%s:%d" % (host, port)
            ]
            child = fork_and_exec(cmd, child_fds=[self.fd])
            os.close(self.fd)
            self.fd = None
            return child

class ConnectionConsumer(threading.Thread):
    def __init__(self, locks, producer):
        threading.Thread.__init__(self)
        self.daemon = True
        self.execute = True
        self.locks = locks
        self.producer = producer
        self.ports = {}
        self.children = {}
        self.cond = threading.Condition()

    def set(self, ports):
        self.cond.acquire()
        self.ports = ports
        self.cond.release()

    def stop(self):
        self.execute = False
        self.wakeup()

    def handle(self, connection):
        self.cond.acquire()
        try:
            # Index by the destination port.
            port = connection.dst[1]
            if not(self.ports.has_key(port)):
                connection.drop()
                return True

            # Create a map of the IPs.
            (exclusive, reconnect, backends) = self.ports[port]
            ipmap = {}
            ipmap.update(backends)
            ips = ipmap.keys()

            # Find a backend IP (exclusive or not).
            ip = None
            if exclusive:
                # See if we have a VM to reconnect to.
                if reconnect > 0:
                    ip = self.locks.find_locked_ip(connection.src[0])
                if not(ip):
                    ip = self.locks.find_unused_ip(ips, connection.src[0])
            else:
                ip = ips[random.randint(0, len(ips)-1)]

            # Either redirect or drop the connection.
            if ip:
                child = connection.redirect(ip, ipmap[ip])
                self.children[child] = [ip, connection]
                return True
            else:
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

            # Reap dead children
            self.reap_children()

        # Kill all children
        for child in self.children.keys():
            try:
                os.kill(child, signal.SIGQUIT)
            except:
                pass

    def reap_children(self):
        self.cond.acquire()
        for child in self.children.keys():
            # Check if child is alive
            try:
                os.kill(child, 0)
            except:
                # Not alive - remove from children list
                del self.children[child]
        self.cond.release()

    def _as_client(self, src_ip, src_port):
        return "%s:%d" % (src_ip, src_port)

    def sessions(self):
        session_map = {}
        for (ip, conn) in self.children.values():
            (src_ip, src_port) = conn.src
            # We store clients as ip:port pairs.
            # This matters for below, where we must match
            # in order to drop the session.
            ip_sessions = session_map.get(ip, [])
            ip_sessions.append(self._as_client(src_ip, src_port))
            session_map[ip] = ip_sessions
        return session_map

    def drop_session(self, backend, client):
        self.cond.acquire()
        for child in self.children.keys():
            (ip, conn) = self.children[child]
            (src_ip, src_port) = conn.src
            if client == self._as_client(src_ip, src_port) and backend == ip:
                try:
                    os.kill(child, signal.SIGTERM)
                except:
                    pass
        self.cond.release()

class ConnectionProducer(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.daemon = True
        self.execute = True
        self.pending = Queue.Queue()
        self.sockets = {}
        self.filemap = {}
        self.portmap = {}
        self.cond = threading.Condition()
        self.set()

    def stop(self):
        self.execute = False

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
        for socket in self.sockets.values():
            self.epoll.register(socket.fileno(), select.EPOLLIN)

    def next(self, block=True, timeout=0):
        try:
            # Pull the next connection.
            return self.pending.get(block, timeout)
        except Queue.Empty:
            return None

    def push(self, connection):
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
                    # Stale connection.
                    continue

                sock = self.filemap[fileno]
                port = self.portmap[fileno]

                # Create a new connection object.
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

class Connection(LoadBalancerConnection):
    """ Raw TCP """

    _ENDPOINT_CONFIG_CLASS = TcpEndpointConfig

    producer = None
    consumer = None

    def __init__(self, **kwargs):
        LoadBalancerConnection.__init__(self, **kwargs)
        self.portmap = {}
        self.tracked = {}
        self.active = {}
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
        self.tracked = {}
        self.active = {}
        self.standby = {}
        if self.producer and self.consumer:
            self.producer.set([])
            self.consumer.set([])
            self.consumer.flush()
            self.producer.stop()
            self.consumer.stop()
        if self.locks:
            self.locks.forget_all()

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

        # If no backends, don't queue anything
        if len(ips) == 0:
            return

        # Update the portmap (including exclusive info).
        config = self._endpoint_config(config)
        self.portmap[listen] = [config.exclusive, config.reconnect, []]
        for backend in ips:
            if not(backend.port):
                port = listen
            else:
                port = backend.port

            # NOTE: We save some extra metadata about these backends in the
            # portmap and in the tracker connections list. These are used to
            # later on cleanup backend machines and correctly assign
            # connections (i.e. either exclusively or not exclusively).
            self.portmap[listen][2].append((backend.ip, port))
            self.tracked[url].append((backend.ip, port, config.exclusive, config.reconnect))

    def save(self):
        self.producer.set(self.portmap.keys())
        self.consumer.set(self.portmap)
        self.consumer.wakeup()

    def metrics(self):
        records = {}

        # Grab the active connections.
        active_connections = connection_count()
        forget_active = []
        locked_ips = self.locks.list_ips() or []
        now = time.time()

        for connection_list in self.tracked.values():

            for (ip, port, exclusive, reconnect) in connection_list:

                active = active_connections.get((ip, port), 0)

                # Cap at 1.0 if we are exclusive
                if exclusive:
                    active = min(active, 1)

                records[ip] = { "active" : (1, active) }

                if active:
                    # Record this server as active.
                    self.active[ip] = True
                    if ip in self.standby:
                        del self.standby[ip]

                elif not(active) and (self.active.has_key(ip) or ip in locked_ips):
                    # Check the reconnect timer.
                    if exclusive and reconnect > 0:
                        # Add to the standby list if we are not there
                        if ip not in self.standby:
                            self.standby[ip] = now + reconnect

                        # If we've still got time left to wait,
                        if self.standby[ip] > now:
                            # Skip for now.
                            records[ip] = { "active" : (1, 1) }
                            self.active[ip] = True
                            continue
                        # Else delete the entry and fall through
                        else:
                            del self.standby[ip]

                    # Record this server as stale.
                    if self.active.has_key(ip):
                        del self.active[ip]

                    if exclusive:
                        forget_active.append(ip)

        # Remove old active connections.
        if forget_active:
            for ip in forget_active:
                self.locks.forget_ip(ip)
            self.consumer.wakeup()

        return records

    def sessions(self):
        if self.consumer:
            return self.consumer.sessions()
        return None

    def drop_session(self, backend, client):
        if self.consumer:
            self.consumer.drop_session(backend, client)
