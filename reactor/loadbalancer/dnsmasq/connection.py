# Copyright 2013 GridCentric Inc.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import os
import signal
import subprocess

from mako.template import Template

from reactor.config import Config
from reactor.loadbalancer.connection import LoadBalancerConnection
from reactor.loadbalancer.utils import read_pid

class DnsmasqManagerConfig(Config):

    pid_file = Config.string(label="Pid file",
        default="/var/run/dnsmasq/dnsmasq.pid",
        description="The dnsmasq pid file.")

    config_path = Config.string(label="Configuration Path", default="/etc/dnsmasq.d", \
        description="The configuration directory to insert base configuration.")

    hosts_path = Config.string(label="Site Config Path", default="/etc/hosts.reactor", \
        description="The directory in which to generate site configurations.")

class Connection(LoadBalancerConnection):

    """ Dnsmasq """

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

    def change(self, url, backends, config=None):
        # Save the mappings.
        name = self.url_info(url)
        if len(backends) == 0:
            if name in self.ipmappings:
                del self.ipmappings[name]
        else:
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
        pid = read_pid(self._manager_config().pid_file)
        if pid:
            os.kill(pid, signal.SIGHUP)
        else:
            subprocess.call(
                ["service", "dnsmasq", "start"],
                close_fds=True)

    def drop_session(self, client, backend):
        raise NotImplementedError()
