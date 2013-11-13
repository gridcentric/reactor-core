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
import threading

from . atomic import Atomic

class Worker(threading.Thread):

    def __init__(self, queue):
        super(Worker, self).__init__()
        self._queue = queue
        self.daemon = True

    def run(self):
        while True:
            job = self._queue.pop()
            if job is None:
                break
            job.run()
            del job

class Job(object):

    def __init__(self, fn, args, kwargs):
        super(Job, self).__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs
        self._cond = threading.Condition()
        self._exc_info = None
        self._returnval = None
        self._done = False

    def run(self):
        assert not self._done

        try:
            self._returnval = self._fn(*self._args, **self._kwargs)
        except BaseException:
            self._exc_info = sys.exc_info()

        self._cond.acquire()
        try:
            self._done = True
        finally:
            self._cond.notifyAll()
            self._cond.release()

    def join(self):
        self._cond.acquire()
        try:
            while not self._done:
                self._cond.wait()
            if self._exc_info:
                raise self._exc_info[0], \
                      self._exc_info[1], \
                      self._exc_info[2]
            return self._returnval
        finally:
            self._cond.release()

class Queue(object):

    def __init__(self):
        super(Queue, self).__init__()
        self._cond = threading.Condition()
        self._waiting = 0
        self._jobs = []

    def push(self, job):
        self._cond.acquire()
        try:
            self._jobs.append(job)
        finally:
            self._cond.notifyAll()
            self._cond.release()

    def spare(self):
        self._cond.acquire()
        try:
            if self._waiting < len(self._jobs):
                return 0
            else:
                return self._waiting - len(self._jobs)
        finally:
            self._cond.release()

    def pop(self):
        self._cond.acquire()
        try:
            self._waiting += 1
            while len(self._jobs) == 0:
                self._cond.wait()
            return self._jobs.pop(0)
        finally:
            self._waiting -= 1
            self._cond.release()

class Threadpool(Atomic):

    def __init__(self):
        super(Threadpool, self).__init__()
        self._queue = Queue()
        self._workers = 0

    def __del__(self):
        self.clear()

    @Atomic.sync
    def clear(self):
        for _ in range(self._workers):
            self._queue.push(None)
        self._workers = 0

    @Atomic.sync
    def new_worker(self):
        self._workers += 1
        w = Worker(self._queue)
        w.start()

    def submit(self, fn, *args, **kwargs):
        job = Job(fn, args, kwargs)
        if self._queue.spare() == 0:
            self.new_worker()
        self._queue.push(job)
        return job
