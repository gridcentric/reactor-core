import os
import signal

from mako.template import Template

from gridcentric.pancake.config import SubConfig
from gridcentric.pancake.loadbalancer.connection import LoadBalancerConnection
from gridcentric.pancake.loadbalancer.netstat import connection_count

class DnsmasqLoadBalancerConfig(SubConfig):

    def config_path(self):
        return self._get("config_path", "/etc/dnsmasq.d")

    def hosts_path(self):
        return self._get("hosts_path", "/etc/hosts.pancake")

class DnsmasqLoadBalancerConnection(LoadBalancerConnection):
    
    def __init__(self, config, scale_manager):
        self.config = config
        self.scale_manager = scale_manager
        template_file = os.path.join(os.path.dirname(__file__),'dnsmasq.template')
        self.template = Template(filename=template_file)
        self.mappings = {}

    def _determine_dnsmasq_pid(self):
        if os.path.exists("/var/run/dnsmasq/dnsmasq.pid"):
            pid_file = file("/var/run/dnsmasq/dnsmasq.pid",'r')
            pid = pid_file.readline().strip()
            pid_file.close()
            return int(pid)
        else:
            return None

    def clear(self):
        self.mappings = {}

    def change(self, url, names, public_ips, private_ips):
        # Save the mappings.
        for name in names:
            self.mappings[name] = public_ips

    def save(self):
        # Compute the address mapping.
        # NOTE: We do not currently support the weight parameter
        # for dns-based loadbalancer. This may be implemented in
        # the future -- but for now this parameter is ignored.
        ipmap = {}
        for (name, backends) in self.mappings.items():
            for backend in backends:
                if not(backend.ip in ipmap):
                    ipmap[backend.ip] = []
                ipmap[backend.ip].append(name)

        # Write out our hosts file.
        hosts = open(self.config.hosts_path(), 'wb')
        for (address, names) in ipmap.items():
            hosts.write("%s %s\n" % (address, " ".join(set(names))))
        hosts.close()

        # Make sure we have a domain.
        domain = self.scale_manager.domain
        if not(domain):
            domain = "example.com"

        # Write out our configuration template.
        conf = self.template.render(domain=domain, hosts=self.config.hosts_path())

        # Write out the config file.
        config_file = file(os.path.join(self.config.config_path(), "pancake.conf"), 'wb')
        config_file.write(conf)
        config_file.flush()
        config_file.close()

        # Send a signal to dnsmasq to reload the configuration
        # (Note: we might need permission to do this!!).
        dnsmasq_pid = self._determine_dnsmasq_pid()
        if dnsmasq_pid:
            os.kill(dnsmasq_pid, signal.SIGHUP)

    def metrics(self):
        return {}
