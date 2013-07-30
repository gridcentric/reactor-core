"""
Simple utility class to provide atomic operations.
"""

import threading

class Atomic(object):

    """
    A simple mixin-type class, which provides basic synchronization.
    """

    def __init__(self):
        super(Atomic, self).__init__()
        self._cond = threading.Condition()

    def _notify(self):
        self._cond.notify()

    def _wait(self):
        self._cond.wait()

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
