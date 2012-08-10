import re
import time
import threading
import random

import flowcontrol
import flowcontrol.daemon

from gridcentric.pancake.config import SubConfig
from gridcentric.pancake.loadbalancer.connection import LoadBalancerConnection
from gridcentric.pancake.loadbalancer.netstat import connection_count

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
        self.flush()

    def stop(self):
        self.execute = False

    def handle(self, req):
        self.cond.acquire()
        try:
            # Index by the destination port.
            port = req.dst[1]
            if not(self.ports.has_key(port)):
                req.drop()
                return False

            # Create a map of the IPs.
            backends = self.ports[req.dst[1]]
            ipmap = {}
            ipmap.update(backends)
            ips = ipmap.keys()

            # Find a backend IP (exclusive or not).
            if self.exclusive:
                ip = self.connection._find_ip(ips)
            else:
                ip = ips[random.randint(0, len(ips)-1)]

            # Either redirect or drop the connection.
            if ip:
                req.redirect(ip, ipmap[ip])
                return True
            else:
                return False
        finally:
            self.cond.release()

    def flush(self):
        # Attempt to flush all requests.
        while self.producer.has_pending():
            req = self.producer.next()
            if not(self.handle(req)):
                self.producer.push(req)
                break

    def run(self):
        while self.execute:
            req = self.producer.next()

            if self.handle(req):
                # If we can handle this request,
                # make sure that the queue is flushed.
                self.flush()
            else:
                # If we can't handle this request right
                # now, we wait and will try it again on
                # the next round.
                self.producer.push(req)
                time.sleep(5.0)

class FlowControlProducer(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.execute = True
        self.monitor = flowcontrol.FlowControl()
        self.pending = []
        self.cond    = threading.Condition()

    def stop(self):
        self.cond.acquire()
        self.execute = False
        del self.monitor
        flowcontrol.daemon.stop()
        self.cond.release()

    def set(self, ports):
        # Set the appropriate ports.
        self.cond.acquire()
        try:
            for port in ports:
                self.monitor.add_port(port)
        finally:
            self.cond.release()

    def next(self, timeout=None):
        # Pull the next request.
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

    def push(self, req):
        # Push back a request.
        self.cond.acquire()
        try:
            self.pending.insert(0, req)
            self.cond.notifyAll()
        finally:
            self.cond.release()

    def has_pending(self):
        # Check for pending requests.
        self.cond.acquire()
        try:
            return self.execute and len(self.pending) > 0
        finally:
            self.cond.release()

    def run(self):
        # Process connections from monitor.
        while True:
            req = self.monitor.next(timeout=1000)
            self.cond.acquire()

            # Check if we should continue executing.
            if not(self.execute):
                self.cond.notifyAll()
                self.cond.release()
                break
            if not(req):
                self.cond.release()
                continue

            # Push the request into the queue.
            self.pending.append(req)
            print "REQUEST %s is now PENDING" % req.src[0]
            self.cond.notifyAll()
            self.cond.release()

class TcpLoadBalancerConfig(SubConfig):

    def exclusive(self):
        # Whether or not the server is exclusive.
        return self._get("exclusive", "true").lower() == "true"

class TcpLoadBalancerConnection(LoadBalancerConnection):

    def __init__(self, name, scale_manager, config):
        LoadBalancerConnection.__init__(self, name, scale_manager)
        self.tracked = {}
        self.portmap = {}
        self.config = config

        self.producer = FlowControlProducer()
        self.producer.start()
        self.consumer = ConnectionConsumer(self, self.producer, self.config.exclusive())
        self.consumer.start()

    def __del__(self):
        self.producer.stop()
        self.consumer.stop()

    def clear(self):
        # Remove all mapping and tracking configuration.
        self.portmap = {}
        self.tracked = {}

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

    def metrics(self):
        records = {}

        # Grab the active connections.
        active_connections = connection_count()

        for connection_list in self.tracked.values():
            for (ip, port) in connection_list:
                active = active_connections.get((ip, port), 0)
                records[ip] = { "active" : (1, active) }

        return records
