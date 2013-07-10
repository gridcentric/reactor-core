import struct
import time

# Implements a binary logging class
class BinaryLogRecord:
    def __init__(self, printfn=lambda args: "No information (%d, %d)" % (args[0], args[1])):
        self.printfn = printfn

# Records are stored as an array of structs:
#   f64 time
#   u16 severity
#   u16 record type
#   u32 arg1
#   u32 arg2
STRUCT_FMT = '<dHHLL'
STRUCT_SIZE = struct.calcsize(STRUCT_FMT)

class BinaryLog:
    # Severeties
    INFO, WARN, ERROR = range(3)
    SEVERITY_MAP = {
            INFO    : "INFO",
            WARN    : "WARNING",
            ERROR   : "ERROR"
    }

    # Unknown Record type
    UNKNOWN_RECTYPE = BinaryLogRecord(lambda args: "Unknown log entry (args %d, %d)" % (args[0], args[1]))

    def __init__(self, size, record_types=None,
                 store_cb=None, retrieve_cb=None):
        self.size = size
        self.num_entries = self.size / STRUCT_SIZE
        self.type_list = []
        self.type_map = {}
        if record_types:
            self.add_record_types(record_types)
        self.store_cb = store_cb
        self.retrieve_cb = retrieve_cb
        self.data = None
        self.buffer = None
        self.pointer = 0
        self.reload()

    # Add a single new record type
    def add_record_type(self, record_type):
        self.type_list.append(record_type)
        self.type_map[record_type] = len(self.type_list)

    # Add a list of record types
    def add_record_types(self, record_types):
        # Append record types to our internal list,
        # and add them to a type->int map (1-based).
        for t in record_types:
            self.add_record_type(t)

    def reload(self):
        if self.retrieve_cb:
            self.data = self.retrieve_cb()
        if not self.data or len(self.data) != self.size:
            self.data = bytearray(self.size)
        self.buffer = buffer(self.data)
        self.find_pointer()

    def extract_entry(self, index):
        return struct.unpack_from(STRUCT_FMT, self.buffer, index * STRUCT_SIZE)

    def create_entry(self, index, ts, sev, code, arg1, arg2):
        struct.pack_into(STRUCT_FMT, self.data, index * STRUCT_SIZE,
                        ts, sev, code, arg1, arg2)

    def find_pointer(self):
        max_ts = 0
        max_ts_ent = 0
        # Look for the latest non-null entry
        for i in range(self.num_entries):
            (ts, sev, code, arg1, arg2) = self.extract_entry(i)
            if ts > max_ts:
                max_ts = ts
                max_ts_ent = i

        # If we found an entry:
        if max_ts > 0:
            # Use the following slot as the write pointer
            self.pointer = max_ts_ent
            self.pointer = self.next_pointer(self.pointer)
        # Else,
        else:
            # Start at zero.
            self.pointer = 0

    def next_pointer(self, current):
        current += 1
        if current >= self.num_entries:
            current = 0
        return current

    def prev_pointer(self, current):
        current -= 1
        if current < 0:
            current  = self.num_entries - 1
        return current

    def log_raw(self, sev, code, *args):
        # Gather entry fields
        ts = time.time()
        arg1 = len(args) >= 1 and args[0] or 0
        arg2 = len(args) >= 2 and args[1] or 0

        # Write entry
        self.create_entry(self.pointer, ts, sev, code, arg1, arg2)

        # Advance pointer
        self.pointer = self.next_pointer(self.pointer)

        # Store log
        if self.store_cb:
            self.store_cb(self.data)

    def log(self, sev, rectype, *args):
        # Get code for rectype (or throw exception)
        code = self.type_map[rectype]
        # Log raw entry
        return self.log_raw(sev, code, *args)

    def info(self, rectype, *args):
        self.log(self.INFO, rectype, *args)

    def warn(self, rectype, *args):
        self.log(self.WARN, rectype, *args)

    def error(self, rectype, *args):
        self.log(self.ERROR, rectype, *args)

    def get_raw(self, since=None, num=None):
        entries = []

        # If starting point is unspecified, return
        # all since the beginning of time
        if not(since):
            since = 0.0

        # If limit is unspecified, return all
        # available entries
        if not(num):
            num = self.size / STRUCT_SIZE

        # Return entries, in chronological order, starting
        # from the slot after the last written entry
        pointer = self.pointer
        orig_pointer = pointer
        # Pull the requested amount:
        while len(entries) < num:
            # Extract an entry
            (ts, sev, code, arg1, arg2) = self.extract_entry(pointer)
            # If it's non-null and after the requested timestamp,
            if code != 0 and ts > since:
                # Save it
                entries.append((ts, sev, code, arg1, arg2))

            # Advance the pointer
            pointer = self.next_pointer(pointer)

            # Quit if we've looped around the log
            if pointer == orig_pointer:
                break

        return entries

    def pretty_print_entry(self, entry):
        (ts, sev, code, arg1, arg2) = entry
        # Get original record type
        if code > 0 and code <= len(self.type_list):
            rectype = self.type_list[code-1]
        else:
            rectype = self.UNKNOWN_RECTYPE

        # Format severity string
        sevstr = "%s" % self.SEVERITY_MAP[sev]

        # Format entry string
        recstr = rectype.printfn((arg1, arg2))

        # Form new entry, pretty printed
        return [ts, sevstr, recstr]

    def get(self, since=None, num=None):
        # Get raw entries
        raw_entries = self.get_raw(since, num)

        # Convert to human readable entries
        entries = map(self.pretty_print_entry, raw_entries)

        # Return pretty-printed list
        return entries
