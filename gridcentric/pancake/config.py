import ConfigParser
import logging
import socket
import re
from StringIO import StringIO

from gridcentric.pancake.exceptions import ConfigFileNotFound

class Config(object):

    def __init__(self, config_str=''):
        self.default = ConfigParser.SafeConfigParser()
        self.config  = ConfigParser.SafeConfigParser()
        self._load(config_str)
        self.clean = True

    def _get(self, section, key, default):
        # Set the default value.
        if not(self.default.has_section(section)):
            self.default.add_section(section)
        self.default.set(section, key, default)

        # Get the real value.
        if self.config.has_option(section, key):
            return self.config.get(section, key)
        else:
            return default

    def _set(self, section, key, value):
        if not(self.config.has_section(section)):
            self.config.add_section(section)

        # Check for a same value.
        if self.config.has_option(section, key) and \
            self.config.get(section, key) == value:
            return
        else:
            self.config.set(section, key, value)
            self.clean = False

    def _is_clean(self):
        return self.clean

    def _load(self, config_str):
        if config_str != None:
            self.config.readfp(StringIO(config_str))

    def reload(self, config_str):
        self.config.readfp(StringIO(config_str))

    def __str__(self):
        config_value = StringIO()
        self.default.write(config_value)
        self.config.write(config_value)
        return config_value.getvalue()

class ConfigView(object):

    def __init__(self, config, section):
        self.config  = config
        self.section = section

    def get(self, key, default):
        return self.config._get(self.section, key, default)

class ManagerConfig(Config):

    def loadbalancer_names(self):
        """ The name of the loadbalancer. """
        return self._get("manager", "loadbalancer", "").split(",")

    def loadbalancer_config(self, name):
        """ The set of keys required to configure the loadbalancer. """
        return ConfigView(self, "loadbalancer:%s" % name)

    def mark_maximum(self, label):
        if label in ['unregistered', 'decommissioned']:
            return int(self._get("manager", "%s_wait" % (label), "20"))

    def keys(self):
        return int(self._get("manager", "keys", "64"))

    def health_check(self):
        return float(self._get("manager", "health_check", "5"))

class EndpointConfig(Config):

    def url(self):
        return self._get("endpoint", "url", '')

    def port(self):
        return int(self._get("endpoint", "port", "80"))

    def public(self):
        return self._get("endpoint", "public", "true") == "true"

    def enabled(self):
        return self._get("endpoint", "enabled", "false") == "true"

    def min_instances(self):
        return int(self._get("scaling", "min_instances", "1"))

    def max_instances(self):
        return int(self._get("scaling", "max_instances", "1"))

    def rules(self):
        return self._get("scaling", "rules", "").split(",")

    def ramp_limit(self):
        return int(self._get("scaling", "ramp_limit", "5"))

    def source_url(self):
        return self._get("scaling", "url", "")

    def cloud_type(self):
        return self._get("endpoint", "cloud", "none")

    def cloud_config(self):
        return ConfigView(self, "cloud:%s" % self.cloud_type())

    def get_endpoint_auth(self):
        return (self._get("endpoint", "auth_hash", ""),
                self._get("endpoint", "auth_salt", ""),
                self._get("endpoint", "auth_algo", ""))

    def static_ips(self):
        """ Returns a list of static ips associated with the configured static instances. """
        static_instances = self._get("endpoint", "static_instances", "").split(",")

        # (dscannell) The static instances can be specified either as IP
        # addresses or hostname.  If its an IP address then we are done. If its
        # a hostname then we need to do a lookup to determine its IP address.
        ip_addresses = []
        for static_instance in static_instances:
            try:
                if static_instance != '':
                    ip_addresses += [socket.gethostbyname(static_instance)]
            except:
                logging.warn("Failed to determine the ip address "
                             "for the static instance %s." % static_instance)

        return ip_addresses
