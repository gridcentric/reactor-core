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
    
    def __init__(self, name, scale_manager, config):
        LoadBalancerConnection.__init__(self, name, scale_manager)
        self.config = config
        template_file = os.path.join(os.path.dirname(__file__),'dnsmasq.template')
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

    def redirect(self, url, names, other_url, manager_ips):
        # We simply serve up the public servers as our DNS
        # records. It's very difficult to implement CNAME
        # records or even parse what is being specified in 
        # the other_url.
        self.change(url, names, [], manager_ips, [])

    def change(self, url, names, public_ips, manager_ips, private_ips):
        # If there are no public IPs to serve up for this endpoint,
        # then we provide instead the available manager IPs. 
        if len(public_ips) == 0:
            public_ips = manager_ips

        # Save the mappings.
        for name in names:
            self.ipmappings[name] = public_ips

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
        hosts = open(self.config.hosts_path(), 'wb')
        for (address, names) in ipmap.items():
            for name in set(names):
                hosts.write("%s %s\n" % (address, name))
        hosts.close()

        # Make sure we have a domain.
        domain = self._scale_manager.domain
        if not(domain):
            domain = "example.com"

        # Write out our configuration template.
        conf = self.template.render(domain=domain,
                                    hosts=self.config.hosts_path())

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
