import uuid
import hashlib
import sys

def import_class(import_str):
    module_str, _, class_str = import_str.rpartition('.')
    try:
        __import__(module_str)
        return getattr(sys.modules[module_str], class_str)
    except (ImportError, ValueError, AttributeError), _:
        raise ImportError("Class %s can not be found." %
                          (import_str,))

def sha_hash(input_str):
    hash_fn = hashlib.new('sha1')
    hash_fn.update(input_str)
    return hash_fn.hexdigest()

def random_key():
    return sha_hash(str(uuid.uuid4()))
