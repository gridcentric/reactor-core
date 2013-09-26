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
