
import zookeeper

ZOO_OPEN_ACL_UNSAFE = {"perms":0x1f, "scheme":"world", "id":"anyone"}
class ZookeeperConnection(object):
    
    def __init__(self, servers, acl=ZOO_OPEN_ACL_UNSAFE):
        self.handle = zookeeper.init(servers)
        self.acl = acl
    
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

    def read(self, path):
        """
        Returns the conents in the path. None is returned if the path does not exists.
        """
        if zookeeper.exists(self.handle, path):
            value, timeinfo = zookeeper.get(self.handle, path)
            return value
    
    def delete(self, path):
        """
        Delete the path.
        """
        if zookeeper.exists(self.handle, path):
            zookeeper.delete(self.handle, path)
    
    def watch_contents(self, path, fn):
        pass
    
    def watch_children(self, path, fn):
        pass