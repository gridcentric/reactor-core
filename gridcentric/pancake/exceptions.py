"""
Exceptions used throughout the ScaleManager
"""

class ScaleManagerException(Exception):
    
    def __init__(self, message, details=None):
        self.message = message
        self.details = details
        
    def __str__(self):
        if self.details:
            return "%s: %s (%s)" %( self.__class__.__name__, self.message, self.details )
        else:
            return "%s: %s" %( self.__class__.__name__, self.message)

class ConfigFileNotFound(ScaleManagerException):
    pass
