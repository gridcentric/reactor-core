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
import getopt
import logging
import sys
import traceback
import json
import getpass
import atexit
import time

# Resolve internal threading bug, that spams log output.
# For more information see --
# http://stackoverflow.com/questions/13193278/understand-python-threading-bug
import threading
threading._DummyThread._Thread__stop = lambda x: 42

# Our default API server.
DEFAULT_API = "localhost"

# Our default port.
DEFAULT_PORT = 8080

# Log message formats.
LOG_FORMATS = {
    "ERROR": "%s \033[91m%s\033[0m %s",
    "WARNING": "%s \033[93m%s\033[0m %s",
    "INFO": "%s \033[94m%s\033[0m %s",
}
def log_format(severity):
    return LOG_FORMATS.get(severity, "%s %s %s")

def usage(is_server=False):
    print "Usage: %s [options] <command>" % sys.argv[0]
    print "Options:"
    print ""
    print "   --help                  Display this help message."
    print ""
    if is_server:
        print "   --zookeeper=            The host:port of a zookeeper instance. Use this"
        print "                           option multiple times to specify multiple servers."
        print "                           (Alternately, this ZooKeeper servers can be provided"
        print "                            in the environment variable REACTOR_ZK_SERVERS)."
        print ""
        print "   --log=                  Log to a file instead of stdout."
        print ""
        print "   --pidfile=              Daemonize and write the pid to the given file."
        print ""
        print "   --gui                   Enable the GUI extension (for runapi)."
        print ""
        print "   --cluster               Enable the cluster extension (for runapi)."
        print ""
    else:
        print "   --api=                  The API URL (default is %s)." % DEFAULT_API
        print "                           (Alternately, this API server can be provided"
        print "                            in the environment variable REACTOR_API)."
        print ""
        print "   --password=             Specify a password to connect to the API."
        print "   --askpass               Prompt for the password."
        print "                           (Alternately, the API password can be provided"
        print "                            in the environment variable REACTOR_PASSWORD)."
        print ""
    print "   --port=                 The port for the API server (default is %d)." % DEFAULT_PORT
    print "                           (Alternately, the API port can be provided"
    print "                            in the environment variable REACTOR_PORT)."
    print ""
    print "   --debug                 Enables verbose logging and full stack errors."
    print ""
    if is_server:
        print "Server commands:"
        print ""
        print "    zk_servers             Print and update ZooKeeper servers."
        print ""
        print "    zk_dump                Dump all zookeeper contents."
        print ""
        print "    runserver [names...]   Run the scale manager server."
        print "    runapi                 Runs the API server."
        print ""
    else:
        print "Global commands:"
        print ""
        print "    version                Get the server API version."
        print ""
        print "    url [<URL>]            Get or set the server API URL."
        print ""
        print "    passwd [password]      Set or clear the API password."
        print ""
        print "Manager commands:"
        print ""
        print "    managers               List all the configured managers."
        print "    managers-active        List all the active managers."
        print ""
        print "    manager-update <ip>    Set the configuration for the given manager."
        print "    manager-show <ip>      Show the current configuration for the manager."
        print "    manager-forget <ip>    Remove and forget the given manager."
        print ""
        print "Endpoint commands:"
        print ""
        print "    list                   List all managed endpoints."
        print ""
        print "    manage [endpoint]      Create or update the given endpoint."
        print "                           (The endpoint configuration is read from stdin.)"
        print "    unmanage [endpoint]    Delete the endpoint with the given name."
        print "    show [endpoint]        Show the current configuration for the endpoint."
        print ""
        print "    rename [endpoint] <new-name>  Rename the givern endpoint."
        print "    alias [endpoint] <new-name>   Alias the given endpoint."
        print "                                  The endpoints will share all state."
        print ""
        print "    get [endpoint] <section> <key>"
        print "    set [endpoint] <section> <key> <value>"
        print ""
        print "    register [ip]          Register the given IP address."
        print "    drop [ip]              Remove the given IP address."
        print "    ips [endpoint]         Displays confirmed IP addresses."
        print ""
        print "    associate [endpoint] <instance>    Associate the given instance."
        print "    disassociate [endpoint] <instance> Disassociate the instance."
        print "    instances [endpoint]               Show all current instances."
        print ""
        print "    state [endpoint]       Get the endpoint state."
        print ""
        print "    start [endpoint]       "
        print "    stop [endpoint]        Update the endpoint state."
        print "    pause [endpoint]       "
        print ""
        print "    get-metrics [endpoint] Get custom endpoint metrics."
        print "    set-metrics [endpoint] Set custom endpoint metrics."
        print "                           (The metrics are read as JSON from stdin.)"
        print "                               {\"name\": [weight, value], ...}"
        print ""
        print "    log [endpoint]         Show the endpoint log."
        print "    watch [endpoint]       Watch the endpoint log."
        print "    post [endpoint]        Post to the endpoint log."
        print ""
        print "    sessions [endpoint]        List all managed sessions."
        print "    kill [endpoint] <session>  Kill the given session."
        print ""

def daemonize(pidfile):
    # Perform a double fork().
    # This will allow us to integrate cleanly
    # with startup workflows (i.e. the daemon
    # function on RedHat / CentOS).
    pid = os.fork()
    if pid > 0:
        sys.exit(0)

    # Move to the root.
    os.chdir("/")
    os.setsid()
    os.umask(0)

    pid = os.fork()
    if pid > 0:
        sys.exit(0)

    # Close standard file descriptors.
    sys.stdout.flush()
    sys.stderr.flush()
    null = "/dev/null"
    si = file(null, 'r')
    so = file(null, 'a+')
    se = file(null, 'a+', 0)
    os.dup2(si.fileno(), sys.stdin.fileno())
    os.dup2(so.fileno(), sys.stdout.fileno())
    os.dup2(se.fileno(), sys.stderr.fileno())

    try:
        maxfd = os.sysconf("SC_OPEN_MAX")
    except (AttributeError, ValueError):
        maxfd = 1024
    for fd in range(3, maxfd):
        try:
            os.close(fd)
        except OSError:
            pass

    # Write out the pidfile.
    def rmpidfile():
        os.remove(pidfile)
    atexit.register(rmpidfile)
    pid = str(os.getpid())
    f = open(pidfile,'w+')
    f.write("%s\n" % pid)
    f.close()

def main(is_server):
    port = os.getenv("REACTOR_PORT") or DEFAULT_PORT
    api_server = os.getenv("REACTOR_API") or DEFAULT_API
    if "REACTOR_ZK_SERVERS" in os.environ:
        zk_servers = os.environ["REACTOR_ZK_SERVERS"].split(",")
    else:
        zk_servers = []
    password = os.getenv("REACTOR_PASSWORD")
    debug = False
    logfile = None
    pidfile = None
    gui = False
    cluster = False
    do_help = False

    available_opts = [
        "help",
        "api=",
        "askpass",
        "password=",
        "port=",
        "debug",
        # NOTE: These are server-only options.
        # They are parsed at the same time but
        # will not generally be shown in the help
        # unless the --server option is passed.
        "zookeeper=",
        "gui",
        "pidfile=",
        "log=",
        "cluster",
    ]

    opts, args = getopt.getopt(sys.argv[1:], "", available_opts)
    for o, a in opts:
        if o in ('--help',):
            do_help = True
        elif o in ('--api',):
            api_server = a
        elif o in ('--askpass',):
            password = getpass.getpass()
        elif o in ('--password',):
            password = a
        elif o in ('--zookeeper',):
            zk_servers.append(a)
        elif o in ('--port',):
            port = int(a)
        elif o in ('--debug',):
            debug = True
        elif o in ('--log',):
            logfile = a
        elif o in ('--pidfile',):
            pidfile = a
        elif o in ('--gui',):
            gui = True
        elif o in ('--cluster',):
            cluster = True

    if do_help:
        usage(is_server)
        sys.exit(0)

    loglevel = logging.INFO
    if debug:
        loglevel = logging.DEBUG

    # Disable all logging for now.
    # We want start-up errors to go to the console. The first thing the server
    # does prior to starting up is call server_ready() below which will enable
    # the logfile, etc.
    from . import log
    log.configure(loglevel, None)

    def get_arg(n):
        if len(args) < n+1:
            usage(is_server)
            sys.exit(1)
        return args[n]

    def get_args():
        return args[1:]

    def server_ready():
        log.configure(loglevel, logfile)
        if pidfile:
            daemonize(pidfile)

    if len(zk_servers) == 0:
        try:
            # Try to read the saved configuration.
            from . zookeeper import config as zk_config
            zk_servers = zk_config.read_config()
        except Exception:
            zk_servers = []

    if len(zk_servers) == 0:
        # Otherwise, use the default.
        from . import ips as ips_mod
        zk_servers = [ips_mod.find_default()]

    # Fixup the API server.
    if not 'http:' in api_server and \
       not 'https:' in api_server:
        api_server = "http://%s" % (api_server)
    if len(api_server.split(":")) < 3:
        api_server = "%s:%d" % (api_server, port)

    def get_api_client():
        # Grab the client.
        from reactor.apiclient import ReactorApiClient
        return ReactorApiClient(api_server, password)

    command = get_arg(0)

    try:
        if not is_server and command == "version":
            api_client = get_api_client()
            print api_client.version()

        elif not is_server and command == "url":
            api_client = get_api_client()
            if len(args) > 1:
                new_url = get_arg(1)
                api_client.url_set(new_url)
            else:
                print api_client.url()

        elif not is_server and command == "list":
            api_client = get_api_client()
            endpoints = api_client.endpoint_list()
            for endpoint in endpoints:
                print endpoint

        elif is_server and command == "zk_servers":
            from . zookeeper import config as zk_config
            zk_config.check_config(zk_servers)
            for server in zk_servers:
                print server

        elif is_server and command == "zk_dump":
            from . zookeeper.client import ZookeeperClient
            from . objects.root import Reactor

            client = ZookeeperClient(zk_servers)
            root = Reactor(client)
            root.dump()

        elif not is_server and command == "manage":
            if len(args) > 1:
                endpoint_name = get_arg(1)
            else:
                endpoint_name = None

            new_conf = ""
            for line in sys.stdin.readlines():
                new_conf += line

            api_client = get_api_client()
            api_client.endpoint_manage(
                endpoint_name=endpoint_name,
                config=new_conf)

        elif not is_server and command == "unmanage":
            if len(args) > 1:
                endpoint_name = get_arg(1)
            else:
                endpoint_name = None

            api_client = get_api_client()
            api_client.endpoint_unmanage(endpoint_name=endpoint_name)

        elif not is_server and command == "show":
            if len(args) > 1:
                endpoint_name = get_arg(1)
            else:
                endpoint_name = None

            api_client = get_api_client()
            config = api_client.endpoint_config(endpoint_name=endpoint_name)
            print json.dumps(config, indent=2)

        elif not is_server and command == "rename":
            if len(args) > 2:
                endpoint_name = get_arg(1)
                new_name = get_arg(2)
            else:
                endpoint_name = None
                new_name = get_arg(1)

            api_client = get_api_client()
            api_client.endpoint_alias(
                endpoint_name=endpoint_name,
                new_name=new_name)
            api_client.endpoint_unmanage(endpoint_name=endpoint_name)

        elif not is_server and command == "alias":
            if len(args) > 2:
                endpoint_name = get_arg(1)
                new_name = get_arg(2)
            else:
                endpoint_name = None
                new_name = get_arg(1)

            api_client = get_api_client()
            api_client.endpoint_alias(
                endpoint_name=endpoint_name,
                new_name=new_name)

        elif not is_server and command == "get":
            if len(args) > 3:
                endpoint_name = get_arg(1)
                section = get_arg(2)
                key = get_arg(3)
            else:
                endpoint_name = None
                section = get_arg(1)
                key = get_arg(2)

            api_client = get_api_client()
            config = api_client.endpoint_config(endpoint_name=endpoint_name)
            section_config = config.get(section, {})
            if section_config.has_key(key):
                print section_config[key]

        elif not is_server and command == "set":
            if len(args) > 4:
                endpoint_name = get_arg(1)
                section = get_arg(2)
                key = get_arg(3)
                value = get_arg(4)
            else:
                endpoint_name = None
                section = get_arg(1)
                key = get_arg(2)
                value = get_arg(3)

            api_client = get_api_client()
            config = api_client.endpoint_config(endpoint_name=endpoint_name)
            if not section in config:
                config[section] = {}
            config[section][key] = value
            api_client.endpoint_manage(
                endpoint_name=endpoint_name,
                config=config)

        elif not is_server and command == "managers":
            api_client = get_api_client()
            managers = api_client.manager_list()
            for manager in managers:
                print manager

        elif not is_server and command == "managers-active":
            api_client = get_api_client()
            managers = api_client.manager_list(active=True)
            for (ip, key) in managers.items():
                print ip, key

        elif not is_server and command == "manager-update":
            manager = get_arg(1)

            new_conf = ""
            for line in sys.stdin.readlines():
                new_conf += line

            api_client = get_api_client()
            api_client.manager_update(manager, new_conf)

        elif not is_server and command == "manager-show":
            manager = get_arg(1)
            api_client = get_api_client()
            config = api_client.manager_config(manager)
            print json.dumps(config, indent=2)

        elif not is_server and command == "manager-forget":
            manager = get_arg(1)
            api_client = get_api_client()
            api_client.manager_forget(manager)

        elif not is_server and command == "ips":
            if len(args) > 1:
                endpoint_name = get_arg(1)
            else:
                endpoint_name = None

            api_client = get_api_client()
            ips = api_client.endpoint_ips(endpoint_name=endpoint_name)
            for ip in ips:
                print ip

        elif not is_server and command == "register":
            if len(args) > 1:
                ip = get_arg(1)
            else:
                ip = None

            api_client = get_api_client()
            api_client.register_ip(ip)

        elif not is_server and command == "drop":
            if len(args) > 1:
                ip = get_arg(1)
            else:
                ip = None

            api_client = get_api_client()
            api_client.drop_ip(ip)

        elif not is_server and command == "associate":
            if len(args) > 2:
                endpoint_name = get_arg(1)
                instance_id = get_arg(2)
            else:
                endpoint_name = None
                instance_id = get_arg(1)

            api_client = get_api_client()
            api_client.associate(
                endpoint_name=endpoint_name,
                instance_id=instance_id)

        elif not is_server and command == "disassociate":
            if len(args) > 2:
                endpoint_name = get_arg(1)
                instance_id = get_arg(2)
            else:
                endpoint_name = None
                instance_id = get_arg(1)

            api_client = get_api_client()
            api_client.disassociate(
                endpoint_name=endpoint_name,
                instance_id=instance_id)

        elif not is_server and command == "instances":
            if len(args) > 1:
                endpoint_name = get_arg(1)
            else:
                endpoint_name = None

            api_client = get_api_client()
            instances = api_client.instances(endpoint_name=endpoint_name)
            for (state, instance_list) in instances.items():
                for instance_id in instance_list:
                    print instance_id, state

        elif not is_server and command == "state":
            if len(args) > 1:
                endpoint_name = get_arg(1)
            else:
                endpoint_name = None

            api_client = get_api_client()
            state = api_client.endpoint_state(endpoint_name=endpoint_name)
            print json.dumps(state, indent=2)

        elif not is_server and \
            (command == "start" or command == "stop" or command == "pause"):
            if len(args) > 1:
                endpoint_name = get_arg(1)
            else:
                endpoint_name = None

            api_client = get_api_client()
            api_client.endpoint_action(
                endpoint_name=endpoint_name,
                action=command)

        elif not is_server and command == "get-metrics":
            if len(args) > 1:
                endpoint_name = get_arg(1)
            else:
                endpoint_name = None

            api_client = get_api_client()
            metrics = api_client.endpoint_metrics(
                endpoint_name=endpoint_name)
            print metrics

        elif not is_server and command == "set-metrics":
            if len(args) > 1:
                endpoint_name = get_arg(1)
            else:
                endpoint_name = None

            new_metrics = ""
            for line in sys.stdin.readlines():
                new_metrics += line

            api_client = get_api_client()
            api_client.endpoint_metrics_set(
                endpoint_name=endpoint_name,
                metrics=json.loads(new_metrics))

        elif not is_server and command == "log":
            if len(args) > 1:
                endpoint_name = get_arg(1)
            else:
                endpoint_name = None

            api_client = get_api_client()
            entries = api_client.endpoint_log(endpoint_name=endpoint_name)
            for (ts, level, message) in entries:
                print log_format(level) % (ts, level, message)

        elif not is_server and command == "watch":
            if len(args) > 1:
                endpoint_name = get_arg(1)
            else:
                endpoint_name = None

            api_client = get_api_client()
            delay = 2.0
            last_ts = 0.0
            while True:
                entries = api_client.endpoint_log(
                    endpoint_name=endpoint_name,
                    since=last_ts)
                for (ts, level, message) in entries:
                    print log_format(level) % (ts, level, message)
                    last_ts = ts
                time.sleep(delay)

        elif not is_server and command == "post":
            if len(args) > 1:
                endpoint_name = get_arg(1)
            else:
                endpoint_name = None

            message = ""
            for line in sys.stdin.readlines():
                message += line

            api_client = get_api_client()
            api_client.endpoint_post(
                endpoint_name=endpoint_name,
                message=message.strip())

        elif not is_server and command == "sessions":
            if len(args) > 1:
                endpoint_name = get_arg(1)
            else:
                endpoint_name = None

            api_client = get_api_client()
            sessions = api_client.session_list(endpoint_name=endpoint_name)
            for client, backend in sessions.items():
                print client, backend

        elif not is_server and command == "kill":
            if len(args) > 2:
                endpoint_name = get_arg(1)
                session = get_arg(2)
            else:
                endpoint_name = None
                session = get_arg(1)

            api_client = get_api_client()
            api_client.session_kill(
                endpoint_name=endpoint_name,
                session=session)

        elif not is_server and command == "passwd":
            if len(args) > 1:
                new_password = get_arg(1)
            else:
                new_password = None

            api_client = get_api_client()
            api_client.api_key_set(new_password)

        elif is_server and command == "runserver":

            from . manager import ScaleManager
            manager = ScaleManager(zk_servers, get_args())
            server_ready()
            try:
                manager.run()
            finally:
                manager.stop()

        elif is_server and command == "runapi":

            from reactor.api import ReactorApi
            api = ReactorApi(zk_servers)
            if cluster:
                from . cluster import ClusterMixin
                api.extend(ClusterMixin)
            if gui:
                from . gui import GuiMixin
                api.extend(GuiMixin)
            server_ready()
            try:
                api.run(host='0.0.0.0', port=DEFAULT_PORT)
            finally:
                api.stop()

        else:
            usage(is_server)
            sys.exit(1)

    except Exception, e:
        if debug:
            traceback.print_exc()
        else:
            sys.stderr.write("%s\n" %(e))
        sys.exit(1)
