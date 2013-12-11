# Copyright 2013 GridCentric Inc.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

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

from reactor import utils
from reactor.atomic import Atomic
from reactor.atomic import AtomicRunnable
from reactor.config import Config
from reactor.loadbalancer.connection import LoadBalancerConnection
from reactor.ips import is_local
from reactor.objects.ip_address import IPAddresses

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

    # Fork, return the child.
    pid = os.fork()
    if pid != 0:
        return pid

    # Close off all parent FDs.
    close_fds(except_fds=child_fds)

    # Create process group.
    os.setsid()

    # Exec the given command.
    os.execvp(cmd[0], cmd)

def _as_client(src_ip, src_port):
    return "%s:%d" % (src_ip, src_port)

class Accept(object):

    def __init__(self, sock):
        super(Accept, self).__init__()
        (client, address) = sock.accept()
        # Ensure that the underlying socket is closed.
        # It's probably crazy pills -- but I saw weird
        # issues with the socket object. This way we only
        # keep around the file descriptor nothing more.
        self.fd = os.dup(client.fileno())
        client._sock.close()
        self.src = address
        self.dst = sock.getsockname()

    def __del__(self):
        # If the Accept object hasn't been cleaned up,
        # we ensure that it drops on garbage collection.
        self.drop()

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

class ConnectionConsumer(AtomicRunnable):

    def __init__(self, locks, error_notify, discard_notify, producer):
        super(ConnectionConsumer, self).__init__()

        self.locks = locks
        self.error_notify = utils.callback(error_notify)
        self.discard_notify = utils.callback(discard_notify)
        self.producer = producer

        self.portmap = {}
        self.postponed = []
        self.standby = {}
        self.children = {}

        # Subscribe to events generated by the producer.
        # NOTE: These are cleaned up in stop().
        self.producer.subscribe(self.notify)

        # Start the thread.
        super(ConnectionConsumer, self).start()

    @Atomic.sync
    def set(self, portmap):
        self.portmap = portmap
        self._notify()

    @Atomic.sync
    def _stop(self):
        super(ConnectionConsumer, self).stop()

        # Clean up leftover children.
        self.reap_children()

        # Remove all standby locks.
        self.clear_standby(force=True)

    def stop(self):
        # Unsubscribe from notifications.
        self.producer.unsubscribe(self.notify)

        # Stop the thread.
        self._stop()
        self.join()

    @Atomic.sync
    def notify(self):
        self._notify()

    @Atomic.sync
    def handle(self, connection):
        # Index by the destination port.
        port = connection.dst[1]
        if not(self.portmap.has_key(port)):
            connection.drop()
            return True

        # Grab the information for this port.
        (_, exclusive, disposable, reconnect, backends, client_subnets) = self.portmap[port]

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
        port = None

        if exclusive:
            # See if we have a VM to reconnect to.
            if reconnect > 0:
                existing = self.locks.find(connection.src[0])
                if len(existing) > 0:
                    (ip, port) = existing[0].split(":", 1)
                    port = int(port)
                    if (ip, port) in self.standby:
                        # NOTE: We will have a lock representing
                        # this connection, but is it already held.
                        del self.standby[(ip, port)]
            if not ip:
                # Grab the grab the named lock (w/ ip and port).
                candidates = ["%s:%d" % backend for backend in backends]
                got = self.locks.lock(candidates, value=connection.src[0])
                if got:
                    # We managed to grab the above lock.
                    (ip, port) = got.split(":", 1)
                    port = int(port)
        else:
            # Select an IP at random.
            (ip, port) = backends[random.randint(0, len(backends)-1)]

        if ip and port:
            # Either redirect or drop the connection.
            child = connection.redirect(ip, port)
            standby_time = (exclusive and reconnect)
            # Note: disposable is either None or a mimumum session time.
            # So set the time to dispose as now + minimum session time,
            # or False.
            dispose_time = (disposable is not None and time.time() + disposable)

            if child is not None:
                # Start a notification thread. This will
                # wake up the main consumer thread (so that
                # the child can be reaped) when the child exits,
                # but it will also mark the IP as failed if
                # an error ultimately lead to the exit.
                def closure(child_pid, error_fn, notify_fn):
                    def fn():
                        while True:
                            try:
                                (pid, status) = os.waitpid(child_pid, 0)
                                if pid == child_pid:
                                    break
                            except (TypeError, OSError):
                                (pid, status) = (child_pid, 0)
                                break

                        if os.WEXITSTATUS(status) > 0:
                            # Notify the high-level manager about an error
                            # found on this IP. This may ultimately result in
                            # the instance being terminated, etc.
                            error_fn()

                        # Wait up the consumer that it may reap this
                        # process and accept any new incoming connections.
                        notify_fn()

                    return fn

                # Start threads that will wait for the child process.
                # NOTE: Unlike most other threads in the system, these
                # threads are *not* daemon threads. We want them to keep
                # everything alive so that our Zookeeper locks are properly
                # maintained while the socat processes are alive.
                def error_fn():
                    self.error_notify("%s:%d" % (ip, port))
                t = threading.Thread(target=closure(
                    child, error_fn, utils.callback(self.notify)))
                t.start()

                self.children[child] = (
                    ip,
                    port,
                    connection,
                    standby_time,
                    dispose_time)

                return True

        return False

    @Atomic.sync
    def clear_standby(self, force=False):
        removed = []
        now = time.time()
        for (ip, port) in self.standby:
            (timeout, dispose) = self.standby[(ip, port)]
            if force or timeout < now:
                # If backends are disposable, discard this backend.
                if dispose:
                    self.discard_notify(ip)
                # Remove the named lock (w/ port).
                self.locks.remove("%s:%d" % (ip, port))
                removed.append((ip, port))
        for (ip, port) in removed:
            del self.standby[(ip, port)]
        return len(removed)

    @Atomic.sync
    def run(self):
        while self.is_running():
            connection = self.producer.next()

            # Service connection, if any.
            if connection:
                if not self.handle(connection):
                    # now, we add it to the list of postponed
                    # connections, which we will try again shortly.
                    self.postponed.append(connection)

                # Continue servicing connections while
                # there is an active queue in the producer.
                continue

            # Try servicing postponed connections.
            new_postponed = []
            for connection in self.postponed:
                if not self.handle(connection):
                    # Arg, still not handled. We keep the connection
                    # on our list of postponed connections and continue.
                    new_postponed.append(connection)
            self.postponed = new_postponed

            # Clear any standby IPs.
            if self.clear_standby():
                continue

            # Reap children.
            if self.reap_children():
                continue

            # Wait for a second.
            # This will be waken by either producer events,
            # or by more backends appearing that may make
            # available new backends for us to schedule.
            # The only event that won't wake this is an
            # existing connection expiring.
            self._wait(1.0)

    def reap_children(self):
        reaped = 0

        # Reap dead children.
        for child in self.children.keys():
            try:
                # Check if child is alive.
                os.kill(child, 0)
            except OSError:
                # Not alive - remove from children list.
                (ip, port, _, standby_time, dispose_time) = self.children[child]
                del self.children[child]
                reaped += 1

                # If VMs are disposable, make sure the minimum
                # amount of session time has passed.
                dispose = dispose_time and time.time() >= dispose_time

                # If reconnect and exclusive is on, then
                # we add this connection to the standby list.
                # NOTE: At this point, you only get on the standby
                # list if the IP is exclusive and with reconnect.
                # This means that it will *not* get selected again
                # and the only necessary means of removing the IP
                # is through the clear_standby() hook.
                if standby_time:
                    self.standby[(ip, port)] = \
                        (time.time() + standby_time, dispose)
                else:
                    if dispose:
                        self.discard_notify(ip)
                    self.locks.remove("%s:%d" % (ip, port))

        # Return the number of children reaped.
        # This means that callers can do if self.reap_children().
        return reaped

    @Atomic.sync
    def pending(self):
        pending = {}
        for connection in self.postponed:
            # Index by the destination port.
            port = connection.dst[1]
            if not(self.portmap.has_key(port)):
                continue

            # Get the associated URL for the postponed connection.
            (url, _, _, _, _, _) = self.portmap[port]
            if not pending.has_key(url):
                pending[url] = 1
            else:
                pending[url] += 1
        return pending

    @Atomic.sync
    def metrics(self):
        metric_map = {}

        # Set the active metric for all known backends to zero.
        for (_, _, _, _, backends, _) in self.portmap.values():
            for (ip, port) in backends:
                metric_map["%s:%d" % (ip, port)] = [{ "active" : (1, 0) }]

        # Add 1 for every active connection we're tracking.
        ports = ["%s:%d" % (ip, port) for (ip, port, _, _, _) in self.children.values()]
        ports.extend(["%s:%d" % (ip, port) for (ip, port) in self.standby.keys()])

        for port in ports:
            if not port in metric_map:
                # Set the current active count to one.
                # NOTE: This must be an ip that is no longer
                # in the portmap, but we can still report it.
                metric_map[port] = [{ "active" : (1, 1) }]
            else:
                # Add one to our current active count.
                cur_count = metric_map[port][0]["active"][1]
                metric_map[port][0]["active"] = (1, cur_count+1)

        return metric_map

    @Atomic.sync
    def sessions(self):
        session_map = {}
        for (ip, port, conn, _, _) in self.children.values():
            (src_ip, src_port) = conn.src
            portinfo = "%s:%d" % (ip, port)
            # We store clients as ip:port pairs.
            # This matters for below, where we must match
            # in order to drop the session.
            ip_sessions = session_map.get(portinfo, [])
            ip_sessions.append(_as_client(src_ip, src_port))
            session_map[portinfo] = ip_sessions
        return session_map

    @Atomic.sync
    def drop_session(self, client, backend):
        for child in self.children.keys():
            (ip, port, conn, _, _) = self.children[child]
            (src_ip, src_port) = conn.src
            portinfo = "%s:%d" % (ip, port)
            if client == _as_client(src_ip, src_port) and backend == portinfo:
                try:
                    os.kill(child, signal.SIGTERM)
                except OSError:
                    # The process no longer exists.
                    pass

class ConnectionProducer(AtomicRunnable):

    # On cleanup --
    # When this class is garbage collected, all
    # the pending connections will be dropped.
    # This is due to the fact that everything in
    # the queue is wrapped in the Accept class
    # above, and when these objects are deleted,
    # they will explicitly drop the connection.

    def __init__(self):
        super(ConnectionProducer, self).__init__()

        self.epoll = None
        self.queue = Queue.Queue()
        self.sockets = {}
        self.filemap = {}
        self.notifiers = []
        self.set()

        self._update_epoll()

        # Start the thread.
        super(ConnectionProducer, self).start()

    @Atomic.sync
    def _stop(self):
        super(ConnectionProducer, self).stop()

        if hasattr(self.epoll, 'close'):
            self.epoll.close()

    def stop(self):
        # Stop the thread.
        self._stop()
        self.join()

    @Atomic.sync
    def set(self, ports=None):
        if ports is None:
            ports = []

        # Set the appropriate ports.
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

    @Atomic.sync
    def _update_epoll(self):
        self.epoll = select.epoll()
        for sock in self.sockets.values():
            self.epoll.register(sock.fileno(), select.EPOLLIN)

    @Atomic.sync
    def subscribe(self, cb):
        self.notifiers.append(cb)

    @Atomic.sync
    def unsubscribe(self, cb):
        if cb in self.notifiers:
            self.notifiers.remove(cb)

    @Atomic.sync
    def notify(self):
        for notifier in self.notifiers:
            notifier()

    def next(self):
        try:
            # Pull the next connection.
            return self.queue.get(block=False)
        except Queue.Empty:
            return None

    def run(self):
        while self.is_running():
            try:
                # Poll for events.
                events = self.epoll.poll(1)
            except IOError:
                # Whoops -- could just be an interrupted system call.
                # (To be specific, I see this error when attaching via
                # strace to the process). We just let it go again...
                continue

            # Scan the events and accept.
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

                # Notify all listens that there
                # are new connections available.
                self.queue.put(connection)
                self.notify()

class TcpEndpointConfig(Config):

    exclusive = Config.boolean(label="One VM per connection", default=True,
        description="Each Instance is used exclusively to serve a single connection.")

    disposable = Config.boolean(label="Kill on Disconnect", default=False,
        validate=lambda self: self.exclusive or not(self.disposable) or \
            Config.error("Kill on Disconnect requires One VM per connection."),
        description="Discard backend instances on disconnect. Requires" \
                    + " 'One VM per connection'.")

    dispose_min = Config.integer(label="Minimum session time", default=30,
        validate=lambda self: self.dispose_min >= 0 or \
            Config.error("Minimum session time must be non-negative."),
        description="Minimum session time (in seconds) before a session is" \
                    + " killed on disconnect.")

    reconnect = Config.integer(label="Reconnect Timeout", default=60,
        validate=lambda self: self.reconnect >= 0 or \
            Config.error("The reconnect must be non-negative."),
        description="Amount of time a disconnected client has to reconnect before" \
                    + " the VM is returned to the pool.")

    client_subnets = Config.list(label="Client Subnets", order=7,
        description="Only allow connections from these client subnets.")

class Connection(LoadBalancerConnection):

    """ Managed TCP """

    _ENDPOINT_CONFIG_CLASS = TcpEndpointConfig
    _SUPPORTED_URLS = {
        "tcp://([1-9][0-9]*)": lambda m: int(m.group(1))
    }

    producer = None
    consumer = None

    def __init__(self,
                 zkobj=None,
                 error_notify=None,
                 discard_notify=None,
                 **kwargs):
        super(Connection, self).__init__(**kwargs)

        self.portmap = {}
        self.active = set()
        self.locks = zkobj and zkobj._cast_as(IPAddresses)

        self.producer = ConnectionProducer()
        self.consumer = ConnectionConsumer(
            self.locks,
            error_notify,
            discard_notify,
            self.producer)

    def __del__(self):
        if self.producer:
            self.producer.set([])
            self.producer.stop()
        if self.consumer:
            self.consumer.set([])
            self.consumer.stop()

    def dropped(self, ip):
        # Ensure the locks are gone.
        self.locks.remove(ip)

    def change(self, url, backends, config=None):
        # Grab the listen port.
        listen = self.url_info(url)

        # Ensure that we can't end up in a loop.
        looping_ips = [backend.ip for backend in backends
            if backend.port == listen and
               is_local(backend.ip)]

        # Clear existing data.
        if self.portmap.has_key(listen):
            del self.portmap[listen]

        if len(looping_ips) > 0:
            logging.error("Attempted TCP loop.")
            return

        # If no backends, don't queue anything.
        if len(backends) == 0:
            return

        # Build our list of backends.
        config = self._endpoint_config(config)
        portmap_backends = []
        for backend in backends:
            portmap_backends.append((backend.ip, backend.port))

        # Update the portmap (including exclusive info).
        # NOTE: The reconnect/exclusive/client_subnets parameters
        # control how backends are mapped by the consumer, how machines
        # are cleaned up, etc. See the Consumer class and the metrics()
        # function below to understand the interactions there.
        self.portmap[listen] = (
            url,
            config.exclusive,
            # If disposable is True, pass dispose_min (which
            # may be 0). Else pass None.
            (config.disposable or None) and config.dispose_min,
            config.reconnect,
            portmap_backends,
            config.client_subnets)

    def save(self):
        self.consumer.set(self.portmap)
        self.producer.set(self.portmap.keys())

    def metrics(self):
        return self.consumer.metrics()

    def sessions(self):
        return self.consumer.sessions()

    def drop_session(self, client, backend):
        self.consumer.drop_session(client, backend)

    def pending(self):
        return self.consumer.pending()
