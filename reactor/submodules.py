import os
import logging

import reactor.loadbalancer.connection as loadbalancer
import reactor.cloud.connection as cloud

def loadbalancer_submodules():
    return _discover_submodules(loadbalancer)

def cloud_submodules():
    return _discover_submodules(cloud)

def _discover_submodules(mod):
    discovered = []
    path = os.path.dirname(mod.__file__)
    for name in os.listdir(path):
        try:
            # Check if it's a directory, and we can
            # successfully perform get_connection().
            if os.path.isdir(os.path.join(path, name)):
                mod.get_connection(name)
                discovered.append(name)
        except:
            import traceback
            logging.debug("Unable to load module %s: %s" % (name, traceback.format_exc()))
            continue
    return discovered

# We should really be querying the scale manager for the list
# of enabled cloud and loadbalancer submodules, but the current
# architecture does not easily allow for that.
def cloud_options():
    options = []
    modules = cloud_submodules()
    for name in modules:
        desc = cloud.get_connection(name).description()
        options.append((desc, name))
    return options

def loadbalancer_options():
    options = []
    modules = loadbalancer_submodules()
    for name in modules:
        desc = loadbalancer.get_connection(name).description()
        options.append((desc, name))
    return options
