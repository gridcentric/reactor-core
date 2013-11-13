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
This provides a simple wrapper around the CLI tools that does safe restarts and
stops of the process (if it's acting as a server). Because the server can take
a while to shutdown (it waits for all non-daemon threads, which may be waiting
for child processes, etc.) this allows us to integrate cleanly with supervisors
(i.e. upstart) that expect instant response from a SIGTERM.

Basically, we always run a child for the actual server. When we get hit with a
SIGTERM, we deliver the appropriate signal to that process and exit. The child
process will unbind the socket but stay alive to handle ongoing loadbalancer
connections, etc.
"""

import os
import sys
import time
import atexit
import signal
import ctypes
import tempfile
import threading
import logging

from . import cli
from . import log
from . import utils

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

    # Register our cleanup function.
    def rm_pidfile():
        os.remove(pidfile)
    atexit.register(rm_pidfile)

    # Write out the pidfile.
    pid = str(os.getpid())
    f = open(pidfile,'w+')
    f.write("%s\n" % pid)
    f.close()

def commit_suicide():
    # We open up a file and unlink immediately.
    # The file data will continue to get dumped
    # to disk, but will be cleaned up automatically
    # when the process disappears. This is simply
    # to enable easier debugging if we end up with
    # reactor processes that do not die as expected.
    debug_output = tempfile.NamedTemporaryFile()
    os.unlink(debug_output.name)

    while True:
        # NOTE: We use SIGINT as the mechanism to raise
        # an exception in the main thread. This seems to
        # be more effective than thread.interrupt_main().
        os.kill(os.getpid(), signal.SIGINT)
        time.sleep(1.0)
        utils.dump_threads(debug_output)

SUICIDE_THREAD = threading.Thread(target=commit_suicide)
SUICIDE_THREAD.daemon = True

def start_suicide(signo=None, frame=None):
    # Ugh. This is plain awful. I've had so many problems
    # with the paste httpserver eating KeyboardInterrupts.
    # For safety, we start a thread that commits suicide
    # every second until the process is actually gone.
    try:
        SUICIDE_THREAD.start()
    except RuntimeError:
        # We're hit with a second signal?
        # Let's get more serious about this.
        os._exit(1)

ZK_SERVERS = cli.OptionSpec(
    "zk_servers",
    "A list of Zookeeper server addresses.",
    lambda x: x.split(","),
    ["localhost"]
)

PIDFILE = cli.OptionSpec(
    "pidfile",
    "Daemonize and write the pid the given file.",
    str,
    None
)

LOG = cli.OptionSpec(
    "log",
    "Log to a file (as opposed to stdout).",
    str,
    None
)

VERBOSE = cli.OptionSpec(
    "verbose",
    "Enable verbose logging.",
    None,
    None
)

SAFE_STOP = cli.OptionSpec(
    "safe",
    "Enable safe stop (useful for some loadbalancers).",
    None,
    None
)

def main(real_main_fn, option_specs, help_msg):
    try:
        # We setup a safe procedure here to ensure that the
        # child will receive a SIGTERM when the parent exits.
        # This is because we can't reliably ensure that when
        # we are hit by a signal we will have time to deliver
        # the appropriate signal to the child (perhaps upstart
        # is being nasty, or the user).
        libc = ctypes.CDLL("libc.so.6")
    except OSError:
        # We must be an operating system where we don't
        # have this capability. Unfortunately, we can't
        # really use our fork(), waitpid() trick.
        libc = None

    # Insert our specs.
    option_specs = option_specs[:]
    option_specs.append(ZK_SERVERS)
    option_specs.append(PIDFILE)
    option_specs.append(LOG)
    option_specs.append(VERBOSE)
    option_specs.append(SAFE_STOP)

    def server_main(options, args):
        # We don't expect arguments.
        if args:
            raise cli.InvalidArguments()

        # Pull out our zk_servers.
        zk_servers = options.get("zk_servers")

        # Enable logging.
        loglevel = logging.INFO
        if options.get("verbose"):
            loglevel = logging.DEBUG
        logfile = options.get("log")
        log.configure(loglevel, logfile)

        # Daemonize if necessary.
        pidfile = options.get("pidfile")
        if pidfile:
            daemonize(pidfile)

        # Check if we are safe stopping.
        safe_stop = options.get("safe")

        if safe_stop and libc is not None:
            # Create a child process.
            parent_pid = os.getpid()
            child_pid = os.fork()
            if child_pid == 0:
                # Set P_SETSIGDEATH to SIGTERM.
                libc.prctl(1, signal.SIGTERM)

                # Ensure that our parent is still who we think it is.
                # This is because we have a race above, where we could
                # have already missed the parent death.
                if os.getppid() != parent_pid:
                    sys.exit(1)

                # Install a handler for SIGTERM that raises an
                # exception in the main thread. This will allow
                # us to wait for our non-daemon threads to end.
                signal.signal(signal.SIGTERM, start_suicide)

                # Run our server command.
                real_main_fn(zk_servers, options)

            # Wait for the child to die.
            (_, status) = os.waitpid(child_pid, 0)
            sys.exit(os.WEXITSTATUS(status))
        else:
            # Run the server directly.
            real_main_fn(zk_servers, options)

    # Run the cli.
    cli.main(server_main, option_specs, help_msg)
