import hashlib
import os
import signal
import urlparse
import shutil
import glob
import re
import time
import threading
import logging
import subprocess
import tempfile

from mako.template import Template

from reactor.config import Config
from reactor.loadbalancer.connection import LoadBalancerConnection
from reactor.loadbalancer.utils import read_pid

class HaproxyManagerConfig(Config):

    config_file = Config.string(label="Configuration path",
        default="/etc/haproxy/haproxy.cfg",
        description="The configuration file for HAProxy.")

    pid_file = Config.string(label="Pid file",
        default="/var/run/haproxy.pid",
        description="The HAProxy pid file.")

    stats_path = Config.string(label="Stats socket path",
        default="/var/run/haproxy.sock",
        description="The stats socket path.")

    stats_mode = Config.string(label="Stats socket mode",
        default="0666",
        description="The stats permission mode.")

    global_opts = Config.list(label="Other global configuration options",
        default=[
            "log 127.0.0.1 local0",
            "log 127.0.0.1 local1 notice",
            "user haproxy",
            "group haproxy",
        ])

    maxconn = Config.integer(label="Maximum connection",
        default=5000,
        description="Maximum number of simultaneous connections.")

    clitimeout = Config.integer(label="Client timeout",
        default=50000,
        description="Client connection timeout.")

class HaproxyEndpointConfig(Config):

    balance = Config.select(label="Loadbalancing mode",
        default="roundrobin",
        options=[
            ("Roundrobin", "roundrobin"),
            ("URI-based", "uri"),
            ("Source-based", "source")],
        description="The loadbalancing mode used to choose backends.")

    sticky = Config.boolean(label="Sticky mode",
        default=True,
        description="Whether sessions should be sticky.")

    check_url = Config.string(label="Check URL",
        default="",
        description="If using HTTP, the URL used to check the backend.")

    errorloc = Config.string(label="Error location",
        default="",
        description="An error location used as ${errorloc}/${code}.")

    contimeout = Config.integer(label="Connection timeout",
        default=5000,
        description="A generic connection timeout.")

    srvtimeout = Config.integer(label="Server timeout",
        default=50000,
        description="Server connection timeout.")

class Connection(LoadBalancerConnection):

    """ Haproxy """

    _MANAGER_CONFIG_CLASS = HaproxyManagerConfig
    _ENDPOINT_CONFIG_CLASS = HaproxyEndpointConfig
    _SUPPORTED_URLS = {
        "http://([a-zA-Z0-9]+[a-zA-Z0-9.]*)(:[0-9]+|)(/.*|)": \
            lambda m: ("http", m.group(1), m.group(2), m.group(3)),
        "(http|tcp)://(:[0-9]+|)": \
            lambda m: (m.group(1), None, m.group(2), None)
    }

    def __init__(self, **kwargs):
        LoadBalancerConnection.__init__(self, **kwargs)
        template_file = os.path.join(os.path.dirname(__file__), 'haproxy.template')
        self.template = Template(filename=template_file)
        self.frontends = {}
        self.http_backends = {}
        self.tcp_backends = {}
        self.error_notify = kwargs.get("error_notify")

    def change(self, url, backends, config=None):
        # We use a simple hash of the URL as the backend key.
        hash_fn = hashlib.new('md5')
        hash_fn.update(url)
        uniq_id = hash_fn.hexdigest()

        # Parse the url because we need to know the netloc.
        (scheme, netloc, listen, path) = self.url_info(url)
        if listen:
            listen = int(listen)
        elif scheme == "http":
            listen = 80
        elif scheme == "tcp":
            raise Exception("Need listen port for TCP.")

        if path:
            # We don't support backend paths in haproxy.
            raise Exception("Paths are not supported by HAProxy.")

        # Select the correct set of frontends & backends.
        if scheme == "http":
            backend_map = self.http_backends
        elif scheme == "tcp":
            backend_map = self.tcp_backends

        # Clear the frontend.
        if listen in self.frontends:
            self.frontends[listen][1].remove((netloc, uniq_id))
            if len(self.frontends[listen][1]) == 0:
                del self.frontends[listen]

        # Check for a removal.
        if len(backends) == 0:
            if not uniq_id in backend_map:
                return

            # Pull out the backend.
            (ipspecs) = backend_map[uniq_id]
            del backend_map[uniq_id]
            return

        # Check for a conflict (default HTTP and TCP on same port).
        if self.frontends.get(listen, (scheme,))[0] != scheme:
            raise Exception("Conflicting mode rules.")

        # Grab the backend configuration.
        config = self._endpoint_config(config)
        ipspecs = []
        for backend in backends:
            if config.sticky:
                hash_fn = hashlib.new('md5')
                hash_fn.update("%s:%d" % (backend.ip, backend.port))
                cookie = hash_fn.hexdigest()
            else:
                hash_fn = hashlib.new('md5')
                hash_fn.update("nosticky")
                cookie = hash_fn.hexdigest()
            ipspecs.append("server %s:%d %s:%d weight %d cookie %s check" % \
                (backend.ip, backend.port, backend.ip, backend.port, backend.weight, cookie))

        # Add it to our list of backends and frontends.
        if not listen in self.frontends:
            self.frontends[listen] = (scheme, [])
        self.frontends[listen][1].append((netloc, uniq_id))
        backend_map[uniq_id] = (config, ipspecs)

    def save(self):
        # Render our given template.
        config = self._manager_config()
        conf = self.template.render(global_opts=config.global_opts,
                                    maxconn=config.maxconn,
                                    clitimeout=config.clitimeout,
                                    stats_path=config.stats_path,
                                    stats_mode=config.stats_mode,
                                    frontends=self.frontends,
                                    http_backends=self.http_backends,
                                    tcp_backends=self.tcp_backends)

        # Write out the config file.
        config_file = file(config.config_file, 'wb')
        config_file.write(conf)
        config_file.flush()
        config_file.close()

        # Restart gently.
        pid = read_pid(config.pid_file)
        if pid:
            subprocess.call([
                "haproxy",
                "-f", str(config.config_file),
                "-p", str(config.pid_file),
                "-sf", str(pid)],
                close_fds=True)
        else:
            subprocess.call(
                ["service", "haproxy", "start"],
                close_fds=True)

    def _sock_command(self, command):
        if not os.path.exists(self._manager_config().stats_path):
            return None
        socat = subprocess.Popen([
            "socat",
            "stdio",
            "unix-connect:%s" % self._manager_config().stats_path],
            close_fds=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE)
        (stdout, stderr) = socat.communicate(command + '\n')
        if socat.returncode != 0:
            return None
        return stdout.split("\n")

    def metrics(self):
        # Dump all proxyIds, server objects, all serverIds.
        output = self._sock_command("show stat -1 4 -1")
        if not output:
            return {}

        # Header is prefixed with '# '.
        header = output[0].strip()[2:]
        keys = header.split(",")
        data_keys = keys[2:]

        results = {}

        for line in output[1:]:
            # Skip blank lines.
            line = line.strip()
            if not line:
                continue

            # Slice the csv.
            chunks = line.split(",")
            port = chunks[1]

            # Extract all legimate keys.
            # (Obviously all keys are okay, but we can
            # only really aggregate the integer-based keys.)
            all_data = dict(zip(data_keys, chunks[2:]))
            def is_int(v):
                try:
                    int(v)
                    return True
                except:
                    return False
            valid_data = dict([(k, int(v)) for (k,v) in all_data.items() if is_int(v)])
            results[port] = [valid_data]

            # Notify errors if status is DOWN.
            if all_data.get('status') == 'DOWN' and self.error_notify:
                self.error_notify(port)

        # Reset counters for next time.
        self._sock_command("clear counters")
        return results
