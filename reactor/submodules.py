# Copyright 2013 GridCentric Inc.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import os
import logging

import reactor.loadbalancer.connection as loadbalancer
import reactor.cloud.connection as cloud

def _discover_submodules(mod, connection_fn, all=False):
    discovered = [""] # Include the base class.
    path = os.path.dirname(mod.__file__)
    for name in os.listdir(path):
        try:
            # Check if it's a directory, and we can
            # successfully perform get_connection().
            if os.path.isdir(os.path.join(path, name)):
                if not all:
                    # Ensure it's importable.
                    connection_fn(name)
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
def cloud_submodules(all=False):
    return _discover_submodules(cloud, cloud.get_connection, all=all)

def loadbalancer_submodules(all=False):
    return _discover_submodules(loadbalancer, loadbalancer.get_connection, all=all)

def cloud_options():
    return _build_options(cloud_submodules(all=True), cloud.get_connection)

def loadbalancer_options():
    return _build_options(loadbalancer_submodules(all=True), loadbalancer.get_connection)
