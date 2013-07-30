import os
import logging

import reactor.loadbalancer.connection as loadbalancer
import reactor.cloud.connection as cloud

def _discover_submodules(mod):
    discovered = [""] # Include the base class.
    path = os.path.dirname(mod.__file__)
    for name in os.listdir(path):
        try:
            # Check if it's a directory, and we can
            # successfully perform get_connection().
            if os.path.isdir(os.path.join(path, name)):
                discovered.append(name)
        except Exception:
            import traceback
            logging.debug("Unable to load module %s: %s",
                          name, traceback.format_exc())
            continue
    return discovered

def _build_options(mods, connection_fn):
    options = []
    for mod in mods:
        try:
            # NOTE: The below line may roll an exception,
            # because __doc__ is None on the class. If this is
            # the case, it will be caught below and an empty
            # description appended.
            desc = connection_fn(mod).__doc__.split("\n")[0]
            options.append((desc, mod))
        except Exception:
            logging.error("Module %s is missing docstring!", mod)
            options.append((mod, mod))
    return options

# We should really be querying the scale manager for the list
# of enabled cloud and loadbalancer submodules, but the current
# architecture does not easily allow for that.
def cloud_submodules():
    return _discover_submodules(cloud)

def loadbalancer_submodules():
    return _discover_submodules(loadbalancer)

def cloud_options():
    return _build_options(cloud_submodules(), cloud.get_connection)

def loadbalancer_options():
    return _build_options(loadbalancer_submodules(), loadbalancer.get_connection)
