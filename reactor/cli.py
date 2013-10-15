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
import signal
import sys
import traceback
import json
import gc
import atexit

from . import log
from . zookeeper import config as zk_config

# Resolve internal threading bug, that spams log output.
# For more information see --
# http://stackoverflow.com/questions/13193278/understand-python-threading-bug
import threading
threading._DummyThread._Thread__stop = lambda x: 42

# For debugging stop race conditions.
def find_objects(t):
    return filter(lambda o: isinstance(o, t), gc.get_objects())
def print_threads():
    for i, stack in sys._current_frames().items():
        sys.stderr.write("thread %s\n" % str(i))
        traceback.print_stack(stack)

def sig_usr2_handler(signum, frame):
    print_threads()

signal.signal(signal.SIGUSR2, sig_usr2_handler)

def usage():
    print "usage: %s < --help | [options] command >" % sys.argv[0]
    print ""
    print "Optional arguments:"
    print "   --help                  Display this help message."
    print ""
    print "   --api=                  The API url (default is localhost)."
    print ""
    print "   --password=             The password used to connect to the API."
    print ""
    print "   --zookeeper=            The host:port of a zookeeper instance. Use this option"
    print "                           multiple times to specific multiple instances. Only"
    print "                           necessary for run commands. The default is localhost."
    print ""
    print "   --debug                 Enables debugging log and full stack trace errors."
    print ""
    print "   --log=                  Log to a file instead of stdout."
    print ""
    print "   --pidfile=              Write the current pid to the given file."
    print ""
    print "   --gui                   Enable the GUI extension."
    print ""
    print "   --cluster               Enable the cluster extension."
    print ""
    print "Commands:"
    print "    version                Get the server API version."
    print ""
    print "    url                    Get the server API url."
    print ""
    print "    list                   List all the endpoints currently being managed."
    print ""
    print "    manage <endpoint>      Manage or update a serivce with the given name."
    print "                           The endpoint configuration is read from stdin."
    print "    unmanage <endpoint>    Unmanged the endpoint with the given name."
    print "    show <endpoint>        Show the current configuration for the endpoint."
    print ""
    print "    register <ip>          Register the given IP address."
    print "    drop <ip>              Remove the given IP address."
    print "    ips <endpoint>         Displays all of the confirmed IP addresses."
    print ""
    print "    state <endpoint>       Get the endpoint state."
    print "    start <endpoint>       "
    print "    stop  <endpoint>       Update the endpoint state."
    print "    pause <endpoint>       "
    print ""
    print "    get-metrics <endpoint> Get custom endpoint metrics."
    print "    set-metrics <endpoint> Set custom endpoint metrics. The metrics are read"
    print "                           as JSON { \"name\" : [weight, value] } from stdin."
    print ""
    print "    sessions <endpoint>        List all the sessions."
    print "    kill <endpoint> <session>  Kill the given session."
    print ""
    print "    managers               List all the configured managers."
    print "    managers-active        List all the active managers."
    print ""
    print "    manager-update <ip>    Set the configuration for the given manager."
    print "    manager-show <ip>      Show the current configuration for the manager."
    print "    manager-forget <ip>    Remove and forget the given manager."
    print ""
    print "    passwd [password]      Updates the API's password."
    print ""
    print "    runserver [names...]   Run the scale manager server."
    print "    runapi                 Runs the API server."
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

def main():
    api_server = "http://localhost:8080"
    zk_servers = []
    password = None
    debug = False
    logfile = None
    pidfile = None
    gui = False
    cluster = False

    opts, args = getopt.getopt(sys.argv[1:], "",
        [
            "help",
            "api=",
            "password=",
            "zookeeper=",
            "debug",
            "gui",
            "pidfile=",
            "log=",
            "cluster",
        ])

    for o, a in opts:
        if o in ('--help',):
            usage()
            sys.exit(0)
        elif o in ('--api',):
            api_server = a
        elif o in ('--password',):
            password = a
        elif o in ('--zookeeper',):
            zk_servers.append(a)
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

    if len(zk_servers) == 0:
        try:
            # Try to read the saved configuration.
            zk_servers = zk_config.read_config()
        except Exception:
            zk_servers = []

    if len(zk_servers) == 0:
        # Otherwise, use localhost.
        zk_servers = ["localhost"]

    loglevel = logging.INFO
    if debug:
        loglevel = logging.DEBUG
    log.configure(loglevel, None)

    def get_arg(n):
        if len(args) < n+1:
            usage()
            sys.exit(1)
        return args[n]
    def get_args():
        return args[1:]
    def ready():
        log.configure(loglevel, logfile)
        if pidfile:
            daemonize(pidfile)

    command = get_arg(0)

    def get_api_client():
        from reactor.apiclient import ReactorApiClient
        return ReactorApiClient(api_server, password)

    def get_api():
        from reactor.api import ReactorApi
        api = ReactorApi(zk_servers)
        if gui:
            from . gui import ReactorGui
            api = ReactorGui(api)
        if cluster:
            from . cluster import Cluster
            api = Cluster(api)
        return api

    try:
        if command == "version":
            api_client = get_api_client()
            print api_client.version()

        elif command == "url":
            api_client = get_api_client()
            if len(args) > 1:
                new_url = get_arg(1)
                api_client.url_set(new_url)
            else:
                print api_client.url()

        elif command == "list":
            api_client = get_api_client()
            endpoints = api_client.endpoint_list()
            if endpoints:
                for endpoint in endpoints:
                    print endpoint

        elif command == "manage":
            endpoint_name = get_arg(1)
            new_conf = ""
            for line in sys.stdin.readlines():
                new_conf += line

            api_client = get_api_client()
            api_client.endpoint_manage(endpoint_name, new_conf)

        elif command == "unmanage":
            endpoint_name = get_arg(1)
            api_client = get_api_client()
            api_client.endpoint_unmanage(endpoint_name)

        elif command == "show":
            endpoint_name = get_arg(1)
            api_client = get_api_client()
            config = api_client.endpoint_config(endpoint_name)
            print json.dumps(config, indent=2)

        elif command == "managers":
            api_client = get_api_client()
            managers = api_client.manager_list()
            for manager in managers:
                print manager

        elif command == "managers-active":
            api_client = get_api_client()
            managers = api_client.manager_list(active=True)
            for (ip, key) in managers.items():
                print ip, key

        elif command == "manager-update":
            manager = get_arg(1)
            new_conf = ""
            for line in sys.stdin.readlines():
                new_conf += line

            api_client = get_api_client()
            api_client.manager_update(manager, new_conf)

        elif command == "manager-show":
            manager = get_arg(1)
            api_client = get_api_client()
            config = api_client.manager_config(manager)
            print json.dumps(config, indent=2)

        elif command == "manager-forget":
            manager = get_arg(1)
            api_client = get_api_client()
            api_client.manager_reset(manager)

        elif command == "ips":
            endpoint_name = get_arg(1)
            api_client = get_api_client()
            ip_addresses = api_client.endpoint_ip_addresses(endpoint_name)
            for ip in ip_addresses:
                print ip

        elif command == "register":
            ip = get_arg(1)
            api_client = get_api_client()
            api_client.register_ip(ip)

        elif command == "drop":
            ip = get_arg(1)
            api_client = get_api_client()
            api_client.drop_ip(ip)

        elif command == "state":
            api_client = get_api_client()
            endpoint_name = get_arg(1)
            state = api_client.endpoint_state(endpoint_name)
            print json.dumps(state, indent=2)

        elif command == "start" or command == "stop" or command == "pause":
            api_client = get_api_client()
            endpoint_name = get_arg(1)
            api_client.endpoint_action(endpoint_name, command)

        elif command == "get-metrics":
            endpoint_name = get_arg(1)
            api_client = get_api_client()
            metrics = api_client.endpoint_metrics(endpoint_name)
            print metrics

        elif command == "set-metrics":
            new_metrics = ""
            for line in sys.stdin.readlines():
                new_metrics += line

            endpoint_name = get_arg(1)
            api_client = get_api_client()
            api_client.endpoint_metrics_set(endpoint_name, json.loads(new_metrics))

        elif command == "log":
            endpoint_name = get_arg(1)
            api_client = get_api_client()
            entries = api_client.endpoint_log(endpoint_name)
            for (ts, level, message) in entries:
                print ts, level, message

        elif command == "sessions":
            endpoint_name = get_arg(1)
            api_client = get_api_client()
            sessions = api_client.session_list(endpoint_name)
            for client, backend in sessions.items():
                print client, backend

        elif command == "kill":
            endpoint_name = get_arg(1)
            session = get_arg(2)
            api_client = get_api_client()
            api_client.session_kill(endpoint_name, session)

        elif command == "passwd":
            if len(args) > 1:
                new_password = get_arg(1)
            else:
                new_password = None

            api_client = get_api_client()
            api_client.api_key_set(new_password)

        elif command == "runserver":

            from . manager import ScaleManager
            manager = ScaleManager(zk_servers, get_args())
            ready()
            manager.run()

        elif command == "runapi":

            api = get_api()
            app = api.get_wsgi_app()

            from paste.httpserver import serve
            logging.info("Preparing API...")
            ready()
            serve(app, host='0.0.0.0')

        else:
            usage()
            sys.exit(1)

    except Exception, e:
        if debug:
            traceback.print_exc()
        else:
            sys.stderr.write("%s\n" %(e))
            sys.exit(1)
