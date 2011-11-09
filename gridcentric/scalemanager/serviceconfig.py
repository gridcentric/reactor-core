
import ConfigParser
from exceptions import ConfigFileNotFound

class ServiceConfig(object):
    
    CONF_FILE='service.conf'
    CONF_SECTION='service'
    
    def __init__(self, path):
        self.path = path
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
    
    def listen(self, id, fn):
        self.listeners[id] = fn
    
    def load(self):
        self.config = ConfigParser.SafeConfigParser()
        config_filename = '%s/%s' % (self.path, self.CONF_FILE)
        try:
            config_file = file(config_filename, 'r')
        except:
            # The configuration file does not exist.
            raise ConfigFileNotFound(config_filename)
        
        self.config.readfp(config_file)
        
        # Notify the listeners that we have loaded 
        for fn in self.listeners.values():
            fn()