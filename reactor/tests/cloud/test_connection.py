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

import unittest

from reactor.cloud.connection import get_connection
from reactor.cloud.connection import CloudConnection
from reactor.cloud.mock.connection import Connection

class GetConnectionTests(unittest.TestCase):

    def test_get_connection_none(self):
        assert isinstance(get_connection(None), CloudConnection)

    def test_get_connection_empty_str(self):
        assert isinstance(get_connection(""), CloudConnection)

    def test_get_connection_invalid(self):
        self.assertRaises(ImportError, get_connection, "invalid")

    def test_get_connection_mock(self):
        assert isinstance(get_connection("mock"), Connection)
