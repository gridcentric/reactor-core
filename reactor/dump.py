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

from . import cli
from . import server
from . objects.root import Reactor
from . zookeeper.client import ZookeeperClient

HELP = ("""Usage: reactor-dump [options]

    Dump the current Zookeeper tree (for debugging).

""",)

def dump_main(options, args):
    zk_servers = options.get("zk_servers")
    client = ZookeeperClient(zk_servers)
    root = Reactor(client)
    root.dump()

def main():
    cli.main(dump_main, [server.ZK_SERVERS], HELP)

if __name__ == "__main__":
    main()
