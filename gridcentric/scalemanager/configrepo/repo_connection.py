
import os

def get_connection(url):
    from gridcentric.scalemanager.configrepo.git_connection import GitConnection
    return GitConnection(url) 


class ConfigRepoConnection():
    
    def __init__(self, url):
        self.url = url
        self.path = None
    
    def get_copy(self, path):
        self.path = path
        self._get_copy()
    
    def update(self):
        self._update()
    
    def get_file_path(self, file_path):
        """ 
        Returns the file from the repo with the file path based from the
        root of the repo.
        """
        return os.path.join(self._get_repo_path(), file_path)
    
    def _get_copy(self):
        """ Get a copy of the config repo, if it doesn't already exist. """
        pass
    
    def _update(self):
        """ Update the working copy of the config repo. """
        pass
    
    def _get_repo_path(self):
        return self.path