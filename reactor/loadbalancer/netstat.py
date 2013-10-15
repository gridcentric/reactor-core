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

"""
Simple parser to extract active connections via netstat.
"""

import subprocess

def connections():
    active = []

    netstat = subprocess.Popen(["netstat", "-tn"], stdout=subprocess.PIPE)
    (stdout, _) = netstat.communicate()

    lines = stdout.split("\n")

    if len(lines) < 2:
        return []

    lines = lines[2:]
    for line in lines:
        try:
            # NOTE(amscanne): These variables are unused at the moment,
            # but good to know what the different components of the netstat
            # output are... just in case we want to enhance this function in
            # the future.
            #   (proto, recvq, sendq, local, foreign, state) = line.split()
            (_, _, _, _, foreign, _) = line.split()
            (host, port) = foreign.split(":")
            active.append((host, int(port)))
        except Exception:
            pass

    return active

def connection_count():
    active_count = {}
    active = connections()

    for (host, port) in active:
        try:
            active_count[(host, port)] = \
                active_count.get((host, port), 0) + 1
        except Exception:
            pass

    return active_count
