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

import logging
import threading
import traceback
import zookeeper

from reactor.log import log

ZOO_OPEN_ACL_UNSAFE = {"perms":0x1f, "scheme":"world", "id":"anyone"}
ZOO_CONNECT_WAIT_TIME = 10.0

# Save the exception for use in other modules.
ZookeeperException = zookeeper.ZooKeeperException
BadArgumentsException = zookeeper.BadArgumentsException

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
        except Exception:
            raise ZookeeperException("Unknown error: %s" % str(traceback.format_exc()))
    wrapped_fn.__name__ = fn.__name__
    wrapped_fn.__doc__ = fn.__doc__
    return wrapped_fn

@log
@wrap_exceptions
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
        handle = zookeeper.init(server_list, connect_watcher, int(ZOO_CONNECT_WAIT_TIME * 1000))
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

class ZookeeperConnection(object):

    def __init__(self, servers, acl=None):
        # FIXME(amscanne): Something really funny is going
        # on here. Unfortunately, I don't really have the
        # energy to look into this right now, but basically
        # when this is driven through the test framework,
        # We will see an exception that self is not an instance
        # of ZookeeperConnection for *some* tests. Now, I
        # know we did the mocking underneath but I can't for
        # the life of me figure out what's going on here.
        # So -- no object constructor for this fella!
        #   super(ZookeeperConnection, self).__init__()
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

    @log
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

    @log
    @wrap_exceptions
    def silence(self):
        zookeeper.set_debug_level(zookeeper.LOG_LEVEL_ERROR)

    def _write(self, path, contents, ephemeral, exclusive, sequential, mustexist):
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

        if sequential:
            exists = False
        else:
            exists = zookeeper.exists(self.handle, path)

        # Don't create it if we're exclusive.
        if exists and exclusive:
            return False

        # Check if we require the node to exist.
        if not exists and mustexist:
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
            return path
        else:
            flags = 0
            if ephemeral:
                flags = flags | zookeeper.EPHEMERAL
            if sequential:
                flags = flags | zookeeper.SEQUENCE

            # NOTE: We return the final path created.
            return zookeeper.create(self.handle, path, contents, [self.acl], flags)

    @log
    @wrap_exceptions
    def write(
        self,
        path,
        contents,
        ephemeral=False,
        exclusive=False,
        sequential=False,
        mustexist=False):

        """
        Writes the contents to the path in zookeeper. It will create the path in
        zookeeper if it does not already exist.

        This method will return the path if the value is written, False otherwise.
        (The value will not be written if the exclusive is True and the node
        already exists.)
        """
        if not(path) or contents is None:
            raise BadArgumentsException("Invalid path/contents: %s/%s" % (path, contents))

        while True:
            try:
                # Perform the write.
                return self._write(path=path,
                                   contents=contents,
                                   ephemeral=ephemeral,
                                   exclusive=exclusive,
                                   sequential=sequential,
                                   mustexist=mustexist)
            except zookeeper.NodeExistsException:
                # If we're writing to an exclusive path, then the caller lost
                # to another thread/writer. Else, retry.
                if exclusive:
                    return False

    @log
    @wrap_exceptions
    def exists(self, path):
        """
        Return whether the path exists.
        """
        return zookeeper.exists(self.handle, path)

    @log
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

    @log
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

    @log
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

    @log
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
        finally:
            self.cond.release()

        value, _ = zookeeper.get(self.handle, path, self.zookeeper_watch)
        return value

    @log
    @wrap_exceptions
    def watch_children(self, path, fn, clean=False):
        if not (path and fn):
            raise BadArgumentsException("Invalid path/fn: %s/%s" % (path, fn))

        if not zookeeper.exists(self.handle, path):
            self.write(path, "")

        self.cond.acquire()
        try:
            if clean:
                self.child_watches[path] = []
            if not(fn in self.child_watches.get(path, [])):
                self.child_watches[path] = self.child_watches.get(path, []) + [fn]
        finally:
            self.cond.release()

        rval = zookeeper.get_children(self.handle, path, self.zookeeper_watch)
        return rval

    def zookeeper_watch(self, zh, event, state, path):
        self.cond.acquire()
        try:
            if event == zookeeper.CHILD_EVENT:
                fns = self.child_watches.get(path, None)
            elif event == zookeeper.CHANGED_EVENT:
                fns = self.content_watches.get(path, None)
            else:
                fns = None
        finally:
            self.cond.release()

        result = None
        try:
            if fns and event == zookeeper.CHILD_EVENT:
                result = zookeeper.get_children(self.handle, path, self.zookeeper_watch)
            elif fns and event == zookeeper.CHANGED_EVENT:
                result, _ = zookeeper.get(self.handle, path, self.zookeeper_watch)
        except zookeeper.NoNodeException:
            pass

        if result != None and fns != None:
            for fn in fns:
                # Don't allow an individual watch firing an exception to
                # prevent all other watches from being fired. Just log an
                # error message and moved on to the next callback.
                try:
                    fn(result)
                except Exception:
                    logging.exception("Error executing watch for %s.", path)

    @log
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

    @log
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
