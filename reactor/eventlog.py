import time

class Event(object):

    """ Implements a log event. """

    def __init__(self, formatfn=lambda args: "Unknown event."):
        self._formatfn = formatfn

    @property
    def formatfn(self):
        return self._formatfn

class EventLog(object):

    # Severeties.
    INFO, WARN, ERROR = range(3)
    SEVERITY_MAP = {
        INFO: "INFO",
        WARN: "WARNING",
        ERROR: "ERROR"
    }

    # Default event.
    UNKNOWN_EVENT = Event()

    def __init__(self, zkobj, size=None):
        self.zkobj = zkobj
        self.size = size and int(size)
        self.type_rmap = {}
        self.type_map = {}

        # Enumerate all known events for this class.
        for k in dir(self):
            v = getattr(self, k)
            if isinstance(v, Event):
                self.type_map[k] = v
                self.type_rmap[v] = k

    def _log(self, sev, event, *args):
        # Get the event type.
        # NOTE: This will throw an exception if not available.
        code = self.type_rmap[event]

        # Log raw entry (note this is the only time we limit the log).
        self.zkobj.add((time.time(), sev, code, args), limit=self.size)

    def info(self, event, *args):
        self._log(self.INFO, event, *args)

    def warn(self, event, *args):
        self._log(self.WARN, event, *args)

    def error(self, event, *args):
        self._log(self.ERROR, event, *args)

    def _format_entry(self, entry):
        (ts, sev, code, args) = entry

        # Get the original event type.
        event = self.type_map.get(code, self.UNKNOWN_EVENT)

        # Format severity string.
        sevstr = self.SEVERITY_MAP.get(sev, "???")

        # Format entry string.
        try:
            prettystr = event.formatfn(args)
        except Exception, e:
            prettystr = "Failed to format event: %s" % str(e)

        # Form new entry, pretty printed.
        return [ts, sevstr, prettystr]

    def get(self, since=None, num=None):
        # Get raw entries.
        raw_entries = self.zkobj.entries(since=since, limit=num)

        # Convert to human readable entries.
        entries = map(self._format_entry, raw_entries)

        # Return pretty-printed list.
        return entries
