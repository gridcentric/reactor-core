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

"""
A simple module used to configure the logger for the reactor project.
"""

import logging
import logging.handlers
import sys

def configure(level, logfile=None):

    logger = logging.getLogger()
    logger.setLevel(level=level)

    # Clear out old handlers.
    for handler in logger.handlers:
        logger.removeHandler(handler)

    # Add ourselves.
    if logfile != None:
        handler = logging.handlers.WatchedFileHandler(logfile)
    else:
        handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter('%(asctime)s [%(thread)d] %(levelname)s %(name)s: %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

def log(fn):
    def _sanitize(arg):
        try:
            strval = str(arg)
        except TypeError:
            return "???"
        if strval.find("\n") >= 0:
            return "..."
        elif len(strval) > 80:
            return strval[:70] + "..."
        else:
            return strval

    def _log_fn(*args, **kwargs):
        argfmt = []
        argfmt.extend(map(_sanitize, args))
        argfmt.extend(map(lambda (x, y): "%s=%s" % (x, _sanitize(y)), kwargs.items()))
        rv = fn(*args, **kwargs)
        logging.debug("%s::%s(%s) -> %s",
            fn.__module__,
            fn.__name__,
            ",".join(argfmt), _sanitize(rv))
        return rv
    _log_fn.__name__ = fn.__name__
    _log_fn.__doc__ = fn.__doc__
    return _log_fn
