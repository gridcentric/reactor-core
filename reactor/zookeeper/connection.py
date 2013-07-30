import logging
import threading
import traceback
import zookeeper

ZOO_OPEN_ACL_UNSAFE = {"perms":0x1f, "scheme":"world", "id":"anyone"}
ZOO_CONNECT_WAIT_TIME = 60.0

# Save the exception for use in other modules.
ZookeeperException = zookeeper.ZooKeeperException
BadArgumentsException = zookeeper.BadArgumentsException

def connect(servers, timeout=ZOO_CONNECT_WAIT_TIME):
    cond = threading.Condition()
    connected = [False]

    # We attempt a connection for 10 seconds here. This is a long timeout
    # for servicing a web request, so hopefully it is successful.
    def connect_watcher(zh, event, state, path):
        logging.debug("CONNECT WATCHER: event=%s, state=%s, path=%s", event, state, path)
        try:
            cond.acquire()
            if state == zookeeper.CONNECTED_STATE:
                # We only want to notify the main thread once the state has been
                # connected. We store the connected variable in an odd way because
                # of the way variables are bound in the local scope for functions.
                connected[0] = True
                cond.notify()
            elif state < 0:
                # We've received an error state, bonk out.
                cond.notify()
        finally:
            cond.release()

    if not(servers) or not(isinstance(servers, (list, tuple))):
        raise BadArgumentsException("servers must be a list or tuple: %s" % servers)

    # We default to port 2181 if no port is provided as part of the host specification.
    server_list = ",".join(map(lambda x: (x.find(":") > 0 and x) or "%s:2181" % x, servers))

    try:
        cond.acquire()
        handle = zookeeper.init(server_list, connect_watcher, 10000)
        cond.wait(timeout)
    except Exception as e:
        raise ZookeeperException("Exception while connecting to zookeeper: %s" % e.message)
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
    wrapped_fn.__name__ = fn.__name__
    wrapped_fn.__doc__ = fn.__doc__
    return wrapped_fn

class ZookeeperConnection(object):

    @wrap_exceptions
    def __init__(self, servers, acl=None):
        if acl is None:
            acl = ZOO_OPEN_ACL_UNSAFE
        self.cond = threading.Condition()
        self.acl = acl
        self.content_watches = {}
        self.child_watches = {}
        self.silence()
        self.handle = connect(servers)

    def __del__(self):
        self.close()

    def close(self):
        self.cond.acquire()
        # Forget current watches, otherwise it's easy for
        # circular references to keep this object around.
        self.content_watches = {}
        self.child_watches = {}
        try:
            if hasattr(self, 'handle') and self.handle:
                zookeeper.close(self.handle)
                self.handle = None
        except Exception:
            logging.warn("Error closing Zookeeper handle.")
        finally:
            self.cond.release()

    @wrap_exceptions
    def silence(self):
        zookeeper.set_debug_level(zookeeper.LOG_LEVEL_ERROR)

    def _write(self, path, contents, ephemeral, exclusive):
        # We start from the second element because we do not want to inclued
        # the initial empty string before the first "/" because all paths begin
        # with "/". We also don't want to include the final node because that
        # is dealt with later.
        partial_path = ''
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
            zookeeper.create(self.handle, path, contents, [self.acl], flags)
            return True

    @wrap_exceptions
    def write(self, path, contents, ephemeral=False, exclusive=False):
        """
        Writes the contents to the path in zookeeper. It will create the path in
        zookeeper if it does not already exist.

        This method will return True if the value is written, False otherwise.
        (The value will not be written if the exclusive is True and the node
        already exists.)
        """
        if not(path) or contents is None:
            raise BadArgumentsException("Invalid path/contents: %s/%s" % (path, contents))

        while True:
            try:
                # Perform the write
                return self._write(path, contents, ephemeral, exclusive)
            except zookeeper.NodeExistsException:
                # If we're writing to an exclusive path, then the caller lost
                # to another thread/writer. Else, retry.
                if exclusive:
                    return False

    @wrap_exceptions
    def exists(self, path):
        """
        Return whether the path exists.
        """
        return zookeeper.exists(self.handle, path)

    @wrap_exceptions
    def read(self, path, default=None):
        """
        Returns the conents in the path. default is returned if the path does not exists.
        """
        if not path:
            raise BadArgumentsException("Invalid path: %s" % (path))

        value = default
        if zookeeper.exists(self.handle, path):
            try:
                value, _ = zookeeper.get(self.handle, path)
            except zookeeper.NoNodeException:
                pass

        return value

    @wrap_exceptions
    def list_children(self, path):
        """
        Returns a list of all the children nodes in the path. None is returned if the path does
        not exist.
        """
        if not path:
            raise BadArgumentsException("Invalid path: %s" % (path))

        if zookeeper.exists(self.handle, path):
            try:
                value = zookeeper.get_children(self.handle, path)
                return value
            except zookeeper.NoNodeException:
                pass
        return []

    @wrap_exceptions
    def delete(self, path):
        """
        Delete the path.
        """
        if not path:
            raise BadArgumentsException("Invalid path: %s" % (path))

        path_children = self.list_children(path)
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
    def watch_contents(self, path, fn, default_value="", clean=False):
        if not (path and fn):
            raise BadArgumentsException("Invalid path/fn: %s/%s" % (path, fn))

        if not zookeeper.exists(self.handle, path):
            self.write(path, default_value)

        self.cond.acquire()
        try:
            if clean:
                self.content_watches[path] = []
            if not(fn in self.content_watches.get(path, [])):
                self.content_watches[path] = self.content_watches.get(path, []) + [fn]
            value, _ = zookeeper.get(self.handle, path, self.zookeeper_watch)
        finally:
            self.cond.release()
        return value

    @wrap_exceptions
    def watch_children(self, path, fn, clean=False):
        if not (path and fn):
            raise BadArgumentsException("Invalid path/fn: %s/%s" % (path, fn))

        self.cond.acquire()
        if not zookeeper.exists(self.handle, path):
            self.write(path, "")

        try:
            if clean:
                self.child_watches[path] = []
            if not(fn in self.child_watches.get(path, [])):
                self.child_watches[path] = self.child_watches.get(path, []) + [fn]
            rval = zookeeper.get_children(self.handle, path, self.zookeeper_watch)
        finally:
            self.cond.release()
        return rval

    @wrap_exceptions
    def zookeeper_watch(self, zh, event, state, path):
        self.cond.acquire()
        try:
            result = None
            if event == zookeeper.CHILD_EVENT:
                fns = self.child_watches.get(path, None)
                if fns:
                    try:
                        result = zookeeper.get_children(self.handle, path, self.zookeeper_watch)
                    except zookeeper.NoNodeException:
                        result = None
            elif event == zookeeper.CHANGED_EVENT:
                fns = self.content_watches.get(path, None)
                if fns:
                    try:
                        result, _ = zookeeper.get(self.handle, path, self.zookeeper_watch)
                    except zookeeper.NoNodeException:
                        result = None
            else:
                return

            if result != None and fns != None:
                for fn in fns:
                    # Don't allow an individual watch firing an exception to
                    # prevent all other watches from being fired. Just log an
                    # error message and moved on to the next callback.
                    try:
                        fn(result)
                    except Exception:
                        logging.exception("Error executing watch for %s.", path)
        finally:
            self.cond.release()

    @wrap_exceptions
    def clear_watch_path(self, path):
        if not path:
            raise BadArgumentsException("Invalid path: %s" % (path))

        self.cond.acquire()
        try:
            if path in self.content_watches:
                del self.content_watches[path]
            if path in self.child_watches:
                del self.child_watches[path]
        finally:
            self.cond.release()

    @wrap_exceptions
    def clear_watch_fn(self, fn):
        if not fn:
            raise BadArgumentsException("Invalid fn: %s" % (fn))

        self.cond.acquire()
        try:
            for path in self.content_watches:
                fns = self.content_watches[path]
                if fn in fns:
                    fns.remove(fn)
            for path in self.child_watches:
                fns = self.child_watches[path]
                if fn in fns:
                    fns.remove(fn)
        finally:
            self.cond.release()

    def sync(self):
        # This function exists to faciliate testing.
        # If the underlying zookeeper module is mocked,
        # then it is capable of flushing out all pending
        # watches, etc. The sync calls is what does that.
        if hasattr(zookeeper, '_sync'):
            getattr(zookeeper, '_sync')()
