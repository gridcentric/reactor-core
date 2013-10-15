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

import subprocess
import re
import collections
import socket

IpTableRule = collections.namedtuple(
    'IpTableRule', 'target, prot, opt, source, destination, filters')

def build_cmd(rule):
    cmd = []
    cmd.extend(["-j", rule.target])
    cmd.extend(["-s", rule.source])
    cmd.extend(["-d", rule.destination])
    cmd.extend(["-p", rule.prot])
    for filt in rule.filters:
        if filt in ["tcp", "udp", "icmp"]:
            continue
        if filt.startswith("dpt:"):
            cmd.extend(["--dport", filt.split(":")[1]])
        if filt.startswith("spt:"):
            cmd.extend(["--sport", filt.split(":")[1]])
        if filt.startswith("state:"):
            cmd.extend(["-m", "state", "--state", filt.split(":")[1]])
    return cmd

def add_rule(rule, table="INPUT"):
    cmd = ["iptables", "-A", table]
    cmd.extend(build_cmd(rule))
    subprocess.check_call(cmd)

def remove_rule(rule, table="INPUT"):
    cmd = ["iptables", "-D", table]
    cmd.extend(build_cmd(rule))
    subprocess.check_call(cmd)

def list_rules(table="INPUT"):
    p = subprocess.Popen(["iptables", "-L", table, "-n"], stdout=subprocess.PIPE)
    (stdout, _) = p.communicate()
    if p.returncode != 0:
        raise Exception("Error executing iptables.")

    found = []

    # Skip two lines of the header.
    rules = stdout.split("\n")[2:]
    for rule in rules:
        m = re.match("([^ ]+)\s+([^ ]+)\s+([^ ]+)\s+([^ ]+)\s+([^ ]+)\s+(.+)", rule)
        if m:
            target = m.group(1)
            prot = m.group(2)
            opt = m.group(3)
            source = m.group(4)
            destination = m.group(5)
            filters = m.group(6).split()

            # Fixup the state filter.
            if "state" in filters:
                stateidx = filters.index("state")
                state_val = "state:%s" % filters[stateidx+1]
                filters.remove("state")
                filters[stateidx] = state_val

            found.append(IpTableRule(target, prot, opt, source, destination, filters))

    return found

def modify_host(source="0.0.0.0/0", destination="0.0.0.0/0", action="ACCEPT", prot="tcp", port=0):
    if source.find("/") < 0:
        source = "%s/32" % source
    if destination.find("/") < 0:
        destination = "%s/32" % destination
    rule = IpTableRule(action, prot, "--", source, destination, [])
    if port:
        rule.filters.append("dpt:%d" % port)
    add_rule(rule)

ZOOKEEPER_LOCAL = "127.0.0.0/8"
ZOOKEEPER_PORTS = [2181, 2888, 3888]
ESTABLISHED_RULE = IpTableRule(
    "ACCEPT",
    "tcp",
    "--",
    "0.0.0.0/0",
    "0.0.0.0/0",
    ["state:RELATED,ESTABLISHED"]
)

def zookeeper_clear():
    rules = list_rules()
    ports = ZOOKEEPER_PORTS[:]
    for rule in rules:
        for port in ports:
            if "dpt:%d" % port in rule.filters:
                remove_rule(rule)
                break

def zookeeper_allow(host):
    if not ESTABLISHED_RULE in list_rules():
        add_rule(ESTABLISHED_RULE)
    ports = ZOOKEEPER_PORTS[:]
    for port in ports:
        for prot in ("tcp", "udp"):
            try:
                modify_host(
                    source=host,
                    action="ACCEPT",
                    prot=prot,
                    port=port)
            except socket.error:
                return

def zookeeper_reject():
    ports = ZOOKEEPER_PORTS[:]
    for port in ports:
        for prot in ("tcp", "udp"):
            modify_host(source="0.0.0.0/0", action="DROP", prot=prot, port=port)

def setup(hosts=None):
    if hosts is None:
        hosts = []
    zookeeper_clear()
    zookeeper_allow(ZOOKEEPER_LOCAL)
    addresses = [ZOOKEEPER_LOCAL]
    for host in hosts:
        try:
            address = socket.gethostbyname(host)
        except socket.error:
            continue
        if not(address in addresses):
            zookeeper_allow(address)
            addresses.append(address)
    zookeeper_reject()
