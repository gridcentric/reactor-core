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
Simple utility class to provide atomic operations.
"""

import threading

class Atomic(object):

    """
    A simple mixin-type class, which provides basic synchronization.
    """

    def __init__(self, *args, **kwargs):
        super(Atomic, self).__init__(*args, **kwargs)
        self._cond = threading.Condition()

    def _notify(self):
        self._cond.notify()

    def _wait(self, timeout=None):
        self._cond.wait(timeout=timeout)

    @staticmethod
    def sync(fn):
        def wrapper_fn(self, *args, **kwargs):
            self._cond.acquire()
            try:
                return fn(self, *args, **kwargs)
            finally:
                self._cond.release()
        wrapper_fn.__name__ = fn.__name__
        wrapper_fn.__doc__ = fn.__doc__
        return wrapper_fn

class AtomicRunnable(threading.Thread, Atomic):

    def __init__(self, *args, **kwargs):
        threading.Thread.__init__(self)
        Atomic.__init__(self, *args, **kwargs)
        self._running = True

    @Atomic.sync
    def is_running(self):
        return self._running

    @Atomic.sync
    def stop(self):
        self._running = False
        self._notify()

    def run(self, *args, **kwargs):
        raise NotImplementedError()
