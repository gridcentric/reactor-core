"""
Mock Zookeeper Implementation. This implemenetation is very limited compared
to the real zookeeper. No data is persistent and we only implement the
methods and flags reactor requires.

The real zookeeper object tracks sessions via an opaque handle rather than
as a python object. However, the call signature of all zookeeper functions
conveniently take the handle as the first argument. This lets us trivially
substitute the handle for a reference the the mock zookeeper object to
trivially track sessions without doing extra work to map between sessions
and mock zookeeper objects.
"""

import sys
import threading
import collections
import Queue

from reactor.log import log

# States.
CONNECTED_STATE = 3

# Flags.
EPHEMERAL = 1

# Events.
OK = 0
CHANGED_EVENT = 3
CHILD_EVENT = 4

# Log level.
LOG_LEVEL_ERROR = 0

class ZooKeeperException(Exception):
    pass

class NoNodeException(Exception):
    pass

class NodeExistsException(Exception):
    pass

class BadArgumentsException(Exception):
    pass

# Our pending list of tasks.
TASKS = Queue.Queue()

def _task_run(fn, *args, **kwargs):
    # Submit the task.
    TASKS.put((fn, args, kwargs))

    # Kick off a thread.
    def _run():
        (fn, args, kwargs) = TASKS.get()
        fn(*args, **kwargs)
        TASKS.task_done()
    thread = threading.Thread(target=_run)
    thread.daemon = True
    thread.start()

class ZkNode(object):
    """
    Represents a single zookeeper node.

    All operations on a node object must be locked by the caller in a
    multithreaded environment.
    """
    def __init__(self, name=None, parent=None, data="", handle=None):
        self._parent = parent
        self._name = name
        self._handle = handle
        self._lock = threading.RLock()
        self.reset(data=data)

    def _fire_data_callbacks(self):
        value = self._data
        for handle, callback in self._data_callbacks:
            _task_run(callback, handle, CHANGED_EVENT, CONNECTED_STATE, self._abspath())
        self._data_callbacks = []

    def _fire_child_callbacks(self):
        value = self._children.keys()
        for handle, callback in self._child_callbacks:
            _task_run(callback, handle, CHILD_EVENT, CONNECTED_STATE, self._abspath())
        self._child_callbacks = []

    def find_parent(self, path):
        comps = path.rsplit("/", 1)
        if len(comps) == 1:
            # If there is no other slash,
            # then this node must be child.
            return self, path
        else:
            # Otherwise find the given node,
            # and return the last piece.
            rv = self.find(comps[0]), comps[1]
            return rv

    def find(self, path):
        if path == "":
            return self
        with self._lock:
            (parent, child) = self.find_parent(path)
            with parent._lock:
                if not child in parent._children:
                    raise NoNodeException()
                return parent._children[child]

    def create(self, child, data, handle):
        if self._handle:
            # Can't create a child for an ephemeral node.
            raise BadArgumentsException()

        with self._lock:
            if child in self._children:
                raise NodeExistsException()
            self._children[child] = ZkNode(name=child, parent=self, data=data, handle=handle)
            self._fire_child_callbacks()

    def close(self, handle):
        with self._lock:
            to_delete = []
            to_recurse = []
            for child, node in self._children.items():
                if node._handle == handle:
                    to_delete.append(child)
                else:
                    to_recurse.append(node)
            for child in to_delete:
                self.delete(child)
            for node in to_recurse:
                node.close(handle)

    def dump(self, indent=0):
        with self._lock:
            sys.stdout.write("%s /%s\n" % (" " * indent, self._name or ""))
            if len(self._data_callbacks) > 0:
                sys.stdout.write("%s  data watches\n" % (" " * indent))
            for fn in self._data_callbacks:
                sys.stdout.write("%s  -> %s\n" % (" " * indent, fn))
            if len(self._child_callbacks) > 0:
                sys.stdout.write("%s  child watches\n" % (" " * indent))
            for fn in self._child_callbacks:
                sys.stdout.write("%s  -> %s\n" % (" " * indent, fn))
            for child, node in self._children.items():
                node.dump(indent=indent+2)

    def _abspath(self):
        if self._parent is None or self._name is None:
            # Handle the case for root.
            return ""
        else:
            # Handle the case for standard nodes.
            return self._parent._abspath() + "/" + self._name

    def set(self, data):
        with self._lock:
            self._data = data
            self._fire_data_callbacks()

    def get(self, handle, callback):
        with self._lock:
            if callback:
                self._data_callbacks.append((handle, callback))
            return self._data

    def delete(self, child):
        with self._lock:
            if not child in self._children:
                raise NoNodeException()
            node = self._children[child]
            if len(node._children) != 0:
                raise BadArgumentsException()
            del self._children[child]
            self._fire_child_callbacks()
        with node._lock:
            node._fire_data_callbacks()
            node._fire_child_callbacks()

    def reset(self, data=None):
        with self._lock:
            self._children = collections.OrderedDict()
            self._data = data
            self._data_callbacks = []
            self._child_callbacks = []

    def get_children(self, handle, callback):
        with self._lock:
            if callback:
                self._child_callbacks.append((handle, callback))
            return self._children.keys()

    def __repr__(self):
        return self._abspath()

ROOT = ZkNode()
CLIENTID = 1
LOCK = threading.Lock()

def _find(path, parent=False):
    if not path[0] == '/':
        raise BadArgumentsException()
    if parent:
        return ROOT.find_parent(path[1:])
    else:
        return ROOT.find(path[1:])

@log
def init(servers, callback, timeout):
    global CLIENTID
    # Get a new connection handle for this connection.
    # This connection handle is used to simulate ephemeral nodes.
    with LOCK:
        handle = CLIENTID
        CLIENTID += 1

    # Schedule the connected callback asynchronously.
    _task_run(callback, handle, OK, CONNECTED_STATE, "/")
    return handle

@log
def set_debug_level(level):
    pass

@log
def close(handle):
    ROOT.close(handle)

@log
def exists(handle, path):
    try:
        _find(path)
        return True
    except NoNodeException:
        return False

@log
def delete(handle, path):
    (parent, child) = _find(path, parent=True)
    return parent.delete(child)

@log
def create(handle, path, data, acl, flags):
    # NOTE: We don't really support ACLs in this
    # mock, nor do we support sequential nodes.
    (parent, child) = _find(path, parent=True)
    return parent.create(child, data, (flags & EPHEMERAL) and handle)

@log
def set(handle, path, data):
    node = _find(path)
    return node.set(data)

@log
def get(handle, path, callback=None):
    # NOTE: We don't support timeinfo.
    node = _find(path)
    return node.get(handle, callback=callback), None

@log
def get_children(handle, path, callback=None):
    node = _find(path)
    return node.get_children(handle, callback=callback)

@log
def dump():
    ROOT.dump()

@log
def reset():
    ROOT.reset()

@log
def _sync():
    # NOTE: See usage in zookeeper/connection.py.
    # This exists to faciliate testing and is not part
    # of the standard zookeeper interface.
    TASKS.join()
