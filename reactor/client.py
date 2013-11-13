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

import sys
import json
import getpass
import time

from . import cli
from . import defaults
from . apiclient import ReactorApiClient

HELP = ("""Usage: reactor [options] <command>

""", """
Global commands:

    version                Get the server API version.

    url [<URL>]            Get or set the server API URL.

    passwd [<password>]    Set or clear the API authentication key.

Manager commands:

    manager-configs        List all the configured managers.
    manager-active         List all the active managers.

    manager-log <name>     Show the given manager log.
    manager-watch <name>   Watch the given manager log.

    manager-update <name>  Set the configuration for the given manager.
    manager-info <uuid>    Show the running manager info.
    manager-show <name>    Show the given manager configuration.
    manager-remove <name>  Remove the manager configuration.

Endpoint commands:

    list                          List all managed endpoints.

    create [endpoint]             Create the named endpoint.
    update [endpoint]             Update the given endpoint.
                                  (The configuration is read from stdin.)

    remove [endpoint]             Remove the endpoint with the given name.
    show [endpoint]               Show the endpoint configuration.

    rename [endpoint] <new-name>  Rename the given endpoint.
    alias [endpoint] <new-name>   Alias the given endpoint.
                                  (Aliased endpoints share state.)

    get [endpoint] <section> <key>
    set [endpoint] <section> <key> <value>

    metadata-list [endpoint]               List all endpoint metadata.
    metadata-get [endpoint] <key>          Get the given key.
    metadata-set [endpoint] <key> <value>  Set the given key.
    metadata-delete [endpoint] <key>       Remove the given key.

    register [ip]                 Register the given IP address.
    drop [ip]                     Remove the given IP address.

    ips [endpoint]                     Displays confirmed IP addresses.
    associate [endpoint] <instance>    Associate the given instance.
    disassociate [endpoint] <instance> Disassociate the instance.
    instances [endpoint]               Show all current instances.

    state [endpoint]              Get the endpoint state.

    start [endpoint]
    stop [endpoint]               Update the endpoint state.
    pause [endpoint]

    get-metrics [endpoint]        Get custom endpoint metrics.
    set-metrics [endpoint]        Set custom endpoint metrics.
                                  (The metrics are read as JSON from stdin.)
                                   {\"name\": [weight, value], ...}

    log [endpoint]                Show the endpoint log.
    watch [endpoint]              Watch the endpoint log.
    post [endpoint]               Post to the endpoint log.

    sessions [endpoint]           List all managed sessions.
    kill [endpoint] <session>     Kill the given session.

""")

API = cli.OptionSpec(
    "api",
    "The API URL.",
    str,
    "%s://%s:%d" % (
        defaults.DEFAULT_PROTO,
        defaults.DEFAULT_HOST,
        defaults.DEFAULT_PORT)
)

PASSWORD = cli.OptionSpec(
    "password",
    "The API password.",
    lambda x: x,
    None
)

ASKPASS = cli.OptionSpec(
    "askpass",
    "Interactively prompt for the password.",
    None,
    None
)

WATCH_DELAY = cli.OptionSpec(
    "watch_delay",
    "The delay for the watch commands.",
    float,
    defaults.DEFAULT_WATCH_DELAY
)

# Log message formats.
LOG_FORMATS = {
    "ERROR": "%s \033[91m%s\033[0m %s",
    "WARNING": "%s \033[93m%s\033[0m %s",
    "INFO": "%s \033[94m%s\033[0m %s",
}
def log_format(severity):
    return LOG_FORMATS.get(severity, "%s %s %s")

def client_main(options, args):
    # Pull out our options.
    api_server = options.get("api")
    password = options.get("password")
    watch_delay = options.get("watch_delay")

    # Prompt if needed.
    if options.get("askpass"):
        password = getpass.getpass()

    # Grab the client.
    api_client = ReactorApiClient(api_server, password)

    # Prepare to parse our command.
    def get_arg(n):
        if len(args) <= n:
            raise cli.InvalidArguments()
        return args[n]
    command = get_arg(0)

    if command == "version":
        print api_client.version()

    elif command == "url":
        if len(args) > 1:
            new_url = get_arg(1)
            api_client.url_set(new_url)
        else:
            print api_client.url()

    elif command == "list":
        endpoints = api_client.endpoint_list()
        for endpoint in endpoints:
            print endpoint

    elif command == "create":
        endpoint_name = get_arg(1)
        new_conf = ""
        for line in sys.stdin.readlines():
            new_conf += line
        api_client.endpoint_create(
            endpoint_name=endpoint_name,
            config=new_conf)

    elif command == "update":
        if len(args) > 1:
            endpoint_name = get_arg(1)
        else:
            endpoint_name = None
        new_conf = ""
        for line in sys.stdin.readlines():
            new_conf += line
        api_client.endpoint_update(
            endpoint_name=endpoint_name,
            config=new_conf)

    elif command == "remove":
        if len(args) > 1:
            endpoint_name = get_arg(1)
        else:
            endpoint_name = None
        api_client.endpoint_remove(endpoint_name=endpoint_name)

    elif command == "show":
        if len(args) > 1:
            endpoint_name = get_arg(1)
        else:
            endpoint_name = None
        config = api_client.endpoint_config(endpoint_name=endpoint_name)
        print json.dumps(config, indent=2)

    elif command == "rename":
        if len(args) > 2:
            endpoint_name = get_arg(1)
            new_name = get_arg(2)
        else:
            endpoint_name = None
            new_name = get_arg(1)
        api_client.endpoint_alias(
            endpoint_name=endpoint_name,
            new_name=new_name)
        api_client.endpoint_remove(endpoint_name=endpoint_name)

    elif command == "alias":
        if len(args) > 2:
            endpoint_name = get_arg(1)
            new_name = get_arg(2)
        else:
            endpoint_name = None
            new_name = get_arg(1)
        api_client.endpoint_alias(
            endpoint_name=endpoint_name,
            new_name=new_name)

    elif command == "get":
        if len(args) > 3:
            endpoint_name = get_arg(1)
            section = get_arg(2)
            key = get_arg(3)
        else:
            endpoint_name = None
            section = get_arg(1)
            key = get_arg(2)
        config = api_client.endpoint_config(endpoint_name=endpoint_name)
        section_config = config.get(section, {})
        if section_config.has_key(key):
            print section_config[key]

    elif command == "set":
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
        config = api_client.endpoint_config(endpoint_name=endpoint_name)
        if not section in config:
            config[section] = {}
        config[section][key] = value
        api_client.endpoint_update(
            endpoint_name=endpoint_name,
            config=config)

    elif command == "metadata-list":
        if len(args) > 1:
            endpoint_name = get_arg(1)
        else:
            endpoint_name = None
        for key in api_client.metadata_list(endpoint_name=endpoint_name):
            print key

    elif command == "metadata-get":
        if len(args) > 2:
            endpoint_name = get_arg(1)
            key = get_arg(2)
        else:
            endpoint_name = None
            key = get_arg(1)
        value = api_client.metadata_get(
            endpoint_name=endpoint_name,
            key=key)
        # NOTE: Don't dump the result as json,
        # because we don't want it to be decorated.
        # We just want strings as raw strings so
        # as to be most useful to the user.
        print value

    elif command == "metadata-set":
        if len(args) > 3:
            endpoint_name = get_arg(1)
            key = get_arg(2)
            value = get_arg(3)
        else:
            endpoint_name = None
            key = get_arg(1)
            value = get_arg(2)
        api_client.metadata_set(
            endpoint_name=endpoint_name,
            key=key,
            value=value)

    elif command == "metadata-delete":
        if len(args) > 2:
            endpoint_name = get_arg(1)
            key = get_arg(2)
        else:
            endpoint_name = None
            key = get_arg(1)
        api_client.metadata_delete(
            endpoint_name=endpoint_name,
            key=key)

    elif command == "manager-list":
        managers = api_client.manager_configs_list()
        for manager in managers:
            print manager

    elif command == "manager-active":
        managers = api_client.manager_active_list()
        for uuid in managers:
            print uuid

    elif command == "manager-log":
        manager = get_arg(1)
        entries = api_client.manager_log(manager)
        for (ts, level, message) in entries:
            print log_format(level) % (ts, level, message)

    elif command == "manager-watch":
        manager = get_arg(1)
        last_ts = 0.0
        while True:
            entries = api_client.manager_log(manager, since=last_ts)
            for (ts, level, message) in entries:
                print log_format(level) % (ts, level, message)
                last_ts = ts
            time.sleep(watch_delay)

    elif command == "manager-update":
        manager = get_arg(1)
        new_conf = ""
        for line in sys.stdin.readlines():
            new_conf += line
        api_client.manager_update(manager, new_conf)

    elif command == "manager-info":
        manager = get_arg(1)
        info = api_client.manager_info(manager)
        print json.dumps(info, indent=2)

    elif command == "manager-show":
        manager = get_arg(1)
        config = api_client.manager_config(manager)
        print json.dumps(config, indent=2)

    elif command == "manager-remove":
        manager = get_arg(1)
        api_client.manager_remove(manager)

    elif command == "ips":
        if len(args) > 1:
            endpoint_name = get_arg(1)
        else:
            endpoint_name = None
        ips = api_client.endpoint_ips(endpoint_name=endpoint_name)
        for ip in ips:
            print ip

    elif command == "register":
        if len(args) > 1:
            ip = get_arg(1)
        else:
            ip = None
        api_client.ip_register(ip)

    elif command == "drop":
        if len(args) > 1:
            ip = get_arg(1)
        else:
            ip = None
        api_client.ip_drop(ip)

    elif command == "associate":
        if len(args) > 2:
            endpoint_name = get_arg(1)
            instance_id = get_arg(2)
        else:
            endpoint_name = None
            instance_id = get_arg(1)
        api_client.associate(
            endpoint_name=endpoint_name,
            instance_id=instance_id)

    elif command == "disassociate":
        if len(args) > 2:
            endpoint_name = get_arg(1)
            instance_id = get_arg(2)
        else:
            endpoint_name = None
            instance_id = get_arg(1)
        api_client.disassociate(
            endpoint_name=endpoint_name,
            instance_id=instance_id)

    elif command == "instances":
        if len(args) > 1:
            endpoint_name = get_arg(1)
        else:
            endpoint_name = None
        instances = api_client.instances(endpoint_name=endpoint_name)
        for (state, instance_list) in instances.items():
            for instance_id in instance_list:
                print instance_id, state

    elif command == "state":
        if len(args) > 1:
            endpoint_name = get_arg(1)
        else:
            endpoint_name = None
        state = api_client.endpoint_state(endpoint_name=endpoint_name)
        print json.dumps(state, indent=2)

    elif command == "start" or command == "stop" or command == "pause":
        if len(args) > 1:
            endpoint_name = get_arg(1)
        else:
            endpoint_name = None
        api_client.endpoint_action(
            endpoint_name=endpoint_name,
            action=command)

    elif command == "get-metrics":
        if len(args) > 1:
            endpoint_name = get_arg(1)
        else:
            endpoint_name = None
        metrics = api_client.endpoint_metrics(
            endpoint_name=endpoint_name)
        print metrics

    elif command == "set-metrics":
        if len(args) > 1:
            endpoint_name = get_arg(1)
        else:
            endpoint_name = None
        new_metrics = ""
        for line in sys.stdin.readlines():
            new_metrics += line
        api_client.endpoint_metrics_set(
            endpoint_name=endpoint_name,
            metrics=json.loads(new_metrics))

    elif command == "log":
        if len(args) > 1:
            endpoint_name = get_arg(1)
        else:
            endpoint_name = None
        entries = api_client.endpoint_log(endpoint_name=endpoint_name)
        for (ts, level, message) in entries:
            print log_format(level) % (ts, level, message)

    elif command == "watch":
        if len(args) > 1:
            endpoint_name = get_arg(1)
        else:
            endpoint_name = None
        last_ts = 0.0
        while True:
            entries = api_client.endpoint_log(
                endpoint_name=endpoint_name,
                since=last_ts)
            for (ts, level, message) in entries:
                print log_format(level) % (ts, level, message)
                last_ts = ts
            time.sleep(watch_delay)

    elif command == "post":
        if len(args) > 1:
            endpoint_name = get_arg(1)
        else:
            endpoint_name = None
        message = ""
        for line in sys.stdin.readlines():
            message += line
        api_client.endpoint_post(
            endpoint_name=endpoint_name,
            message=message.strip())

    elif command == "sessions":
        if len(args) > 1:
            endpoint_name = get_arg(1)
        else:
            endpoint_name = None
        sessions = api_client.session_list(endpoint_name=endpoint_name)
        for client, backend in sessions.items():
            print client, backend

    elif command == "kill":
        if len(args) > 2:
            endpoint_name = get_arg(1)
            session = get_arg(2)
        else:
            endpoint_name = None
            session = get_arg(1)
        api_client.session_kill(
            endpoint_name=endpoint_name,
            session=session)

    elif command == "passwd":
        if len(args) > 1:
            new_password = get_arg(1)
        else:
            new_password = None
        api_client.api_key_set(new_password)

    else:
        raise cli.InvalidArguments()

def main():
    cli.main(client_main, [API, PASSWORD, ASKPASS, WATCH_DELAY], HELP)

if __name__ == "__main__":
    main()
