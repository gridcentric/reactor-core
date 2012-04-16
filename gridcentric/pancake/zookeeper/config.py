#!/usr/bin/env python

import re
import subprocess
import os

ZOOKEEPER_CONFIG_FILE = "/etc/zookeeper/conf/zoo.cfg"
ZOOKEEPER_CONFIG_DATA = \
"""# This file has been automatically generated, do not edit.
tickTime=2000
initLimit=10
syncLimit=5
dataDir=/var/lib/zookeeper
clientPort=2181
preAllocSize=65536
snapCount=1000
leaderServes=yes
"""
ZOOKEEPER_DATA_PORT = 2888
ZOOKEEPER_ELECTION_PORT = 3888
ZOOKEEPER_PID_FILE = "/var/run/zookeeper/zookeeper.pid"

def generate_config(servers):
    f = open(ZOOKEEPER_CONFIG_FILE, 'w')
    f.write(ZOOKEEPER_CONFIG_DATA)
    for i in range(len(servers)):
        # server.N=hostN:2888:3888
        f.write("server.%d=%s:%d:%d\n" % \
            (i+1, servers[i], ZOOKEEPER_DATA_PORT, ZOOKEEPER_ELECTION_PORT))
    f.close()

def read_config():
    servers = []
    f = open(ZOOKEEPER_CONFIG_FILE, 'r')
    for line in f.readlines():
        # server.N=hostN:2888:3888
        m = re.match("server\.\d+=(\S+):%d:%d" % \
            (ZOOKEEPER_DATA_PORT, ZOOKEEPER_ELECTION_PORT), line)
        if m:
            servers.append(m.group(1))
    return servers

def is_running():
    if os.path.exists(ZOOKEEPER_PID_FILE):
        f = open(ZOOKEEPER_PID_FILE, 'r')
        pid = int(f.readline().strip())
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    else:
        return False

def ensure_stopped():
    if is_running():
        subprocess.call(["/etc/init.d/zookeeper", "stop"])

def ensure_started():
    if not(is_running()):
        subprocess.call(["/etc/init.d/zookeeper", "start"])

def check_config(new_servers):
    new_servers.sort()
    old_servers = read_config()
    old_servers.sort()
    if new_servers != old_servers:
        generate_config(new_servers)
        if is_running():
            ensure_stopped()
            ensure_started()

if __name__ == "__main__":
    check_config(["127.0.0.1"])
