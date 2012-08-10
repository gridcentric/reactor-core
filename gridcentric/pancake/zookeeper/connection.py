import logging
import zookeeper
import threading
import traceback

ZOO_OPEN_ACL_UNSAFE = {"perms":0x1f, "scheme":"world", "id":"anyone"}
ZOO_EVENT_NONE = 0
ZOO_EVENT_NODE_CREATED = 1
ZOO_EVENT_NODE_DELETED = 2
ZOO_EVENT_NODE_DATA_CHANGED = 3
ZOO_EVENT_NODE_CHILDREN_CHANGED = 4

# Save the exception for use in other modules.
ZookeeperException = zookeeper.ZooKeeperException

def connect(servers):
    cond = threading.Condition()
    connected = [False]

    # We attempt a connection for 10 seconds here. This is a long timeout
    # for servicing a web request, so hopefully it is successful.
    def connect_watcher(zh, event, state, path):
        logging.debug("CONNECT WATCHER: event=%s, state=%s, path=%s" % (event, state, path))
        try:
            cond.acquire()
            if state == zookeeper.CONNECTED_STATE:
                # We only want to notify the main thread once the state has been
                # connected. We store the connected variable in an odd way because
                # of the way variables are bound in the local scope for functions.
                connected[0] = True
                cond.notify()
        finally:
            cond.release()

    cond.acquire()
    try:
        # We default to port 2181 if no port is provided as part of the host specification.
        server_list = ",".join(map(lambda x: (x.find(":") > 0 and x) or "%s:2181" % x, servers))
        handle = zookeeper.init(server_list, connect_watcher, 10000)
        cond.wait(60.0)
    finally:
        # Save whether we were successful or not.
        is_connected = connected[0]
        cond.release()

    if not(is_connected):
        raise ZookeeperException("Unable to connect.")

    return handle

def wrap_exceptions(fn):
    # We wrap all system exceptions in the Zookeeper-specifc exception.
    # Some versions of Zookeeper have python bindings that don't correctly
    # throw errors for timed-out exceptions.
    # See: https://issues.apache.org/jira/browse/ZOOKEEPER-1318
    def wrapped_fn(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ZookeeperException:
            raise
        except:
            raise ZookeeperException("Unknown error: %s" % str(traceback.format_exc()))
    return wrapped_fn

class ZookeeperConnection(object):

    @wrap_exceptions
    def __init__(self, servers, acl=ZOO_OPEN_ACL_UNSAFE):
        self.cond = threading.Condition()
        self.acl = acl
        self.watches = {}
        self.silence()
        self.handle = connect(servers)

    def __del__(self):
        self.close()

    def close(self):
        self.cond.acquire()
        # Forget current watches, otherwise it's easy for
        # circular references to keep this object around.
        self.watches = {}
        try:
            if self.handle:
                zookeeper.close(self.handle)
                self.handle = None
        except:
            logging.warn("Error closing Zookeeper handle.")
        finally:
            self.cond.release()

    @wrap_exceptions
    def silence(self):
        zookeeper.set_debug_level(zookeeper.LOG_LEVEL_ERROR)

    @wrap_exceptions
    def write(self, path, contents, ephemeral=False, exclusive=False):
        """ 
        Writes the contents to the path in zookeeper. It will create the path in
        zookeeper if it does not already exist.
        """
        partial_path = ''

        # We start from the second element because we do not want to inclued
        # the initial empty string before the first "/" because all paths begin
        # with "/". We also don't want to include the final node because that
        # is dealt with later.

        for path_part in path.split("/")[1:-1]:
            partial_path = partial_path + "/" + path_part
            if not(zookeeper.exists(self.handle, partial_path)):
                try:
                    zookeeper.create(self.handle, partial_path, '', [self.acl], 0)
                except zookeeper.NodeExistsException:
                    pass

        exists = zookeeper.exists(self.handle, path)

        # Don't create it if we're exclusive.
        if exists and exclusive:
            return False

        # We make sure that we have the creation flags for ephemeral nodes,
        # otherwise they could be associated with previous connections that
        # have not yet timed out.
        if ephemeral and exists:
            try:
                zookeeper.delete(self.handle, path)
            except zookeeper.NoNodeException:
                pass
            exists = False

        if exists:
            zookeeper.set(self.handle, path, contents)
            return True
        else:
            flags = (ephemeral and zookeeper.EPHEMERAL or 0)
            try:
                zookeeper.create(self.handle, path, contents, [self.acl], flags)
                return True
            except zookeeper.NodeExistsException:
                if not(exclusive):
                    # Woah, something happened between the top and here.
                    # We just restart and retry the whole routine.
                    self.write(path, contents, ephemeral=ephemeral)
                else:
                    return False

    @wrap_exceptions
    def read(self, path, default=None):
        """
        Returns the conents in the path. default is returned if the path does not exists.
        """
        value = default
        if zookeeper.exists(self.handle, path):
            value, timeinfo = zookeeper.get(self.handle, path)

        return value

    @wrap_exceptions
    def list_children(self, path):
        """
        Returns a list of all the children nodes in the path. None is returned if the path does
        not exist.
        """
        if zookeeper.exists(self.handle, path):
            value = zookeeper.get_children(self.handle, path)
            return value

    @wrap_exceptions
    def delete(self, path):
        """
        Delete the path.
        """
        if zookeeper.exists(self.handle, path):
            path_children = zookeeper.get_children(self.handle, path)
            for child in path_children:
                try:
                    self.delete(path + "/" + child)
                except zookeeper.NoNodeException:
                    pass
            try:
                zookeeper.delete(self.handle, path)
            except zookeeper.NoNodeException:
                pass

    @wrap_exceptions
    def trylock(self, path, default_value=""):
        """
        Try to write to the path in an exclusive way.
        """
        return self.write(path, default_value,
                          ephemeral=False, exclusive=True)

    @wrap_exceptions
    def watch_contents(self, path, fn, default_value="", clean=False):
        if not zookeeper.exists(self.handle, path):
            self.write(path, default_value)

        self.cond.acquire()
        try:
            if clean:
                self.watches[path] = []
            if not(fn in self.watches.get(path, [])):
                self.watches[path] = self.watches.get(path, []) + [fn]
            value, timeinfo = zookeeper.get(self.handle, path, self.zookeeper_watch)
        finally:
            self.cond.release()
        return value

    @wrap_exceptions
    def watch_children(self, path, fn, default_value="", clean=False):
        self.cond.acquire()
        if not zookeeper.exists(self.handle, path):
            self.write(path, default_value)

        try:
            if clean:
                self.watches[path] = []
            if not(fn in self.watches.get(path, [])):
                self.watches[path] = self.watches.get(path, []) + [fn]
            rval = zookeeper.get_children(self.handle, path, self.zookeeper_watch)
        finally:
            self.cond.release()
        return rval

    @wrap_exceptions
    def zookeeper_watch(self, zh, event, state, path):
        self.cond.acquire()
        try:
            fns = self.watches.get(path, None)
            if fns:
                result = None
                if event == ZOO_EVENT_NODE_CHILDREN_CHANGED:
                    result = zookeeper.get_children(self.handle, path, self.zookeeper_watch)
                elif event == ZOO_EVENT_NODE_DATA_CHANGED:
                    result, _ = zookeeper.get(self.handle, path, self.zookeeper_watch)
                if result != None:
                    for fn in fns:
                        # Don't allow an individual watch firing an exception to
                        # prevent all other watches from being fired. Just log an
                        # error message and moved on to the next callback.
                        try:
                            fn(result)
                        except:
                            logging.exception("Error executing watch for %s." % path)
        finally:
            self.cond.release()

    @wrap_exceptions
    def clear_watch_path(self, path):
        self.cond.acquire()
        try:
            if path in self.watches:
                del self.watches[path]
        finally:
            self.cond.release()

    @wrap_exceptions
    def clear_watch_fn(self, fn):
        self.cond.acquire()
        try:
            for path in self.watches:
                fns = self.watches[path]
                if fn in fns:
                    fns.remove(fn)
        finally:
            self.cond.release()
