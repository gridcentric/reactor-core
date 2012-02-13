#!/usr/bin/env python

import hashlib
import os
import signal
import urlparse

from mako.template import Template

from gridcentric.pancake.loadbalancer.connection import LoadBalancerConnection

class NginxLoadBalancerConnection(LoadBalancerConnection):
    
    def __init__(self, config_path):
        self.config_path = config_path
        self.nginx_pid = self._determine_nginx_pid()
        template_file = os.path.join(os.path.dirname(__file__),'nginx.template')
        self.template = Template(filename=template_file)
    
    def _determine_nginx_pid(self):
        if os.path.exists("/var/run/nginx.pid"):
            pid_file = file("/var/run/nginx.pid",'r')
            pid = pid_file.readline().strip()
            pid_file.close()
            return int(pid)
    
    def update(self, url, addresses):
        
        # We use a simple hash of the URL as the file name for the configuration file.
        conf_filename = hashlib.md5(url).hexdigest()
        
        # Parse the url because we need to know the netloc
        (scheme, netloc, path, params, query, fragment) = urlparse.urlparse(url)
        conf = self.template.render(url=url, netloc=netloc, addresses=addresses)
        
        # Write out the config file
        config_file = file(os.path.join(self.config_path,conf_filename), 'wb')
        config_file.write(conf)
        config_file.flush()
        config_file.close()
        
        # Send a signal to NginX to reload the configuration
        # (Note: we might need permission to do this!!)
        os.kill(self.nginx_pid, signal.SIGHUP)
