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

import sys
import unittest

import reactor.endpoint as endpoint

def test_single_manager(endpoint, manager):
    assert manager.endpoint_owned(endpoint)

def test_multiple_managers(endpoint, managers):
    assert len(managers) > 1
    owners = [m for m in managers if m.endpoint_owned(endpoint)]
    assert len(owners) == 1
