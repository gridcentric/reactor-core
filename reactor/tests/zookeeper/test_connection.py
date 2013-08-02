import sys
import thread
import unittest
import mock

# NOTE: We import zookeeper here, but it's going
# to be the mock zookeeper supplied by the tests.
import zookeeper

# We import the connection module with the "real"
# zookeeper above. However, prior to running tests,
# we will reload the module and ensure that it is
# using our mocked module.
import reactor.zookeeper.connection as connection

# Patch zookeeper
class FakeZookeeperException(Exception):
    pass

class FakeBadArgumentsException(FakeZookeeperException):
    pass

class FakeNodeExistsException(FakeZookeeperException):
    pass

class FakeNoNodeException(FakeZookeeperException):
    pass

mock_zookeeper_mod = mock.Mock(name="zookeeper")
mock_zookeeper_mod.CONNECTED_STATE = 3
mock_zookeeper_mod.INVALIDSTATE = -9
mock_zookeeper_mod.EPHEMERAL = zookeeper.EPHEMERAL
mock_zookeeper_mod.SEQUENCE = zookeeper.SEQUENCE
mock_zookeeper_mod.ZooKeeperException  = FakeZookeeperException
mock_zookeeper_mod.BadArgumentsException = FakeBadArgumentsException
mock_zookeeper_mod.NodeExistsException = FakeNodeExistsException
mock_zookeeper_mod.NoNodeException = FakeNoNodeException

# Fake data
FAKE_ZK_HANDLE = 0x5a5a5a5a
FAKE_SERVERS = ["fakehost1", "fakehost2:9000"]
FAKE_SERVER_STRING = "fakehost1:2181,fakehost2:9000"
FAKE_ZK_PATH = "/fake"
FAKE_ZK_CONTENTS = "fakefake"
FAKE_ZK_CHILDREN = ["foo", "bar"]
GARBAGE = "garbage"
LOCK_ARGS = { "ephemeral" : True, "exclusive" : True }

# Mock methods
def mock_zookeeper_init(connect_success=True, throw_exception=None):
    def _zookeeper_init(servers, cb, timeout):
        def _cb_thread():
            if connect_success:
                cb(FAKE_ZK_HANDLE, None,
                   mock_zookeeper_mod.CONNECTED_STATE, None)
            else:
                cb(FAKE_ZK_HANDLE, None,
                   mock_zookeeper_mod.INVALID_STATE, None)

        if throw_exception:
            raise throw_exception()
        else:
            thread.start_new_thread(_cb_thread, ())
        return FAKE_ZK_HANDLE

    return _zookeeper_init

def mock_zookeeper_create(throw_exception=None, num_exceptions=-1):
    call_counter = [0]
    def _zookeeper_create(*args, **kwargs):
        if throw_exception:
            call_counter[0] = call_counter[0] + 1
            if num_exceptions == -1 or call_counter[0] <= num_exceptions:
                raise throw_exception()
        return args[1]

    return _zookeeper_create

class ConnectionTests(unittest.TestCase):

    def setUp(self):
        sys.modules["zookeeper"] = mock_zookeeper_mod
        reload(connection)

    def tearDown(self):
        sys.modules["zookeeper"] = zookeeper
        reload(connection)

    def test_connect_with_bad_server_arg(self):
        with mock.patch("zookeeper.init") as mock_init:
            mock_init.side_effect = mock_zookeeper_init()
            with self.assertRaises(FakeBadArgumentsException):
                connection.connect(None)
            with self.assertRaises(FakeBadArgumentsException):
                connection.connect([])
            with self.assertRaises(FakeBadArgumentsException):
                connection.connect("Blah blah")

    def test_connect_handles_exceptions(self):
        with mock.patch("zookeeper.init") as mock_init:
            mock_init.side_effect = mock_zookeeper_init(\
                                        throw_exception=Exception)
            with self.assertRaises(FakeZookeeperException):
                connection.connect(FAKE_SERVERS)

    def test_connect_handles_connection_timeout(self):
        with mock.patch("zookeeper.init") as mock_init:
            mock_init.side_effect = mock_zookeeper_init(\
                                        connect_success=False)
            with self.assertRaises(FakeZookeeperException):
                connection.connect(FAKE_SERVERS, timeout=1)

    def test_connect_success(self):
        with mock.patch("zookeeper.init") as mock_init:
            mock_init.side_effect = mock_zookeeper_init()
            handle = connection.connect(FAKE_SERVERS)
            self.assertEquals(handle, FAKE_ZK_HANDLE)
            self.assertEquals(mock_init.call_count, 1)
            self.assertEquals(mock_init.call_args_list[0][0][0], FAKE_SERVER_STRING)

    def test_constructor_with_bad_server_arg(self):
        with mock.patch("zookeeper.init") as mock_init:
            mock_init.side_effect = mock_zookeeper_init()
            with self.assertRaises(FakeZookeeperException):
                connection.ZookeeperConnection(None)
            with self.assertRaises(FakeZookeeperException):
                connection.ZookeeperConnection([])
            with self.assertRaises(FakeZookeeperException):
                connection.ZookeeperConnection("Blah blah")

    def test_constructor_success(self):
        with mock.patch("zookeeper.init") as mock_init:
            mock_init.side_effect = mock_zookeeper_init()
            conn = connection.ZookeeperConnection(FAKE_SERVERS)
            self.assertEquals(conn.handle, FAKE_ZK_HANDLE)
            self.assertEquals(mock_init.call_count, 1)
            self.assertEquals(mock_init.call_args_list[0][0][0], FAKE_SERVER_STRING)

    def test_destructor(self):
        with mock.patch("zookeeper.init") as mock_init,\
                mock.patch("reactor.zookeeper.connection.ZookeeperConnection.close") as mock_close:
            mock_init.side_effect = mock_zookeeper_init()
            conn = connection.ZookeeperConnection(FAKE_SERVERS)
            del conn
            # Assert that we called close()
            self.assertEquals(mock_close.call_count, 1)

    def test_close(self):
        with mock.patch("zookeeper.init") as mock_init,\
                mock.patch("zookeeper.close") as mock_close:
            mock_init.side_effect = mock_zookeeper_init()
            conn = connection.ZookeeperConnection(FAKE_SERVERS)
            conn.close()
            self.assertEquals(mock_close.call_count, 1)
            self.assertEquals(mock_close.call_args_list[0][0][0], FAKE_ZK_HANDLE)

    def test_write_with_bad_args(self):
        with mock.patch("zookeeper.init") as mock_init:
            mock_init.side_effect = mock_zookeeper_init()
            conn = connection.ZookeeperConnection(FAKE_SERVERS)
            with self.assertRaises(FakeBadArgumentsException):
                conn.write(FAKE_ZK_PATH, None)
            with self.assertRaises(FakeBadArgumentsException):
                conn.write(None, FAKE_ZK_CONTENTS)

    def test_write_new_path(self):
        with mock.patch("zookeeper.init") as mock_init,\
                mock.patch("zookeeper.exists") as mock_exists,\
                mock.patch("zookeeper.create") as mock_create,\
                mock.patch("zookeeper.delete") as mock_delete,\
                mock.patch("zookeeper.set") as mock_set:
            mock_init.side_effect = mock_zookeeper_init()
            conn = connection.ZookeeperConnection(FAKE_SERVERS)
            mock_exists.return_value = False
            written = conn.write(FAKE_ZK_PATH, FAKE_ZK_CONTENTS, ephemeral=False, exclusive=False)
            self.assertTrue(written)
            # Make sure create got called correctly
            self.assertEquals(mock_create.call_count, 1)
            self.assertEquals(mock_create.call_args_list[0][0], (FAKE_ZK_HANDLE, FAKE_ZK_PATH, FAKE_ZK_CONTENTS, [conn.acl], 0))
            # Make sure nothing else got called
            self.assertEquals(mock_delete.call_count, 0)
            self.assertEquals(mock_set.call_count, 0)
        with mock.patch("zookeeper.init") as mock_init,\
                mock.patch("zookeeper.exists") as mock_exists,\
                mock.patch("zookeeper.create") as mock_create,\
                mock.patch("zookeeper.delete") as mock_delete,\
                mock.patch("zookeeper.set") as mock_set:
            mock_init.side_effect = mock_zookeeper_init()
            conn = connection.ZookeeperConnection(FAKE_SERVERS)
            mock_exists.return_value = False
            written = conn.write(FAKE_ZK_PATH, FAKE_ZK_CONTENTS, ephemeral=True, exclusive=True)
            self.assertTrue(written)
            # Make sure create got called correctly
            self.assertEquals(mock_create.call_count, 1)
            self.assertEquals(mock_create.call_args_list[0][0],
                    (FAKE_ZK_HANDLE, FAKE_ZK_PATH, FAKE_ZK_CONTENTS, [conn.acl], mock_zookeeper_mod.EPHEMERAL))
            # Make sure nothing else got called
            self.assertEquals(mock_delete.call_count, 0)
            self.assertEquals(mock_set.call_count, 0)

    def test_write_existing_path(self):
        with mock.patch("zookeeper.init") as mock_init,\
                mock.patch("zookeeper.exists") as mock_exists,\
                mock.patch("zookeeper.create") as mock_create,\
                mock.patch("zookeeper.delete") as mock_delete,\
                mock.patch("zookeeper.set") as mock_set:
            mock_init.side_effect = mock_zookeeper_init()
            conn = connection.ZookeeperConnection(FAKE_SERVERS)
            mock_exists.return_value = True
            written = conn.write(FAKE_ZK_PATH, FAKE_ZK_CONTENTS, ephemeral=False, exclusive=False)
            self.assertTrue(written)
            # Make sure set got called correctly
            self.assertEquals(mock_set.call_count, 1)
            self.assertEquals(mock_set.call_args_list[0][0], (FAKE_ZK_HANDLE, FAKE_ZK_PATH, FAKE_ZK_CONTENTS))
            # Make sure nothing else got called
            self.assertEquals(mock_create.call_count, 0)
            self.assertEquals(mock_delete.call_count, 0)

    def test_write_existing_path_exclusive(self):
        with mock.patch("zookeeper.init") as mock_init,\
                mock.patch("zookeeper.exists") as mock_exists,\
                mock.patch("zookeeper.create") as mock_create,\
                mock.patch("zookeeper.delete") as mock_delete,\
                mock.patch("zookeeper.set") as mock_set:
            mock_init.side_effect = mock_zookeeper_init()
            conn = connection.ZookeeperConnection(FAKE_SERVERS)
            mock_exists.return_value = True
            written = conn.write(FAKE_ZK_PATH, FAKE_ZK_CONTENTS, ephemeral=False, exclusive=True)
            self.assertFalse(written)
            # Make sure nothing got called
            self.assertEquals(mock_set.call_count, 0)
            self.assertEquals(mock_create.call_count, 0)
            self.assertEquals(mock_delete.call_count, 0)

    def test_write_existing_path_ephemeral(self):
        with mock.patch("zookeeper.init") as mock_init,\
                mock.patch("zookeeper.exists") as mock_exists,\
                mock.patch("zookeeper.create") as mock_create,\
                mock.patch("zookeeper.delete") as mock_delete,\
                mock.patch("zookeeper.set") as mock_set:
            mock_init.side_effect = mock_zookeeper_init()
            conn = connection.ZookeeperConnection(FAKE_SERVERS)
            mock_exists.return_value = True
            written = conn.write(FAKE_ZK_PATH, FAKE_ZK_CONTENTS, ephemeral=True, exclusive=False)
            self.assertTrue(written)
            # Make sure we re-created the node
            self.assertEquals(mock_delete.call_count, 1)
            self.assertEquals(mock_delete.call_args_list[0][0], (FAKE_ZK_HANDLE, FAKE_ZK_PATH))
            self.assertEquals(mock_create.call_count, 1)
            self.assertEquals(mock_create.call_args_list[0][0],
                    (FAKE_ZK_HANDLE, FAKE_ZK_PATH, FAKE_ZK_CONTENTS, [conn.acl], mock_zookeeper_mod.EPHEMERAL))
            self.assertEquals(mock_set.call_count, 0)

    def test_write_existing_path_ephemeral_exclusive(self):
        with mock.patch("zookeeper.init") as mock_init,\
                mock.patch("zookeeper.exists") as mock_exists,\
                mock.patch("zookeeper.create") as mock_create,\
                mock.patch("zookeeper.delete") as mock_delete,\
                mock.patch("zookeeper.set") as mock_set:
            mock_init.side_effect = mock_zookeeper_init()
            conn = connection.ZookeeperConnection(FAKE_SERVERS)
            mock_exists.return_value = True
            written = conn.write(FAKE_ZK_PATH, FAKE_ZK_CONTENTS, ephemeral=True, exclusive=True)
            self.assertFalse(written)
            # Make sure nothing got called
            self.assertEquals(mock_set.call_count, 0)
            self.assertEquals(mock_create.call_count, 0)
            self.assertEquals(mock_delete.call_count, 0)

    def test_write_existing_path_ephemeral_contentious(self):
        with mock.patch("zookeeper.init") as mock_init,\
                mock.patch("zookeeper.exists") as mock_exists,\
                mock.patch("zookeeper.create") as mock_create,\
                mock.patch("zookeeper.delete") as mock_delete,\
                mock.patch("zookeeper.set") as mock_set:
            mock_init.side_effect = mock_zookeeper_init()
            conn = connection.ZookeeperConnection(FAKE_SERVERS)
            mock_exists.return_value = True
            # Simulate lots of contention for this path by
            # thowing lots of NodeExistsExceptions, then
            # finally prevailing.
            mock_create.side_effect = mock_zookeeper_create(\
                    throw_exception=FakeNodeExistsException,
                    num_exceptions=10000)
            written = conn.write(FAKE_ZK_PATH, FAKE_ZK_CONTENTS, ephemeral=True, exclusive=False)
            self.assertTrue(written)
            # Make sure we re-created the node
            self.assertEquals(mock_delete.call_count, 10001)
            self.assertEquals(mock_delete.call_args_list[0][0], (FAKE_ZK_HANDLE, FAKE_ZK_PATH))
            self.assertEquals(mock_create.call_count, 10001)
            self.assertEquals(mock_create.call_args_list[0][0],
                    (FAKE_ZK_HANDLE, FAKE_ZK_PATH, FAKE_ZK_CONTENTS, [conn.acl], mock_zookeeper_mod.EPHEMERAL))
            self.assertEquals(mock_set.call_count, 0)

    def test_read_with_bad_args(self):
        with mock.patch("zookeeper.init") as mock_init:
            mock_init.side_effect = mock_zookeeper_init()
            conn = connection.ZookeeperConnection(FAKE_SERVERS)
            with self.assertRaises(FakeBadArgumentsException):
                conn.read(None, GARBAGE)

    def test_read_nonexistant_path(self):
        with mock.patch("zookeeper.init") as mock_init,\
                mock.patch("zookeeper.exists") as mock_exists,\
                mock.patch("zookeeper.get") as mock_get:
            mock_init.side_effect = mock_zookeeper_init()
            conn = connection.ZookeeperConnection(FAKE_SERVERS)
            mock_exists.return_value = False
            val = conn.read(FAKE_ZK_PATH, GARBAGE)
            self.assertEquals(val, GARBAGE)
            self.assertEquals(mock_exists.call_count, 1)
            self.assertEquals(mock_exists.call_args_list[0][0], (FAKE_ZK_HANDLE, FAKE_ZK_PATH))
            self.assertEquals(mock_get.call_count, 0)

    def test_read_existing_path(self):
        with mock.patch("zookeeper.init") as mock_init,\
                mock.patch("zookeeper.exists") as mock_exists,\
                mock.patch("zookeeper.get") as mock_get:
            mock_init.side_effect = mock_zookeeper_init()
            conn = connection.ZookeeperConnection(FAKE_SERVERS)
            mock_exists.return_value = True
            mock_get.return_value = (FAKE_ZK_CONTENTS, GARBAGE)
            val = conn.read(FAKE_ZK_PATH, GARBAGE)
            self.assertEquals(val, FAKE_ZK_CONTENTS)
            self.assertEquals(mock_exists.call_count, 1)
            self.assertEquals(mock_exists.call_args_list[0][0], (FAKE_ZK_HANDLE, FAKE_ZK_PATH))
            self.assertEquals(mock_get.call_count, 1)
            self.assertEquals(mock_get.call_args_list[0][0], (FAKE_ZK_HANDLE, FAKE_ZK_PATH))

    def test_read_disappearing_path(self):
        with mock.patch("zookeeper.init") as mock_init,\
                mock.patch("zookeeper.exists") as mock_exists,\
                mock.patch("zookeeper.get") as mock_get:
            mock_init.side_effect = mock_zookeeper_init()
            conn = connection.ZookeeperConnection(FAKE_SERVERS)
            mock_exists.return_value = True
            mock_get.side_effect = FakeNoNodeException()
            val = conn.read(FAKE_ZK_PATH, GARBAGE)
            self.assertEquals(val, GARBAGE)
            self.assertEquals(mock_exists.call_count, 1)
            self.assertEquals(mock_exists.call_args_list[0][0], (FAKE_ZK_HANDLE, FAKE_ZK_PATH))
            self.assertEquals(mock_get.call_count, 1)
            self.assertEquals(mock_get.call_args_list[0][0], (FAKE_ZK_HANDLE, FAKE_ZK_PATH))

    def test_list_children_with_bad_args(self):
        with mock.patch("zookeeper.init") as mock_init:
            mock_init.side_effect = mock_zookeeper_init()
            conn = connection.ZookeeperConnection(FAKE_SERVERS)
            with self.assertRaises(FakeBadArgumentsException):
                conn.list_children(None)

    def test_list_children_nonexistant_path(self):
        with mock.patch("zookeeper.init") as mock_init,\
                mock.patch("zookeeper.exists") as mock_exists,\
                mock.patch("zookeeper.get_children") as mock_get:
            mock_init.side_effect = mock_zookeeper_init()
            conn = connection.ZookeeperConnection(FAKE_SERVERS)
            mock_exists.return_value = False
            val = conn.list_children(FAKE_ZK_PATH)
            self.assertEquals(val, [])
            self.assertEquals(mock_exists.call_count, 1)
            self.assertEquals(mock_exists.call_args_list[0][0], (FAKE_ZK_HANDLE, FAKE_ZK_PATH))
            self.assertEquals(mock_get.call_count, 0)

    def test_list_children_existing_path(self):
        with mock.patch("zookeeper.init") as mock_init,\
                mock.patch("zookeeper.exists") as mock_exists,\
                mock.patch("zookeeper.get_children") as mock_get:
            mock_init.side_effect = mock_zookeeper_init()
            conn = connection.ZookeeperConnection(FAKE_SERVERS)
            mock_exists.return_value = True
            mock_get.return_value = FAKE_ZK_CHILDREN
            val = conn.list_children(FAKE_ZK_PATH)
            self.assertEquals(val, FAKE_ZK_CHILDREN)
            self.assertEquals(mock_exists.call_count, 1)
            self.assertEquals(mock_exists.call_args_list[0][0], (FAKE_ZK_HANDLE, FAKE_ZK_PATH))
            self.assertEquals(mock_get.call_count, 1)
            self.assertEquals(mock_get.call_args_list[0][0], (FAKE_ZK_HANDLE, FAKE_ZK_PATH))

    def test_list_children_disappearing_path(self):
        with mock.patch("zookeeper.init") as mock_init,\
                mock.patch("zookeeper.exists") as mock_exists,\
                mock.patch("zookeeper.get_children") as mock_get:
            mock_init.side_effect = mock_zookeeper_init()
            conn = connection.ZookeeperConnection(FAKE_SERVERS)
            mock_exists.return_value = True
            mock_get.side_effect = FakeNoNodeException()
            val = conn.list_children(FAKE_ZK_PATH)
            self.assertEquals(val, [])
            self.assertEquals(mock_exists.call_count, 1)
            self.assertEquals(mock_exists.call_args_list[0][0], (FAKE_ZK_HANDLE, FAKE_ZK_PATH))
            self.assertEquals(mock_get.call_count, 1)
            self.assertEquals(mock_get.call_args_list[0][0], (FAKE_ZK_HANDLE, FAKE_ZK_PATH))

    def test_delete_with_bad_args(self):
        with mock.patch("zookeeper.init") as mock_init:
            mock_init.side_effect = mock_zookeeper_init()
            conn = connection.ZookeeperConnection(FAKE_SERVERS)
            with self.assertRaises(FakeBadArgumentsException):
                conn.delete(None)

    def test_delete_nonexistant_path(self):
        with mock.patch("zookeeper.init") as mock_init,\
                mock.patch("zookeeper.exists") as mock_exists,\
                mock.patch("zookeeper.get_children") as mock_get,\
                mock.patch("zookeeper.delete") as mock_delete:
            mock_init.side_effect = mock_zookeeper_init()
            conn = connection.ZookeeperConnection(FAKE_SERVERS)
            mock_exists.return_value = False
            conn.delete(FAKE_ZK_PATH)
            self.assertEquals(mock_exists.call_count, 1)
            self.assertEquals(mock_exists.call_args_list[0][0], (FAKE_ZK_HANDLE, FAKE_ZK_PATH))
            self.assertEquals(mock_get.call_count, 0)
            self.assertEquals(mock_delete.call_count, 1)
            self.assertEquals(mock_delete.call_args_list[0][0], (FAKE_ZK_HANDLE, FAKE_ZK_PATH))

    def test_delete_existing_path(self):
        with mock.patch("zookeeper.init") as mock_init,\
                mock.patch("zookeeper.exists") as mock_exists,\
                mock.patch("zookeeper.get_children") as mock_get,\
                mock.patch("zookeeper.delete") as mock_delete:
            mock_init.side_effect = mock_zookeeper_init()
            conn = connection.ZookeeperConnection(FAKE_SERVERS)
            mock_exists.return_value = True
            mock_get.return_value = []
            conn.delete(FAKE_ZK_PATH)
            self.assertEquals(mock_exists.call_count, 1)
            self.assertEquals(mock_exists.call_args_list[0][0], (FAKE_ZK_HANDLE, FAKE_ZK_PATH))
            self.assertEquals(mock_get.call_count, 1)
            self.assertEquals(mock_delete.call_count, 1)
            self.assertEquals(mock_delete.call_args_list[0][0], (FAKE_ZK_HANDLE, FAKE_ZK_PATH))

    def test_delete_existing_path_with_children(self):
        with mock.patch("zookeeper.init") as mock_init,\
                mock.patch("zookeeper.exists") as mock_exists,\
                mock.patch("zookeeper.get_children") as mock_get,\
                mock.patch("zookeeper.delete") as mock_delete:
            mock_init.side_effect = mock_zookeeper_init()
            conn = connection.ZookeeperConnection(FAKE_SERVERS)
            mock_exists.return_value = True
            mock_get.side_effect = (FAKE_ZK_CHILDREN, [], [])
            conn.delete(FAKE_ZK_PATH)
            self.assertEquals(mock_delete.call_count, 1 + len(FAKE_ZK_CHILDREN))
            self.assertEquals(mock_delete.call_args_list[0][0], (FAKE_ZK_HANDLE, FAKE_ZK_PATH + "/" + FAKE_ZK_CHILDREN[0]))
            self.assertEquals(mock_delete.call_args_list[1][0], (FAKE_ZK_HANDLE, FAKE_ZK_PATH + "/" + FAKE_ZK_CHILDREN[1]))
            self.assertEquals(mock_delete.call_args_list[2][0], (FAKE_ZK_HANDLE, FAKE_ZK_PATH))

    def test_delete_disappearing_path(self):
        with mock.patch("zookeeper.init") as mock_init,\
                mock.patch("zookeeper.exists") as mock_exists,\
                mock.patch("zookeeper.get_children") as mock_get,\
                mock.patch("zookeeper.delete") as mock_delete:
            mock_init.side_effect = mock_zookeeper_init()
            conn = connection.ZookeeperConnection(FAKE_SERVERS)
            mock_exists.return_value = True
            mock_delete.side_effect = FakeNoNodeException()
            conn.delete(FAKE_ZK_PATH)
            self.assertEquals(mock_delete.call_count, 1)
            self.assertEquals(mock_delete.call_args_list[0][0], (FAKE_ZK_HANDLE, FAKE_ZK_PATH))

    def test_trylock_new_path(self):
        with mock.patch("zookeeper.init") as mock_init,\
                mock.patch("zookeeper.exists") as mock_exists,\
                mock.patch("zookeeper.create") as mock_create,\
                mock.patch("zookeeper.delete") as mock_delete,\
                mock.patch("zookeeper.set") as mock_set:
            mock_init.side_effect = mock_zookeeper_init()
            conn = connection.ZookeeperConnection(FAKE_SERVERS)
            mock_exists.return_value = False
            locked = conn.write(FAKE_ZK_PATH, FAKE_ZK_CONTENTS, **LOCK_ARGS)
            self.assertTrue(locked)
            # Make sure create got called correctly
            self.assertEquals(mock_create.call_count, 1)

    def test_trylock_existing_path(self):
        with mock.patch("zookeeper.init") as mock_init,\
                mock.patch("zookeeper.exists") as mock_exists,\
                mock.patch("zookeeper.create") as mock_create,\
                mock.patch("zookeeper.delete") as mock_delete,\
                mock.patch("zookeeper.set") as mock_set:
            mock_init.side_effect = mock_zookeeper_init()
            conn = connection.ZookeeperConnection(FAKE_SERVERS)
            mock_exists.return_value = True
            locked = conn.write(FAKE_ZK_PATH, FAKE_ZK_CONTENTS, **LOCK_ARGS)
            self.assertFalse(locked)
            # Make sure nothing got called
            self.assertEquals(mock_set.call_count, 0)
            self.assertEquals(mock_create.call_count, 0)
            self.assertEquals(mock_delete.call_count, 0)

    def test_trylock_path_contentious(self):
        with mock.patch("zookeeper.init") as mock_init,\
                mock.patch("zookeeper.exists") as mock_exists,\
                mock.patch("zookeeper.create") as mock_create,\
                mock.patch("zookeeper.delete") as mock_delete,\
                mock.patch("zookeeper.set") as mock_set:
            mock_init.side_effect = mock_zookeeper_init()
            conn = connection.ZookeeperConnection(FAKE_SERVERS)
            mock_exists.return_value = False
            # Simulate contention for this path by
            # thowing a NodeExistsException.
            mock_create.side_effect = mock_zookeeper_create(\
                    throw_exception=FakeNodeExistsException)
            locked = conn.write(FAKE_ZK_PATH, FAKE_ZK_CONTENTS, **LOCK_ARGS)
            self.assertFalse(locked)
            # Make sure nothing got called except the create
            self.assertEquals(mock_create.call_count, 1)
            self.assertEquals(mock_set.call_count, 0)
            self.assertEquals(mock_delete.call_count, 0)

    def test_watch_contents_with_bad_args(self):
        with mock.patch("zookeeper.init") as mock_init:
            mock_init.side_effect = mock_zookeeper_init()
            conn = connection.ZookeeperConnection(FAKE_SERVERS)
            mock_fn = mock.Mock()
            with self.assertRaises(FakeBadArgumentsException):
                conn.watch_contents(None, mock_fn)
            with self.assertRaises(FakeBadArgumentsException):
                conn.watch_contents(FAKE_ZK_PATH, None)

    def test_watch_contents_nonexistant_path(self):
        with mock.patch("zookeeper.init") as mock_init,\
                mock.patch("zookeeper.exists") as mock_exists,\
                mock.patch("zookeeper.create") as mock_create,\
                mock.patch("zookeeper.get") as mock_get:
            mock_init.side_effect = mock_zookeeper_init()
            conn = connection.ZookeeperConnection(FAKE_SERVERS)
            mock_exists.return_value = False
            mock_get.return_value = (FAKE_ZK_CONTENTS, GARBAGE)
            mock_fn = mock.Mock()
            val = conn.watch_contents(FAKE_ZK_PATH, mock_fn, default_value=FAKE_ZK_CONTENTS)
            self.assertEquals(val, FAKE_ZK_CONTENTS)
            self.assertTrue(mock_exists.call_count >= 1)
            self.assertEquals(mock_create.call_count, 1)
            self.assertEquals(mock_get.call_count, 1)
            self.assertIn(FAKE_ZK_PATH, conn.content_watches)
            self.assertIn(mock_fn, conn.content_watches[FAKE_ZK_PATH])

    def test_watch_contents_existing_path(self):
        with mock.patch("zookeeper.init") as mock_init,\
                mock.patch("zookeeper.exists") as mock_exists,\
                mock.patch("zookeeper.create") as mock_create,\
                mock.patch("zookeeper.get") as mock_get:
            mock_init.side_effect = mock_zookeeper_init()
            conn = connection.ZookeeperConnection(FAKE_SERVERS)
            mock_exists.return_value = True
            mock_get.return_value = (FAKE_ZK_CONTENTS, GARBAGE)
            mock_fn_old = mock.Mock()
            conn.content_watches[FAKE_ZK_PATH] = [mock_fn_old]
            mock_fn = mock.Mock()
            val = conn.watch_contents(FAKE_ZK_PATH, mock_fn, default_value=GARBAGE)
            self.assertEquals(val, FAKE_ZK_CONTENTS)
            self.assertEquals(mock_exists.call_count, 1)
            self.assertEquals(mock_create.call_count, 0)
            self.assertEquals(mock_get.call_count, 1)
            self.assertIn(FAKE_ZK_PATH, conn.content_watches)
            self.assertIn(mock_fn, conn.content_watches[FAKE_ZK_PATH])
            self.assertIn(mock_fn_old, conn.content_watches[FAKE_ZK_PATH])

    def test_watch_contents_clean_existing_path(self):
        with mock.patch("zookeeper.init") as mock_init,\
                mock.patch("zookeeper.exists") as mock_exists,\
                mock.patch("zookeeper.create") as mock_create,\
                mock.patch("zookeeper.get") as mock_get:
            mock_init.side_effect = mock_zookeeper_init()
            conn = connection.ZookeeperConnection(FAKE_SERVERS)
            mock_exists.return_value = True
            mock_get.return_value = (FAKE_ZK_CONTENTS, GARBAGE)
            mock_fn_old = mock.Mock()
            conn.content_watches[FAKE_ZK_PATH] = [mock_fn_old]
            mock_fn = mock.Mock()
            val = conn.watch_contents(FAKE_ZK_PATH, mock_fn,
                    default_value=GARBAGE, clean=True)
            self.assertEquals(val, FAKE_ZK_CONTENTS)
            self.assertEquals(mock_exists.call_count, 1)
            self.assertEquals(mock_create.call_count, 0)
            self.assertEquals(mock_get.call_count, 1)
            self.assertIn(FAKE_ZK_PATH, conn.content_watches)
            self.assertIn(mock_fn, conn.content_watches[FAKE_ZK_PATH])
            self.assertNotIn(mock_fn_old, conn.content_watches[FAKE_ZK_PATH])

    def test_watch_children_with_bad_args(self):
        with mock.patch("zookeeper.init") as mock_init:
            mock_init.side_effect = mock_zookeeper_init()
            conn = connection.ZookeeperConnection(FAKE_SERVERS)
            mock_fn = mock.Mock()
            with self.assertRaises(FakeBadArgumentsException):
                conn.watch_children(None, mock_fn)
            with self.assertRaises(FakeBadArgumentsException):
                conn.watch_children(FAKE_ZK_PATH, None)

    def test_watch_children_nonexistant_path(self):
        with mock.patch("zookeeper.init") as mock_init,\
                mock.patch("zookeeper.exists") as mock_exists,\
                mock.patch("zookeeper.create") as mock_create,\
                mock.patch("zookeeper.get_children") as mock_get:
            mock_init.side_effect = mock_zookeeper_init()
            conn = connection.ZookeeperConnection(FAKE_SERVERS)
            mock_exists.return_value = False
            mock_get.return_value = []
            mock_fn = mock.Mock()
            val = conn.watch_children(FAKE_ZK_PATH, mock_fn)
            self.assertEquals(val, [])
            self.assertTrue(mock_exists.call_count >= 1)
            self.assertEquals(mock_create.call_count, 1)
            self.assertEquals(mock_get.call_count, 1)
            self.assertIn(FAKE_ZK_PATH, conn.child_watches)
            self.assertIn(mock_fn, conn.child_watches[FAKE_ZK_PATH])

    def test_watch_children_existing_path(self):
        with mock.patch("zookeeper.init") as mock_init,\
                mock.patch("zookeeper.exists") as mock_exists,\
                mock.patch("zookeeper.create") as mock_create,\
                mock.patch("zookeeper.get_children") as mock_get:
            mock_init.side_effect = mock_zookeeper_init()
            conn = connection.ZookeeperConnection(FAKE_SERVERS)
            mock_exists.return_value = True
            mock_get.return_value = FAKE_ZK_CHILDREN
            mock_fn = mock.Mock()
            val = conn.watch_children(FAKE_ZK_PATH, mock_fn)
            self.assertEquals(val, FAKE_ZK_CHILDREN)
            self.assertTrue(mock_exists.call_count >= 1)
            self.assertEquals(mock_create.call_count, 0)
            self.assertEquals(mock_get.call_count, 1)
            self.assertIn(FAKE_ZK_PATH, conn.child_watches)
            self.assertIn(mock_fn, conn.child_watches[FAKE_ZK_PATH])

    def test_watch_children_clean_existing_path(self):
        with mock.patch("zookeeper.init") as mock_init,\
                mock.patch("zookeeper.exists") as mock_exists,\
                mock.patch("zookeeper.create") as mock_create,\
                mock.patch("zookeeper.get_children") as mock_get:
            mock_init.side_effect = mock_zookeeper_init()
            conn = connection.ZookeeperConnection(FAKE_SERVERS)
            mock_exists.return_value = True
            mock_get.return_value = FAKE_ZK_CHILDREN
            mock_fn_old = mock.Mock()
            conn.child_watches[FAKE_ZK_PATH] = [mock_fn_old]
            mock_fn = mock.Mock()
            val = conn.watch_children(FAKE_ZK_PATH, mock_fn, clean=True)
            self.assertEquals(val, FAKE_ZK_CHILDREN)
            self.assertTrue(mock_exists.call_count >= 1)
            self.assertEquals(mock_create.call_count, 0)
            self.assertEquals(mock_get.call_count, 1)
            self.assertIn(FAKE_ZK_PATH, conn.child_watches)
            self.assertIn(mock_fn, conn.child_watches[FAKE_ZK_PATH])
            self.assertNotIn(mock_fn_old, conn.child_watches[FAKE_ZK_PATH])

    def test_zookeeper_watch_non_event(self):
        with mock.patch("zookeeper.init") as mock_init,\
                mock.patch("zookeeper.get") as mock_get,\
                mock.patch("zookeeper.get_children") as mock_get_children:
            mock_init.side_effect = mock_zookeeper_init()
            conn = connection.ZookeeperConnection(FAKE_SERVERS)
            mock_fn = mock.Mock()
            conn.content_watches[FAKE_ZK_PATH] = [mock_fn]
            conn.child_watches[FAKE_ZK_PATH] = [mock_fn]
            conn.zookeeper_watch(FAKE_ZK_HANDLE, zookeeper.OK,
                    mock_zookeeper_mod.CONNECTED_STATE, FAKE_ZK_PATH)
            self.assertEquals(mock_fn.call_count, 0)
            self.assertEquals(mock_get.call_count, 0)
            self.assertEquals(mock_get_children.call_count, 0)

    def test_zookeeper_watch_content_event(self):
        with mock.patch("zookeeper.init") as mock_init,\
                mock.patch("zookeeper.get") as mock_get,\
                mock.patch("zookeeper.get_children") as mock_get_children:
            mock_init.side_effect = mock_zookeeper_init()
            conn = connection.ZookeeperConnection(FAKE_SERVERS)
            mock_content_fn = mock.Mock()
            conn.content_watches[FAKE_ZK_PATH] = [mock_content_fn]
            mock_child_fn = mock.Mock()
            conn.child_watches[FAKE_ZK_PATH] = [mock_child_fn]
            mock_get.return_value = (FAKE_ZK_CONTENTS, GARBAGE)
            conn.zookeeper_watch(FAKE_ZK_HANDLE,
                    mock_zookeeper_mod.CHANGED_EVENT,
                    mock_zookeeper_mod.CONNECTED_STATE, FAKE_ZK_PATH)
            self.assertEquals(mock_content_fn.call_count, 1)
            self.assertEquals(mock_content_fn.call_args_list[0][0][0], FAKE_ZK_CONTENTS)
            self.assertEquals(mock_child_fn.call_count, 0)
            self.assertEquals(mock_get.call_count, 1)
            self.assertEquals(mock_get_children.call_count, 0)

    def test_zookeeper_watch_children_event(self):
        with mock.patch("zookeeper.init") as mock_init,\
                mock.patch("zookeeper.get") as mock_get,\
                mock.patch("zookeeper.get_children") as mock_get_children:
            mock_init.side_effect = mock_zookeeper_init()
            conn = connection.ZookeeperConnection(FAKE_SERVERS)
            mock_content_fn = mock.Mock()
            conn.content_watches[FAKE_ZK_PATH] = [mock_content_fn]
            mock_child_fn = mock.Mock()
            conn.child_watches[FAKE_ZK_PATH] = [mock_child_fn]
            mock_get_children.return_value = FAKE_ZK_CHILDREN
            conn.zookeeper_watch(FAKE_ZK_HANDLE,
                    mock_zookeeper_mod.CHILD_EVENT,
                    mock_zookeeper_mod.CONNECTED_STATE, FAKE_ZK_PATH)
            self.assertEquals(mock_content_fn.call_count, 0)
            self.assertEquals(mock_child_fn.call_count, 1)
            self.assertEquals(mock_child_fn.call_args_list[0][0][0], FAKE_ZK_CHILDREN)
            self.assertEquals(mock_get.call_count, 0)
            self.assertEquals(mock_get_children.call_count, 1)

    def test_clear_watch_path_with_bad_args(self):
        with mock.patch("zookeeper.init") as mock_init:
            mock_init.side_effect = mock_zookeeper_init()
            conn = connection.ZookeeperConnection(FAKE_SERVERS)
            with self.assertRaises(FakeBadArgumentsException):
                conn.clear_watch_path(None)

    def test_clear_watch_path_nonexistant(self):
        with mock.patch("zookeeper.init") as mock_init,\
                mock.patch("zookeeper.get") as mock_get,\
                mock.patch("zookeeper.get_children") as mock_get_children:
            mock_init.side_effect = mock_zookeeper_init()
            conn = connection.ZookeeperConnection(FAKE_SERVERS)
            conn.clear_watch_path(FAKE_ZK_PATH)
            self.assertNotIn(FAKE_ZK_PATH, conn.content_watches)
            self.assertNotIn(FAKE_ZK_PATH, conn.child_watches)

    def test_clear_watch_path_existant(self):
        with mock.patch("zookeeper.init") as mock_init,\
                mock.patch("zookeeper.get") as mock_get,\
                mock.patch("zookeeper.get_children") as mock_get_children:
            mock_init.side_effect = mock_zookeeper_init()
            conn = connection.ZookeeperConnection(FAKE_SERVERS)
            mock_content_fn = mock.Mock()
            conn.content_watches[FAKE_ZK_PATH] = [mock_content_fn]
            mock_child_fn = mock.Mock()
            conn.child_watches[FAKE_ZK_PATH] = [mock_child_fn]
            conn.clear_watch_path(FAKE_ZK_PATH)
            self.assertNotIn(FAKE_ZK_PATH, conn.content_watches)
            self.assertNotIn(FAKE_ZK_PATH, conn.child_watches)

    def test_clear_watch_fn_with_bad_args(self):
        with mock.patch("zookeeper.init") as mock_init:
            mock_init.side_effect = mock_zookeeper_init()
            conn = connection.ZookeeperConnection(FAKE_SERVERS)
            with self.assertRaises(FakeBadArgumentsException):
                conn.clear_watch_fn(None)

    def test_clear_watch_fn_nonexistant(self):
        with mock.patch("zookeeper.init") as mock_init,\
                mock.patch("zookeeper.get") as mock_get,\
                mock.patch("zookeeper.get_children") as mock_get_children:
            mock_init.side_effect = mock_zookeeper_init()
            conn = connection.ZookeeperConnection(FAKE_SERVERS)
            mock_fn = mock.Mock()
            conn.clear_watch_fn(mock_fn)
            self.assertNotIn(FAKE_ZK_PATH, conn.content_watches)
            self.assertNotIn(FAKE_ZK_PATH, conn.child_watches)

    def test_clear_watch_fn_existant(self):
        with mock.patch("zookeeper.init") as mock_init,\
                mock.patch("zookeeper.get") as mock_get,\
                mock.patch("zookeeper.get_children") as mock_get_children:
            mock_init.side_effect = mock_zookeeper_init()
            conn = connection.ZookeeperConnection(FAKE_SERVERS)
            mock_content_fn = mock.Mock()
            conn.content_watches[FAKE_ZK_PATH] = [mock_content_fn]
            mock_child_fn = mock.Mock()
            conn.child_watches[FAKE_ZK_PATH] = [mock_child_fn]
            conn.clear_watch_fn(mock_content_fn)
            self.assertNotIn(mock_content_fn, conn.content_watches.get(FAKE_ZK_PATH, []))
            self.assertIn(FAKE_ZK_PATH, conn.child_watches)
            self.assertIn(mock_child_fn, conn.child_watches[FAKE_ZK_PATH])
        with mock.patch("zookeeper.init") as mock_init,\
                mock.patch("zookeeper.get") as mock_get,\
                mock.patch("zookeeper.get_children") as mock_get_children:
            mock_init.side_effect = mock_zookeeper_init()
            conn = connection.ZookeeperConnection(FAKE_SERVERS)
            mock_content_fn = mock.Mock()
            conn.content_watches[FAKE_ZK_PATH] = [mock_content_fn]
            mock_child_fn = mock.Mock()
            conn.child_watches[FAKE_ZK_PATH] = [mock_child_fn]
            conn.clear_watch_fn(mock_child_fn)
            self.assertIn(FAKE_ZK_PATH, conn.content_watches)
            self.assertIn(mock_content_fn, conn.content_watches[FAKE_ZK_PATH])
            self.assertNotIn(mock_child_fn, conn.child_watches.get(FAKE_ZK_PATH, []))
