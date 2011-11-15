
import ConfigParser

from gridcentric.scalemanager.exceptions import ConfigFileNotFound
import gridcentric.scalemanager.configrepo.repo_connection as repo_connection

class ServiceConfig(object):
    
    CONF_FILE='service.conf'
    CONF_SECTION='service'
    
    def __init__(self, url, working_dir):
        self.repo_connection = repo_connection.get_connection(url)
        self.working_dir = working_dir
        self.config = None
        self.listeners = {}
    
    def __getattr__(self, attr):
        result = None
        if attr[0] != '_':
            try:
                result = self.config.get(self.CONF_SECTION, attr)
            except:
                pass
            
        if result == None:
            result = object.__getattribute__(self, attr)
        return result

    def load(self):
        
        self.repo_connection.get_copy(self.working_dir)
        self.repo_connection.update()
        
        self.config = ConfigParser.SafeConfigParser()
        config_filename = self.repo_connection.get_file_path(self.CONF_FILE)
        config_file = None
        try:
            config_file = file(config_filename, 'r')
            self.config.readfp(config_file)
        except:
            # The configuration file does not exist.
            raise ConfigFileNotFound(config_filename)
        finally:
            if config_file:
                config_file.close()
        
        self.notify()
    
    def listen(self, id, fn):
        self.listeners[id] = fn
        
    def notify(self):
        # Notify the listeners that we have loaded 
        for fn in self.listeners.values():
            fn()