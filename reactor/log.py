"""
A simple module used to configure the logger for the reactor project.
"""

import logging
import logging.handlers
import sys

def configure(level, logfile=None):

    if logfile != None:
        handler = logging.handlers.WatchedFileHandler(logfile)
    else:
        handler = logging.StreamHandler(sys.stdout)

    formatter = logging.Formatter('%(asctime)s [%(thread)d] %(levelname)s %(name)s: %(message)s')
    handler.setFormatter(formatter) 

    logger = logging.getLogger()
    logger.setLevel(level=level)
    logger.addHandler(handler)

def log(fn):
    def _sanitize(arg):
        strval = str(arg)
        if strval.find("\n") >= 0:
            return "..."
        elif len(strval) > 64:
            return strval[:13] + "..."
        else:
            return strval

    def _log_fn(*args, **kwargs):
        argfmt = []
        argfmt.extend(map(_sanitize, args))
        argfmt.extend(map(lambda x, y: "%s=%s" % (x, _sanitize(y)), kwargs.items()))
        rv = fn(*args, **kwargs)
        logging.debug("%s::%s(%s) -> %s", fn.__module__, fn.__name__, ",".join(argfmt), _sanitize(rv))
        return rv
    _log_fn.__name__ = fn.__name__
    _log_fn.__doc__ = fn.__doc__
    return _log_fn
