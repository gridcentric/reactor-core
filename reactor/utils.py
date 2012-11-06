import sys

def import_class(import_str):
    module_str, _, class_str = import_str.rpartition('.')
    try:
        __import__(module_str)
        return getattr(sys.modules[module_str], class_str)
    except (ImportError, ValueError, AttributeError), e:
        raise ImportError("Class %s can not be found." % (import_str))
