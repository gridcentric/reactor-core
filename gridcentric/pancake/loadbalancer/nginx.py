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

from mako.template import Template

from gridcentric.pancake.config import SubConfig
from gridcentric.pancake.loadbalancer.connection import LoadBalancerConnection
from gridcentric.pancake.loadbalancer.netstat import connection_count

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
        log_filter = "pancake> " \
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

class NginxLoadBalancerConfig(SubConfig):

    def config_path(self):
        return self._get("config_path", "/etc/nginx/conf.d")

    def site_path(self):
        return self._get("site_path", "/etc/nginx/sites-enabled")

    def sticky_sessions(self):
        return self._get("sticky_sessions", "false").lower() == "true"

    def keepalive(self):
        try:
            return int(self._get("keepalive", '0'))
        except:
            return 0

class NginxLoadBalancerConnection(LoadBalancerConnection):

    def __init__(self, name, scale_manager, config):
        LoadBalancerConnection.__init__(self, name, scale_manager)
        self.tracked = {}
        self.config = config
        template_file = os.path.join(os.path.dirname(__file__), 'nginx.template')
        self.template = Template(filename=template_file)
        self.log_reader = NginxLogWatcher("/var/log/nginx/access.log")
        self.log_reader.start()

    def __del__(self):
        self.log_reader.stop()

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
        for conf in glob.glob(os.path.join(self.config.site_path(), "*")):
            try:
                os.remove(conf)
            except OSError:
                pass

        # Remove all tracked connections.
        self.tracked = {}

    def redirect(self, url, names, other, manager_ips):
        self.change(url, names, [], [], [], redirect=other)

    def change(self, url, names, public_ips, manager_ips, private_ips, redirect=False):
        # We use a simple hash of the URL as the file name for the
        # configuration file.
        uniq_id = hashlib.md5(url).hexdigest()
        conf_filename = "%s.conf" % uniq_id

        # There are no privacy concerns here, so we can mix all public and
        # private addresses. (But it doesn't make sense to include the IPs
        # for the managers).
        ips = public_ips + private_ips

        # Check for a removal.
        if not(redirect) and len(ips) == 0:
            # Remove the connection from our tracking list.
            if uniq_id in self.tracked:
                del self.tracked[uniq_id]

            try:
                os.remove(os.path.join(self.config.site_path(), conf_filename))
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
                return

        # Ensure that there is a path.
        path = path or "/"

        # Ensure that there is a server name.
        netloc = netloc or "example.com"

        # Add the connection to our tracking list, and
        # compute the specification for the template.
        ipspecs = []
        self.tracked[uniq_id] = []
        extra = ''

        if not(redirect):
            for backend in ips:
                if not(backend.port):
                    port = listen
                else:
                    port = backend.port
                ipspecs.append("%s:%d weight=%d" % (backend.ip, port, backend.weight))
                self.tracked[uniq_id].append((backend.ip, port))

            # Compute any extra bits for the template.
            if self.config.sticky_sessions():
                extra += '    sticky;\n'
            if self.config.keepalive():
                extra += '    keepalive %d single;\n' % self.config.keepalive()

        # Render our given template.
        conf = self.template.render(id=uniq_id,
                                    url=url,
                                    netloc=netloc,
                                    path=path,
                                    scheme=scheme,
                                    listen=str(listen),
                                    ipspecs=ipspecs,
                                    redirect=redirect,
                                    extra=extra)

        # Write out the config file.
        config_file = file(os.path.join(self.config.site_path(), conf_filename), 'wb')
        config_file.write(conf)
        config_file.flush()
        config_file.close()

    def save(self):
        # Copy over our base configuration.
        shutil.copyfile(os.path.join(os.path.dirname(__file__), 'pancake.conf'),
                        os.path.join(self.config.config_path(), 'pancake.conf'))

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
