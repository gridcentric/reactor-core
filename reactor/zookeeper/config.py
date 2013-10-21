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

import re
import subprocess
import os

import reactor.ips as ips

ZOOKEEPER_CONF_DIRS = [
    "/etc/zookeeper/conf",
    "/etc/zookeeper",
]
ZOOKEEPER_CONF_DIR = ZOOKEEPER_CONF_DIRS[1]
for path in ZOOKEEPER_CONF_DIRS:
    if os.path.exists(path) and os.path.isdir(path):
        ZOOKEEPER_CONF_DIR = path
        break

ZOOKEEPER_RUN_DIRS = [
    "/var/run/zookeeper",
    "/var/run"
]
ZOOKEEPER_RUN_DIR = ZOOKEEPER_RUN_DIRS[1]
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

ZOOKEEPER_DATA_DIR = "/var/lib/zookeeper/version-2"
ZOOKEEPER_LOG_DIR = "/var/lib/zookeeper/version-2"
ZOOKEEPER_BACKUP_COUNT = 3

def generate_config(myid, servers):
    try:
        os.makedirs(os.path.dirname(ZOOKEEPER_ID_FILE))
    except OSError:
        pass

    # Write out the ID file.
    f = open(ZOOKEEPER_ID_FILE, 'w')
    f.write(str(myid).strip() + "\n")
    f.close()

    try:
        os.makedirs(os.path.dirname(ZOOKEEPER_CONFIG_FILE))
    except OSError:
        pass

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
        # Unfortunately, different distros use different
        # return values for the service command. So we just
        # have to rely on the output informing us whether
        # or not Zookeeper is currently running.
        proc = subprocess.Popen(
            ["service", "zookeeper", "status"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (stdout, stderr) = proc.communicate()
        return "running" in stdout

def ensure_stopped():
    if is_running():
        subprocess.call(["/etc/init.d/zookeeper", "stop"])

def ensure_started():
    if not(is_running()):
        subprocess.call(["/etc/init.d/zookeeper", "start"])

def clean_logs():
    subprocess.call([
        "java", "-cp", "zookeeper.jar",
        "org.apache.zookeeper.server.PurgeTxnLog",
        ZOOKEEPER_DATA_DIR,
        ZOOKEEPER_LOG_DIR,
        "-n", str(ZOOKEEPER_BACKUP_COUNT)],
        cwd="/usr/share/java")

def compute_id(servers):
    try:
        return map(ips.is_local, servers).index(True) + 1
    except ValueError:
        return 0

def check_config(new_servers):
    try:
        old_servers = read_config()
    except IOError:
        old_servers = []
    old_servers.sort()
    old_id = compute_id(old_servers)

    new_servers.sort()
    new_id = compute_id(new_servers)

    if new_servers != old_servers or old_id != new_id:
        generate_config(new_id, new_servers)
        if is_running():
            ensure_stopped()
            ensure_started()
