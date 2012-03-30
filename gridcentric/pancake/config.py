#!/usr/bin/env python

import ConfigParser
import logging
import socket
import re
from StringIO import StringIO

from gridcentric.pancake.exceptions import ConfigFileNotFound

class Config(object):
    
    def __init__(self, defaultcfg = None):
        self.defaultcfg = defaultcfg
        self.config = None
    
    def _get(self, section, key):
        if self.config.has_option(section, key):
            return self.config.get(section, key)
        else:
            return None

    def _load(self, config_str):
        self.config = ConfigParser.SafeConfigParser()
        if self.defaultcfg != None:
            self.config.readfp(self.defaultcfg)
        if config_str != None:
            self.config.readfp(StringIO(config_str))

class ManagerConfig(Config):
        
    def __init__(self, config_str):
        super(ManagerConfig, self).__init__(StringIO("""
[manager]
health_check=30
mark_maximum=4

[loadbalancer]
config_path=/etc/nginx/conf.d
site_path=/etc/nginx/sites-enabled
"""))
        self._load(config_str)

    def config_path(self):
        """
        The config path is where general loadbalancer configurations should go. This maybe the
        same as the config path.
        """
        return self._get("loadbalancer", "config_path")
    
    def site_path(self):
        """
        The site path is where the particular service configurations should go. This maybe the
        same as the config path.
        """
        return self._get("loadbalancer", "site_path")

    def mark_maximum(self):
        return int(self._get("manager", "mark_maximum"))

    def health_check(self):
        return float(self._get("manager", "health_check"))

class ServiceConfig(Config):
    
    def __init__(self, config_str):
        super(ServiceConfig, self).__init__(StringIO("""
[service]
url=http://example.com
static_instances=

[scaling]
min_instances=1
max_instances=1
quiet_period=10
metrics=

[nova]
instance_id=0
authurl=http://localhost:8774/v1.1/
user=admin
apikey=admin
project=admin
"""))
        self._load(config_str)
        
    def reload(self, config_str):
        if self.config == None:
            self._load(config_str)
        else:
            self.config.readfp(StringIO(config_str))

    def url(self):
        return self._get("service", "url")

    def instance_id(self):
        return int(self._get("nova", "instance_id"))

    def min_instances(self):
        return int(self._get("scaling", "min_instances") or 1)

    def max_instances(self):
        return int(self._get("scaling", "max_instances") or 1)

    def quiet_period(self):
        return float(self._get("scaling", "quiet_period"))

    def _generate_metrics(self, metrics):
        metric_fcns = {}
        for spec in metrics:
            m = re.match("(.+)([<=>]+)(.+)", spec)
            if not(m):
                continue
            try:
                key = m.group(1)
                comp = m.group(2)
                val = float(m.group(3))
            except ValueError:
                continue
            if comp == "<":
                metric_fcns[key] = lambda x: -(x < val)
            elif comp == ">":
                metric_fcns[key] = lambda x: (x > val)
            elif comp == "<=":
                metric_fcns[key] = lambda x: -(x <= val)
            elif comp == ">=":
                metric_fcns[key] = lambda x: (x >= val)

        def evaluate_all(invals):
            total = 0
            # For each active instance.
            for inst in invals:
                # For each metric available.
                for key in inst:
                    # If it's defined in our metric spec...
                    if key in metric_fcns:
                        val = metric_fcns[key](inst[key])
                        if val:
                            logging.debug("metric active: %s@%f -> %d" %
                                          (key, float(inst[key]), val))
                        total += val
            return total

        # Return the generated function.
        return evaluate_all

    def metrics(self):
        metrics = self._get("scaling", "metrics").split(",")
        #return self._generate_metrics(metrics)
        return metrics

    def auth_info(self):
        return (self._get("nova", "authurl"),
                self._get("nova", "user"),
                self._get("nova", "apikey"),
                self._get("nova", "project"))

    def static_ips(self):
        """ Returns a list of static ips associated with the configured static instances. """
        static_instances = self._get("service", "static_instances").split(",")

        # (dscannell) The static instances can be specified either as IP addresses or hostname. 
        # If its an IP address then we are done. If its a hostname then we need to do a lookup
        # to determine its IP address.
        ip_addresses = []
        for static_instance in static_instances:
            try:
                if static_instance != '':
                    ip_addresses += [socket.gethostbyname(static_instance)]
            except:
                logging.warn("Failed to determine the ip address for the static instance %s." %
                             static_instance)
        return ip_addresses
