import re
import subprocess
import os

import reactor.ips as ips

ZOOKEEPER_CONF_DIRS = [
    "/etc/zookeeper/conf",
    "/etc/zookeeper",
]
for path in ZOOKEEPER_CONF_DIRS:
    if os.path.exists(path) and os.path.isdir(path):
        ZOOKEEPER_CONF_DIR = path
        break

ZOOKEEPER_RUN_DIRS = [
    "/var/run/zookeeper",
    "/var/run"
]
for path in ZOOKEEPER_RUN_DIRS:
    if os.path.exists(path) and os.path.isdir(path):
        ZOOKEEPER_RUN_DIR = path
        break

ZOOKEEPER_ID_FILE = os.path.join(ZOOKEEPER_CONF_DIR, "myid")
ZOOKEEPER_CONFIG_FILE = os.path.join(ZOOKEEPER_CONF_DIR, "zoo.cfg")
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
ZOOKEEPER_PID_FILE = os.path.join(ZOOKEEPER_RUN_DIR, "zookeeper.pid")

def generate_config(myid, servers):
    # Write out the ID file.
    f = open(ZOOKEEPER_ID_FILE, 'w')
    f.write(str(myid).strip() + "\n")
    f.close()

    # Write out the server file.
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

def compute_id(servers):
    try:
        return map(ips.is_local, servers).index(True) + 1
    except ValueError:
        return 0

def check_config(new_servers):
    old_servers = read_config()
    old_servers.sort()
    old_id = compute_id(old_servers)

    new_servers.sort()
    new_id = compute_id(new_servers)

    if new_servers != old_servers or old_id != new_id:
        generate_config(new_id, new_servers)
        if is_running():
            ensure_stopped()
            ensure_started()
