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
import gc
import sys
import time
import signal
import traceback
import ctypes
import tempfile
import threading

from . import cli

def find_objects(t):
    return filter(lambda o: isinstance(o, t), gc.get_objects())
def dump_threads(output):
    output.write("--- %d ---\n" % time.time())
    for i, stack in sys._current_frames().items():
        stack_format = "thread%s\n%s\n" % (
            str(i), "".join(traceback.format_stack(stack)))
        output.write(stack_format)
    output.flush()

def commit_suicide():
    debug_filename = os.path.join(
        tempfile.gettempdir(),
        "reactor.%d.out" % os.getpid())
    debug_output = open(debug_filename, 'w')
    os.unlink(debug_filename)

    while True:
        # NOTE: We use SIGINT as the mechanism to raise
        # an exception in the main thread. This seems to
        # be more effective than thread.interrupt_main().
        os.kill(os.getpid(), signal.SIGINT)
        time.sleep(1.0)
        dump_threads(debug_output)

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

def main():
    # Create a child process.
    parent_pid = os.getpid()
    child_pid = os.fork()
    if child_pid == 0:
        # We setup a safe procedure here to ensure that the
        # child will receive a SIGTERM when the parent exits.
        # This is because we can't reliably ensure that when
        # we are hit by a signal we will have time to deliver
        # the appropriate signal to the child (perhaps upstart
        # is being nasty, or the user).
        libc = ctypes.CDLL("libc.so.6")

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
        cli.main(is_server=True)
        sys.exit(0)

    # Wait for the child to die.
    (_, status) = os.waitpid(child_pid, 0)
    sys.exit(os.WEXITSTATUS(status))

if __name__ == "__main__":
    main()
