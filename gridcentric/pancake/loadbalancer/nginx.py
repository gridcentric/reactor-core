#!/usr/bin/env python

import hashlib
import os
import signal
import urlparse
import glob

from mako.template import Template

from gridcentric.pancake.loadbalancer.connection import LoadBalancerConnection

class NginxLoadBalancerConnection(LoadBalancerConnection):
    
    def __init__(self, config_path):
        self.config_path = config_path
        template_file = os.path.join(os.path.dirname(__file__),'nginx.template')
        self.template = Template(filename=template_file)
    
    def _determine_nginx_pid(self):
        if os.path.exists("/var/run/nginx.pid"):
            pid_file = file("/var/run/nginx.pid",'r')
            pid = pid_file.readline().strip()
            pid_file.close()
            return int(pid)
        else:
            return None

    def clear(self):
        for conf in glob.glob(os.path.join(self.config_path, "*")):
            try:
                os.remove(conf)
            except OSError:
                pass

    def change(self, url, addresses):
        # We use a simple hash of the URL as the file name for the configuration file.
        uniq_id = hashlib.md5(url).hexdigest()
        conf_filename = "%s.conf" % uniq_id

        # Parse the url because we need to know the netloc
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

        conf = self.template.render(id=uniq_id,
                                    url=url,
                                    netloc=netloc,
                                    path=path,
                                    scheme=scheme,
                                    port=port,
                                    addresses=addresses)

        # Write out the config file
        config_file = file(os.path.join(self.config_path,conf_filename), 'wb')
        config_file.write(conf)
        config_file.flush()
        config_file.close()

    def save(self):
        # Send a signal to NginX to reload the configuration
        # (Note: we might need permission to do this!!)
        nginx_pid = self._determine_nginx_pid()
        if nginx_pid:
            os.kill(nginx_pid, signal.SIGHUP)
