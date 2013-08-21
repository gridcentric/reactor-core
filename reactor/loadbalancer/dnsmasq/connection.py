import os
import signal

from mako.template import Template

from reactor.config import Config
from reactor.loadbalancer.connection import LoadBalancerConnection

class DnsmasqManagerConfig(Config):

    config_path = Config.string(label="Configuration Path", default="/etc/dnsmasq.d", \
        description="The configuration directory to insert base configuration.")

    hosts_path = Config.string(label="Site Config Path", default="/etc/hosts.reactor", \
        description="The directory in which to generate site configurations.")

class Connection(LoadBalancerConnection):
    """ DNS-based (dnsmasq) """

    _MANAGER_CONFIG_CLASS = DnsmasqManagerConfig
    _SUPPORTED_URLS = {
        "dns://([a-zA-Z0-9]+[a-zA-Z0-9.]*)" : lambda m: m.group(1)
    }

    def __init__(self, **kwargs):
        super(Connection, self).__init__(**kwargs)

        # the __path__ symbol is set to the path from where this
        # module gets loaded.  In our case, the parent module loads
        # us, so the path is actually the parent directory, not the
        # directory of this source code (python doesn't statically
        # bind the symbol at compile-time like C.  We do a basic file
        # check just in case.
        template_file = os.path.join(os.path.dirname(__file__), 'dnsmasq.template')
        if not os.path.isfile(template_file):
            template_file = os.path.join(os.path.dirname(__file__), 'dnsmasq', 'dnsmasq.template')
        self.template = Template(filename=template_file)
        self.ipmappings = {}

    def _determine_dnsmasq_pid(self):
        if os.path.exists("/var/run/dnsmasq/dnsmasq.pid"):
            pid_file = file("/var/run/dnsmasq/dnsmasq.pid",'r')
            pid = pid_file.readline().strip()
            pid_file.close()
            return int(pid)
        else:
            return None

    def clear(self):
        self.ipmappings = {}

    def change(self, url, backends, config=None):
        # Save the mappings.
        name = self.url_info(url)
        self.ipmappings[name] = backends

    def save(self):
        # Compute the address mapping.
        # NOTE: We do not currently support the weight parameter
        # for dns-based loadbalancer. This may be implemented in
        # the future -- but for now this parameter is ignored.
        ipmap = {}
        for (name, backends) in self.ipmappings.items():
            for backend in backends:
                if not(backend.ip in ipmap):
                    ipmap[backend.ip] = []
                ipmap[backend.ip].append(name)

        # Write out our hosts file.
        hosts = open(self._manager_config().hosts_path, 'wb')
        for (address, names) in ipmap.items():
            for name in set(names):
                hosts.write("%s %s\n" % (address, name))
        hosts.close()

        # Write out our configuration template.
        conf = self.template.render(hosts=self._manager_config().hosts_path)

        # Write out the config file.
        config_file = file(os.path.join(self._manager_config().config_path, "reactor.conf"), 'wb')
        config_file.write(conf)
        config_file.close()

        # Send a signal to dnsmasq to reload the configuration
        # (Note: we might need permission to do this!!).
        dnsmasq_pid = self._determine_dnsmasq_pid()
        if dnsmasq_pid:
            os.kill(dnsmasq_pid, signal.SIGHUP)
