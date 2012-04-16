#!/usr/bin/env python

import logging
import zookeeper

ZOO_OPEN_ACL_UNSAFE = {"perms":0x1f, "scheme":"world", "id":"anyone"}
ZOO_EVENT_NONE=0
ZOO_EVENT_NODE_CREATED=1
ZOO_EVENT_NODE_DELETED=2
ZOO_EVENT_NODE_DATA_CHANGED=3
ZOO_EVENT_NODE_CHILDREN_CHANGED=4

class ZookeeperConnection(object):

    def __init__(self, servers, acl=ZOO_OPEN_ACL_UNSAFE):
        self.silence()
        # We default to port 2181 if no port is provided as part of the host specification.
        server_list = ",".join(map(lambda x: (x.find(":") > 0 and x) or "%s:2181" % x, servers))
        self.handle = zookeeper.init(server_list)
        self.acl = acl
        self.watches = {}

    def silence(self):
        zookeeper.set_debug_level(zookeeper.LOG_LEVEL_ERROR)

    def write(self, path, contents):
        """ 
        Writes the contents to the path in zookeeper. It will create the path in
        zookeeper if it does not already exist.
        """
         
        partial_path = ''
        # We start from the second element because we do not want to inclued the
        # initial empty string before the first "/" because all paths begin with
        #"/". We also don't want to include the final node because that is dealt
        # with later.
        for path_part in path.split("/")[1:-1]:
            partial_path = partial_path + "/" + path_part
            if zookeeper.exists(self.handle, partial_path) == None:
                zookeeper.create(self.handle, partial_path, '', [self.acl], 0)
        
        if zookeeper.exists(self.handle, path):
            zookeeper.set(self.handle, path, contents)
        else:
            zookeeper.create(self.handle, path, contents, [self.acl], 0)

    def read(self, path, default=None):
        """
        Returns the conents in the path. default is returned if the path does not exists.
        """
        value = default
        if zookeeper.exists(self.handle, path):
            value, timeinfo = zookeeper.get(self.handle, path)
        
        return value
    def list_children(self, path):
        """
        Returns a list of all the children nodes in the path. None is returned if the path does
        not exist.
        """
        if zookeeper.exists(self.handle, path):
            value = zookeeper.get_children(self.handle, path)
            return value

    def delete(self, path):
        """
        Delete the path.
        """
        if zookeeper.exists(self.handle, path):
            path_children = zookeeper.get_children(self.handle, path)
            for child in path_children:
                self.delete(path + "/" + child)
                
            zookeeper.delete(self.handle, path)

    def watch_contents(self, path, fn):
        if not zookeeper.exists(self.handle, path):
            self.write(path, "")
        
        self.watches[path] = [fn] + self.watches.get(path, [])
        value, timeinfo = zookeeper.get(self.handle, path, self.zookeeper_watch)

    def watch_children(self, path, fn):
        if not zookeeper.exists(self.handle, path):
            self.write(path, "")
        
        self.watches[path] = [fn] + self.watches.get(path, [])
        return zookeeper.get_children(self.handle, path, self.zookeeper_watch)

    def zookeeper_watch(self, zh, event, state, path):
        fns = self.watches.get(path, None)
        if fns:
            result = None
            if event == ZOO_EVENT_NODE_CHILDREN_CHANGED:
                result = zookeeper.get_children(self.handle, path, self.zookeeper_watch)
            elif event == ZOO_EVENT_NODE_DATA_CHANGED:
                result, _ = zookeeper.get(self.handle, path, self.zookeeper_watch)

            if result != None:
                for fn in fns:
                    fn(result)

# Save the exception for use in other modules.
ZookeeperException = zookeeper.ZooKeeperException
