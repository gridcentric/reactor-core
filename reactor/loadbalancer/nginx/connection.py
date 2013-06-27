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
from reactor.loadbalancer.netstat import connection_count

class NginxLogReader(object):
    def __init__(self, log_filename, filter=None):
        self.log_filename = log_filename
        self.filter = None
        if filter != None:
            self.filter = re.compile(filter)
        self.connected = False

    def connect(self):
        # Re-open the file by name.
        self.logfile = open(self.log_filename, 'r')

        # Seek to the end of the file, always.
        self.logfile.seek(0, 2)
        self.connected = True

    def nextline(self):
        # Open the file initially.
        if not(self.connected):
            try:
                self.connect()
            except IOError:
                return None

        line = self.logfile.readline().strip()
        while self.filter != None and line:
            # Apply the filter to the line.
            m = self.filter.match(line)
            if m != None:
                return m.groups()
            else:
                line = self.logfile.readline().strip()

        # If we got nothing, make sure we've got
        # the right file open (due to rotation) and
        # seek to the end where we should still be.
        if not(line):
            try:
                self.connect()
            except IOError:
                logging.warn("Unable to reopen Nginx log.")

        return line

class NginxLogWatcher(threading.Thread):
    """
    This will monitor the nginx access log.
    """
    def __init__(self, access_logfile):
        threading.Thread.__init__(self)
        self.daemon = True
        log_filter = "reactor> " \
                   + "\[([^\]]*)\]" \
                   + "[^<]*" \
                   + "<([^>]*?)>" \
                   + "[^<]*" \
                   + "<([^>]*?)>" \
                   + "[^<]*" \
                   + "<([^>]*?)>" \
                   + ".*"
        self.log = NginxLogReader(access_logfile, log_filter)
        self.execute = True
        self.lock = threading.Lock()
        self.last_update = time.time()
        self.record = {}

    def stop(self):
        self.execute = False

    def pull(self):
        # Swap out the records.
        self.lock.acquire()
        now = time.time()
        delta = now - self.last_update
        self.last_update = now
        record = self.record
        self.record = {}
        self.lock.release()

        # Compute the response times.
        for host in record:
            hits = record[host][0]
            metrics = \
                {
                "rate" : (hits, hits / delta),
                "response" : (hits, record[host][2] / hits),
                "bytes" : (hits, record[host][1] / delta),
                }
            record[host] = metrics

        return record

    def run(self):
        while self.execute:
            line = self.log.nextline()
            if not(line):
                # No updates.
                time.sleep(1.0)
            else:
                # We have some information.
                (timeinfo, host, body, response) = line
                self.lock.acquire()
                hostinfo = host.split(":")
                if len(hostinfo) > 1:
                    host = hostinfo[0]
                try:
                    if not(host in self.record):
                        self.record[host] = [0, 0, 0.0]
                    self.record[host][0] += 1
                    self.record[host][1] += int(body)
                    self.record[host][2] += float(response)
                except ValueError:
                    continue
                finally:
                    self.lock.release()

class NginxManagerConfig(Config):

    config_path = Config.string(label="Configuration Path",
        default="/etc/nginx/conf.d",
        description="The configuration directory for nginx.")

    site_path = Config.string(label="Sites-enabled Path",
        default="/etc/nginx/sites-enabled",
        description="The site path for nginx.")

class NginxEndpointConfig(Config):

    sticky_sessions = Config.boolean(label="Use Sticky Sessions", default=False,
        description="Enables nginx sticky sessions.")

    keepalive = Config.integer(label="Keepalive Connections", default=0,
        validate=lambda self: self.keepalive >= 0 or \
            Config.error("Keepalive must be non-negative."),
        description="Number of backend connections to keep alive.")

    ssl = Config.boolean(label="Use SSL", default=False,
        description="Configures nginx to handle SSL.")

    ssl_certificate = Config.string(label="SSL Certificate", default=None,
        description="An SSL certification in PEM format.")

    ssl_key = Config.string(label="SSL Key", default=None,
        description="An SSL key (not password protected).")

class Connection(LoadBalancerConnection):

    _MANAGER_CONFIG_CLASS = NginxManagerConfig
    _ENDPOINT_CONFIG_CLASS = NginxEndpointConfig

    def __init__(self, **kwargs):
        LoadBalancerConnection.__init__(self, **kwargs)
        self.tracked = {}
        template_file = os.path.join(os.path.dirname(__file__), 'nginx.template')
        self.template = Template(filename=template_file)
        self.log_reader = NginxLogWatcher("/var/log/nginx/access.log")
        self.log_reader.start()

    def description(self):
        return "HTTP-based (nginx)"

    def __del__(self):
        self.log_reader.stop()

    def _generate_ssl(self, uniq_id, config):
        key = config.ssl_key
        cert = config.ssl_certificate

        prefix = os.path.join(tempfile.gettempdir(), uniq_id)
        try:
            os.makedirs(prefix)
        except OSError:
            pass
        raw_file = os.path.join(prefix, "raw")
        key_file = os.path.join(prefix, "key")
        csr_file = os.path.join(prefix, "csr")
        crt_file = os.path.join(prefix, "crt")

        if key:
            # Save the saved key.
            f = open(key_file, 'w')
            f.write(key)
            f.close()
        elif not os.path.exists(key_file):
            # Genereate a new random key.
            subprocess.check_call(\
                "openssl genrsa -des3 -out %s -passout pass:1 1024" % \
                (raw_file), shell=True)
            subprocess.check_call(\
                "openssl rsa -in %s -passin pass:1 -out %s" % \
                (raw_file, key_file), shell=True)

        if cert:
            # Save the saved certificate.
            f = open(crt_file, 'w')
            f.write(cert)
            f.close()
        elif not os.path.exists(crt_file):
            # Generate a new certificate.
            subprocess.check_call(\
                "openssl req -new -key %s -batch -out %s" % \
                (key_file, csr_file), shell=True)
            subprocess.check_call(\
                "openssl x509 -req -in %s -signkey %s -out %s" % \
                (csr_file, key_file, crt_file), shell=True)

        # Return the certificate and key.
        return (crt_file, key_file)

    def _determine_nginx_pid(self):
        if os.path.exists("/var/run/nginx.pid"):
            pid_file = file("/var/run/nginx.pid", 'r')
            pid = pid_file.readline().strip()
            pid_file.close()
            return int(pid)
        else:
            return None

    def clear(self):
        # Remove all sites configurations.
        for conf in glob.glob(os.path.join(self._manager_config().site_path, "*")):
            try:
                os.remove(conf)
            except OSError:
                pass

        # Remove all tracked connections.
        self.tracked = {}

    def redirect(self, url, names, other, config=None):
        self.change(url, names, [], [], redirect=other)

    def change(self, url, names, ips, redirect=False, config=None):
        # We use a simple hash of the URL as the file name for the configuration file.
        uniq_id = hashlib.md5(url).hexdigest()
        conf_filename = "%s.conf" % uniq_id

        # Check for a removal.
        if not(redirect) and len(ips) == 0:
            # Remove the connection from our tracking list.
            if uniq_id in self.tracked:
                del self.tracked[uniq_id]

            try:
                os.remove(os.path.join(self._manager_config().site_path, conf_filename))
            except OSError:
                logging.warn("Unable to remove file: %s" % conf_filename)
            return

        # Parse the url because we need to know the netloc.
        (scheme, netloc, path, params, query, fragment) = urlparse.urlparse(url)

        # Check that this is a URL we should be managing.
        if not(scheme == "http") and not(scheme == "https"):
            return

        # Grab a sensible listen port.
        w_port = netloc.split(":")
        netloc = w_port[0]
        if len(w_port) == 1:
            if scheme == "http":
                listen = 80
            elif scheme == "https":
                listen = 443
        else:
            try:
                listen = int(w_port[1])
            except ValueError:
                logging.warn("Invalid listen port: %s" % str(w_port[1]))
                return

        # Ensure that there is a path.
        path = path or "/"

        # If there is no netloc, set it so False.
        netloc = netloc or False

        # Add the connection to our tracking list, and
        # compute the specification for the template.
        ipspecs = []
        self.tracked[uniq_id] = []
        extra = ''

        # Figure out if we're doing SSL.
        config = self._endpoint_config(config)
        if config.ssl:
            # Try to either extract existing keys and certificates, or
            # we dynamically generate a local cert here (for testing).
            (ssl_certificate, ssl_key) = self._generate_ssl(uniq_id, config)

            # Since we are front-loading SSL, just use raw HTTP to connect
            # to the backends. If the user doesn't want this, they should disable
            # the SSL key in the nginx config.
            if scheme == "https":
                scheme = "http"
        else:
            # Don't use any SSL backend.
            (ssl_certificate, ssl_key) = (None, None)

        if not(redirect):
            for backend in ips:
                if not(backend.port):
                    port = listen
                else:
                    port = backend.port
                ipspecs.append("%s:%d weight=%d" % (backend.ip, port, backend.weight))
                self.tracked[uniq_id].append((backend.ip, port))

            # Compute any extra bits for the template.
            if self._endpoint_config(config).sticky_sessions:
                extra += '    sticky;\n'
            if self._endpoint_config(config).keepalive:
                extra += '    keepalive %d single;\n' % self._endpoint_config(config).keepalive

        # Render our given template.
        conf = self.template.render(id=uniq_id,
                                    url=url,
                                    netloc=netloc,
                                    path=path,
                                    scheme=scheme,
                                    listen=str(listen),
                                    ipspecs=ipspecs,
                                    redirect=redirect,
                                    ssl=config.ssl,
                                    ssl_certificate=ssl_certificate,
                                    ssl_key=ssl_key,
                                    extra=extra)

        # Write out the config file.
        config_file = file(os.path.join(self._manager_config().site_path, conf_filename), 'wb')
        config_file.write(conf)
        config_file.flush()
        config_file.close()

    def save(self):
        # Copy over our base configuration.
        shutil.copyfile(os.path.join(os.path.dirname(__file__), 'reactor.conf'),
                        os.path.join(self._manager_config().config_path, 'reactor.conf'))

        # Send a signal to NginX to reload the configuration
        # (Note: we might need permission to do this!!)
        nginx_pid = self._determine_nginx_pid()
        if nginx_pid:
            os.kill(nginx_pid, signal.SIGHUP)

    def metrics(self):
        # Grab the log records.
        records = self.log_reader.pull()

        # Grab the active connections.
        active_connections = connection_count()

        for connection_list in self.tracked.values():
            for (ip, port) in connection_list:
                active = active_connections.get((ip, port), 0)
                if not(ip in records):
                    records[ip] = {}
                records[ip]["active"] = (1, active)

        return records
