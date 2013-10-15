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

import uuid
import hashlib
import traceback
import sys

def import_class(import_str):
    module_str, _, class_str = import_str.rpartition('.')
    try:
        __import__(module_str)
        return getattr(sys.modules[module_str], class_str)
    except (ImportError, ValueError, AttributeError), _:
        traceback.print_exc()
        raise ImportError("Class %s can not be loaded." %
                          (import_str,))

def sha_hash(input_str):
    hash_fn = hashlib.new('sha1')
    hash_fn.update(input_str)
    return hash_fn.hexdigest()

def random_key():
    return sha_hash(str(uuid.uuid4()))
