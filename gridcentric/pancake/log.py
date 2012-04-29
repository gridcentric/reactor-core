"""
A simple module used to configure the logger for the pancake project.
"""

import logging
import logging.handlers
import sys

def configure(level, logfile=None):
    
    hanlder = None
    if logfile != None:
        handler = logging.handlers.WatchedFileHandler(logfile)
    else:
        handler = logging.StreamHandler(sys.stdout)
        
    formatter = logging.Formatter('%(asctime)s [%(thread)d] %(levelname)s %(name)s: %(message)s')
    handler.setFormatter(formatter) 
    
    logger = logging.getLogger()
    logger.setLevel(level=level)
    logger.addHandler(handler)
