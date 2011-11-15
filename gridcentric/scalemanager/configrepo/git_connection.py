import logging
import os

from dulwich.client import get_transport_and_path
from dulwich.repo import Repo

from gridcentric.scalemanager.configrepo.repo_connection import ConfigRepoConnection 

class GitConnection(ConfigRepoConnection):
    
    def _get_copy(self):
        """ Get a copy of the config repo, if it doesn't already exist. """
        self.client, self.host_path = get_transport_and_path(self.url)
        try:
            os.mkdir(self.path)
            self.repo = Repo.init(self.path)
        except Exception, e:
            logging.warn("The config repo %s already exists and will not be recreated. (%s)" % (self.path, e))
            self.repo = Repo(self.path)
        
    
    def _update(self):
        """ Update the working copy of the config repo. """
        logging.info("Updating config repo at %s" % (self.path))
        remote_refs = self.client.fetch(self.host_path, self.repo, determine_wants=self.repo.object_store.determine_wants_all)
        self.repo["HEAD"] = remote_refs["HEAD"] 
        
        # Write out the contents
        #get tree corresponding to the head commit
        tree_id = self.repo["HEAD"].tree
        #iterate over tree content, giving path and blob sha.
        for entry in self.repo.object_store.iter_tree_contents(tree_id):
            with open(self.get_file_path(entry.path), 'wb') as file:
                #write blob's content to file
                file.write(self.repo.get_object(entry.sha).as_raw_string())
                file.flush()
                file.close() 
