
import ConfigParser
from StringIO import StringIO

from gridcentric.scalemanager.exceptions import ConfigFileNotFound
import gridcentric.scalemanager.configrepo.repo_connection as repo_connection

class Config(object):
    
    def __init__(self, conf_section, defaultcfg = None):
        self.defaultcfg = defaultcfg
        self.conf_section = conf_section
        self.config = None
    
    def __getattr__(self, attr):
        result = None
        if attr[0] != '_':
            try:
                result = self.config.get(self.conf_section, attr)
            except:
                pass
            
        if result == None:
            result = object.__getattribute__(self, attr)
        return result
    
    def load(self, config_str):
        if config_str != None:
            self.config = ConfigParser.SafeConfigParser()
            if self.defaultcfg != None:
                self.config.readfp(self.defaultcfg)
            self.config.readfp(StringIO(config_str))

class ManagerConfig(Config):
        
    def __init__(self, config_str):
        super(ManagerConfig, self).__init__("manager", StringIO("""
        [manager]
        health_check=60
        """))
        
        self.load(config_str)
    
    def toStr(self, config_str):
        pass


class ServiceConfig(Config):
    
    def __init__(self, config_str):
        super(ServiceConfig, self).__init__("service")
        self.load(config_str)
        
    def reload(self, config_str):
        if self.config == None:
            self.load(config_str)
        else:
            self.config.readfp(StringIO(config_str))
        