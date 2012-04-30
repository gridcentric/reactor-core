import hashlib
import os
import signal
import urlparse
import shutil
import glob
import re
import time
import threading

from mako.template import Template

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
                pass

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

        # Grab all active connections.
        active_connections = connection_count()

        # Compute the response times.
        for host in record:
            hits = record[host][0]
            metrics = \
                {
                "rate" : (hits, hits / delta),
                "response" : (hits, record[host][2] / hits),
                "bytes" : (hits, record[host][1] / delta),
                "active" : (1, active_connections.get(host, 0)),
                }
            del active_connections[host]
            record[host] = metrics

        # Compute the active counts.
        for host in active_connections:
            metrics = \
                {
                "rate" : (0, 0.0),
                "response" : (0, 0.0),
                "bytes" : (0, 0),
                "active" : (1, active_connections.get(host, 0)),
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

class NginxLoadBalancerConnection(LoadBalancerConnection):
    
    def __init__(self, config_path, site_path):
        self.config_path = config_path
        self.site_path = site_path
        template_file = os.path.join(os.path.dirname(__file__),'nginx.template')
        self.template = Template(filename=template_file)
        self.log_reader = NginxLogWatcher("/var/log/nginx/access.log")
        self.log_reader.start()

    def _determine_nginx_pid(self):
        if os.path.exists("/var/run/nginx.pid"):
            pid_file = file("/var/run/nginx.pid",'r')
            pid = pid_file.readline().strip()
            pid_file.close()
            return int(pid)
        else:
            return None

    def clear(self):
        for conf in glob.glob(os.path.join(self.site_path, "*")):
            try:
                os.remove(conf)
            except OSError:
                pass

    def change(self, url, addresses):
        # We use a simple hash of the URL as the file name for the configuration file.
        uniq_id = hashlib.md5(url).hexdigest()
        conf_filename = "%s.conf" % uniq_id

        # Check for a removal.
        if len(addresses) == 0:
            try:
                os.remove(os.path.join(self.site_path,conf_filename))
            except OSError:
                pass
            return

        # Parse the url because we need to know the netloc.
        (scheme, netloc, path, params, query, fragment) = urlparse.urlparse(url)
        w_port = netloc.split(":")
        netloc = w_port[0]
        if len(w_port) == 1:
            if scheme == "http":
                port = "80"
            elif scheme == "https":
                port = "443"
            else:
                port = "80"
        else:
            port = w_port[1]

        # Ensure that there is a path.
        path = path or "/"

        # Render our given template.
        conf = self.template.render(id=uniq_id,
                                    url=url,
                                    netloc=netloc,
                                    path=path,
                                    scheme=scheme,
                                    port=port,
                                    addresses=addresses)

        # Write out the config file.
        config_file = file(os.path.join(self.site_path,conf_filename), 'wb')
        config_file.write(conf)
        config_file.flush()
        config_file.close()

    def save(self):
        # Copy over our base configuration.
        shutil.copyfile(os.path.join(os.path.dirname(__file__),'pancake.conf'),
                        os.path.join(self.config_path,'pancake.conf'))

        # Send a signal to NginX to reload the configuration
        # (Note: we might need permission to do this!!)
        nginx_pid = self._determine_nginx_pid()
        if nginx_pid:
            os.kill(nginx_pid, signal.SIGHUP)

    def metrics(self):
        return self.log_reader.pull()
