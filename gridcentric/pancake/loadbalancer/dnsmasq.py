import os
import signal

from mako.template import Template

from gridcentric.pancake.loadbalancer.connection import LoadBalancerConnection
from gridcentric.pancake.loadbalancer.netstat import connection_count

class DnsmasqLoadBalancerConnection(LoadBalancerConnection):
    
    def __init__(self, config_path, hosts_path, scale_manager):
        self.config_path = config_path
        self.hosts_path = hosts_path
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

    def change(self, url, port, names, manager_ips, public_ips, private_ips):
        # If there are no public ips, we use the manager.
        if len(public_ips) == 0:
            public_ips = manager_ips

        # Save the mappings.
        for name in names:
            self.mappings[name] = public_ips

    def save(self):
        # Compute the address mapping.
        ipmap = {}
        for (name, ips) in self.mappings.items():
            for ip in ips:
                if not(ip in ipmap):
                    ipmap[ip] = []
                ipmap[ip].append(name)

        # Write out our hosts file.
        hosts = file(self.hosts_path, 'wb')
        for (address, names) in ipmap.items():
            hosts.write("%s %s\n" % (address, " ".join(set(names))))
        hosts.close()

        # Make sure we have a domain.
        domain = self.scale_manager.domain
        if not(domain):
            domain = "example.com"

        # Write out our configuration template.
        conf = self.template.render(domain=domain, hosts=self.hosts_path)

        # Write out the config file.
        config_file = file(os.path.join(self.config_path,"pancake.conf"), 'wb')
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
