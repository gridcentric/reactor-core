import ConfigParser
import logging
import socket
import re
from StringIO import StringIO

from gridcentric.pancake.exceptions import ConfigFileNotFound

class Config(object):

    def __init__(self, defaultcfg=None):
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

    def reload(self, config_str):
        if self.config == None:
            self._load(config_str)
        else:
            self.config.readfp(StringIO(config_str))

    def __str__(self):
        config_value = StringIO()
        self.config.write(config_value)
        return config_value.getvalue()

class ManagerConfig(Config):

    def __init__(self, config_str):
        super(ManagerConfig, self).__init__(StringIO("""
[manager]
health_check=5
unregistered_wait=20
decommissioned_wait=5
keys=64
loadbalancer=nginx,dnsmasq

[loadbalancer:nginx]
config_path=/etc/nginx/conf.d
site_path=/etc/nginx/sites-enabled

[loadbalancer:dnsmasq]
config_path=/etc/dnsmasq.d
hosts_path=/etc/hosts.pancake
"""))
        self._load(config_str)

    def loadbalancer_names(self):
        """
        The name of the loadbalancer.
        """
        return self._get("manager", "loadbalancer").split(",")

    def loadbalancer_config(self, name):
        """
        The set of keys required to configure the loadbalancer.
        """
        result = {}
        if self.config.has_section("loadbalancer:%s" % name):
            result.update(self.config.items("loadbalancer:%s" % name))
        return result

    def mark_maximum(self, label):
        if label in ['unregistered', 'decommissioned']:
            return int(self._get("manager", "%s_wait" % (label)))


    def keys(self):
        return int(self._get("manager", "keys"))

    def health_check(self):
        return float(self._get("manager", "health_check"))

class ServiceConfig(Config):

    def __init__(self, config_str):
        super(ServiceConfig, self).__init__(StringIO("""
[service]
url=http://example.com
static_instances=
port=
auth_hash=
auth_salt=
auth_algo=sha1

[scaling]
min_instances=1
max_instances=1
metrics=
source=

[nova]
instance_id=0
authurl=http://localhost:8774/v1.1/
user=admin
apikey=admin
project=admin
"""))
        self._load(config_str)

    def url(self):
        return self._get("service", "url")

    def port(self):
        return self._get("service", "port")

    def instance_id(self):
        return int(self._get("nova", "instance_id"))

    def min_instances(self):
        return int(self._get("scaling", "min_instances") or 1)

    def max_instances(self):
        return int(self._get("scaling", "max_instances") or 1)

    def metrics(self):
        return self._get("scaling", "metrics").split(",")

    def source(self):
        return self._get("scaling", "source")

    def get_service_auth(self):
        return (self._get("service", "auth_hash"),
                self._get("service", "auth_salt"),
                self._get("service", "auth_algo"))

    def auth_info(self):
        return (self._get("nova", "authurl"),
                self._get("nova", "user"),
                self._get("nova", "apikey"),
                self._get("nova", "project"))

    def static_ips(self):
        """ Returns a list of static ips associated with the configured static instances. """
        static_instances = self._get("service", "static_instances").split(",")

        # (dscannell) The static instances can be specified either as IP
        # addresses or hostname.  If its an IP address then we are done. If its
        # a hostname then we need to do a lookup to determine its IP address.
        ip_addresses = []
        for static_instance in static_instances:
            try:
                if static_instance != '':
                    ip_addresses += [socket.gethostbyname(static_instance)]
            except:
                logging.warn("Failed to determine the ip address for the static instance %s." %
                             static_instance)
        return ip_addresses
