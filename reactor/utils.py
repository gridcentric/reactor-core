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

import uuid
import time
import hashlib
import traceback
import threading
import tempfile
import sys
import types
import weakref
import os
import gc

from . log import log

def find_objects(t):
    return filter(lambda o: isinstance(o, t), gc.get_objects())

def dump_threads(output):
    output.write("--- %d ---\n" % time.time())
    for i, stack in sys._current_frames().items():
        stack_format = "thread%s\n%s\n" % (
            str(i), "".join(traceback.format_stack(stack)))
        output.write(stack_format)
    output.flush()

def run_heartbeat(debug_output):
    while True:
        debug_output.seek(0, 0)
        debug_output.truncate()
        dump_threads(debug_output)
        time.sleep(1.0)

def start_heartbeat():
    # We open up a file and unlink immediately.
    # The file data will continue to get dumped
    # to disk, but will be cleaned up automatically
    # when the process disappears. This is simply
    # to enable easier debugging if we end up with
    # reactor processes that do not die as expected.
    debug_output = tempfile.NamedTemporaryFile()
    os.unlink(debug_output.name)

    # Start a heartbeat thread.
    t = threading.Thread(target=lambda: run_heartbeat(debug_output))
    t.daemon = True
    t.start()

def fixup_thread_error():
    # Silence annoying error output.
    # See: http://stackoverflow.com/questions/13193278/understand-python-threading-bug
    threading._DummyThread._Thread__stop = lambda x: 42

def import_class(import_str):
    module_str, _, class_str = import_str.rpartition('.')
    try:
        __import__(module_str)
        return getattr(sys.modules[module_str], class_str)
    except (ImportError, ValueError, AttributeError), _:
        raise ImportError("Class %s can not be loaded." % (import_str,))

def sha_hash(input_str):
    hash_fn = hashlib.new('sha1')
    hash_fn.update(input_str)
    return hash_fn.hexdigest()

def random_key():
    return sha_hash(str(uuid.uuid4()))

def callback(fn):

    def closure(ref, name=None, im_func=None):
        @log
        def cb(*args, **kwargs):
            real_obj = ref()

            if real_obj is not None:
                if im_func is not None:
                    return im_func(real_obj, *args, **kwargs)
                else:
                    return real_obj(*args, **kwargs)
            else:
                return None

        if name:
            cb.__name__ = name
        return cb

    if isinstance(fn, types.MethodType):
        name = fn.__name__
        return closure(weakref.ref(fn.im_self), name=name, im_func=fn.im_func)
    elif fn is not None:
        name = hasattr(fn, "__name__") and fn.__name__
        return closure(weakref.ref(fn), name=name)
    else:
        return closure(lambda: None)
