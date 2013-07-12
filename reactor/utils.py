import sys
import socket
import struct

def import_class(import_str):
    module_str, _, class_str = import_str.rpartition('.')
    try:
        __import__(module_str)
        return getattr(sys.modules[module_str], class_str)
    except (ImportError, ValueError, AttributeError), e:
        raise ImportError("Class %s can not be found." % (import_str))

def inet_ntoa(num):
    return socket.inet_ntoa(struct.pack("!I", num))

def inet_aton(s):
    return struct.unpack("!I", socket.inet_aton(s))[0]
