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
    (stdout, stderr) = p.communicate()
    if p.returncode != 0:
        raise Exception("Error executing iptables.")

    found = []

    # Skip two lines of the header.
    rules = stdout.split("\n")[2:]
    for rule in rules:
        m = re.match("([^ ]+)\s+([^ ]+)\s+([^ ]+)\s+([^ ]+)\s+([^ ]+)\s+(.+)", rule)
        if m:
            target      = m.group(1)
            prot        = m.group(2)
            opt         = m.group(3)
            source      = m.group(4)
            destination = m.group(5)
            filters     = m.group(6).split()

            found.append(IpTableRule(target, prot, opt, source, destination, filters))

    return found

def modify_host(source="0.0.0.0/0", destination="0.0.0.0/0", action="ACCEPT", prot="tcp", port=0):
    rule = IpTableRule(action, prot, "--", source, destination, [])
    if port:
        rule.filters.append("dpt:%d" % port)
    add_rule(rule)

ZOOKEEPER_LOCAL = "127.0.0.1"
ZOOKEEPER_PORTS = [2181, 2888, 3888]

def zookeeper_clear(extra_ports=[]):
    rules = list_rules()
    ports = ZOOKEEPER_PORTS[:]
    ports.extend(extra_ports)
    for rule in rules:
        for port in ports:
            if "dpt:%d" % port in rule.filters:
                remove_rule(rule)
                break

def zookeeper_allow(host, extra_ports=[]):
    ports = ZOOKEEPER_PORTS[:]
    ports.extend(extra_ports)
    for port in ports:
        for prot in ("tcp", "udp"):
            try:
                modify_host(source=("%s/32" % host), action="ACCEPT", prot=prot, port=port)
            except socket.error:
                return

def zookeeper_reject(extra_ports=[]):
    ports = ZOOKEEPER_PORTS[:]
    ports.extend(extra_ports)
    for port in ports:
        for prot in ("tcp", "udp"):
            modify_host(source="0.0.0.0/0", action="REJECT", prot=prot, port=port)

def setup(hosts=[], extra_ports=[]):
    zookeeper_clear(extra_ports=extra_ports)
    zookeeper_allow(ZOOKEEPER_LOCAL, extra_ports=extra_ports)
    addresses = []
    for host in hosts:
        address = socket.gethostbyname(host)
        if not(address in addresses):
            addresses.append(address)
    for address in addresses:
        zookeeper_allow(address, extra_ports=extra_ports)
    zookeeper_reject(extra_ports=extra_ports)
