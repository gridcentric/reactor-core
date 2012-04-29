"""
Simple parser to extract active connections via netstat.
"""

import subprocess

def connections():
    active = []

    netstat = subprocess.Popen(["netstat", "-tn"], stdout=subprocess.PIPE)
    (stdout, stderr) = netstat.communicate()

    lines = stdout.split("\n")

    if len(lines) < 2:
        return []

    lines = lines[2:]
    for line in lines:
        try:
            (proto, recvq, sendq, local, foreign, state) = line.split()
            active.append(foreign)
        except:
            pass

    return active

def connection_count():
    active_count = {}
    active = connections()

    for connection in active:
        try:
            (host, port) = connection.split(":")
            print host, port
            active_count[host] = active_count.get(host, 0) + 1
        except:
            pass

    return active_count
