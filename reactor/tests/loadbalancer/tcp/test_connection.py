import unittest
import mock
import os
import Queue

# Fake data
FAKE_CMD = ["ls"]
FAKE_PIPE = (1, 2)
FAKE_CHILD_PID = 0x123
FAKE_GRANDCHILD_PID = 0x456
FAKE_CHILD_FDS = [ 3 ]
FAKE_SOCK_FD = 3
FAKE_SOCK_FD_2 = 5
FAKE_CLIENT_FD = 4
FAKE_SOCKNAME = ("12.34.56.78", 1234)
FAKE_CLIENT_IP = "98.76.54.32"
FAKE_CLIENT_PORT = 4321
FAKE_CLIENT_SOCKNAME = (FAKE_CLIENT_IP, FAKE_CLIENT_PORT)
FAKE_CLIENT_SESSION = "%s:%s" % FAKE_CLIENT_SOCKNAME
FAKE_CLIENT_SESSION_BOGUS = "0.0.0.0:0"
FAKE_BACKEND_IP = "10.10.10.10"
FAKE_BACKEND_PORT = 9876
FAKE_BACKEND = (FAKE_BACKEND_IP, FAKE_BACKEND_PORT)
FAKE_BACKEND_ID = "%s:%d" % FAKE_BACKEND
FAKE_PORT = 1234
FAKE_PORT_2 = 2345
FAKE_PORTS = [ FAKE_PORT ]
FAKE_PORTS_MULT = [ FAKE_PORT, FAKE_PORT_2 ]
FAKE_RECONNECT = 60
FAKE_URL = "tcp://%d" % FAKE_PORT
FAKE_URL_BAD = "bad://%d" % FAKE_PORT
FAKE_NOW = 123456789012345

GARBAGE = 0xdeadbeef

# A helper to let us simulate os._exit()
class OsExit(Exception):
    pass

import reactor.loadbalancer.tcp.connection as connection

class GlobalTests(unittest.TestCase):
    def test_close_fd_all_excepted(self):
        with mock.patch('os.sysconf') as mock_sysconf,\
                mock.patch('os.close') as mock_close:
            mock_sysconf.return_value = 512
            connection.close_fds(except_fds=range(512))
            self.assertEquals(mock_close.call_count, 0)
        with mock.patch('os.sysconf') as mock_sysconf,\
                mock.patch('os.close') as mock_close:
            mock_sysconf.side_effect = ValueError()
            connection.close_fds(except_fds=range(1024))
            self.assertEquals(mock_close.call_count, 0)

    def test_close_fd_none_excepted(self):
        with mock.patch('os.sysconf') as mock_sysconf,\
                mock.patch('os.close') as mock_close:
            mock_sysconf.return_value = 512
            connection.close_fds(except_fds=[])
            self.assertEquals(mock_close.call_count, 512)
        with mock.patch('os.sysconf') as mock_sysconf,\
                mock.patch('os.close') as mock_close:
            mock_sysconf.side_effect = ValueError()
            connection.close_fds(except_fds=[])
            self.assertEquals(mock_close.call_count, 1024)

    def test_close_fd_some_excepted(self):
        with mock.patch('os.sysconf') as mock_sysconf,\
                mock.patch('os.close') as mock_close:
            mock_sysconf.return_value = 512
            connection.close_fds(except_fds=[1, 2, 3])
            self.assertEquals(mock_close.call_count, 509)
        with mock.patch('os.sysconf') as mock_sysconf,\
                mock.patch('os.close') as mock_close:
            mock_sysconf.side_effect = ValueError()
            connection.close_fds(except_fds=[1, 2, 3])
            self.assertEquals(mock_close.call_count, 1021)

    def test_fork_and_exec_parent(self):
        with mock.patch('os.fork') as mock_fork:
            mock_fork.side_effect = [ FAKE_CHILD_PID ]
            child = connection.fork_and_exec(FAKE_CMD, FAKE_CHILD_FDS)
            self.assertEqual(child, FAKE_CHILD_PID)
            self.assertEquals(mock_fork.call_count, 1)

    def test_fork_and_exec_child(self):
        with mock.patch('os.fork') as mock_fork,\
                mock.patch('os.close') as mock_close,\
                mock.patch('os.setsid') as mock_setsid,\
                mock.patch('os.execvp') as mock_execvp,\
                mock.patch(connection.__name__ + '.close_fds') as mock_close_fds:
            mock_fork.side_effect = [ 0 ]
            child = connection.fork_and_exec(FAKE_CMD, FAKE_CHILD_FDS)
            self.assertIsNone(child)
            self.assertEquals(mock_fork.call_count, 1)
            self.assertEquals(mock_close_fds.call_count, 1)
            self.assertEquals(mock_setsid.call_count, 1)
            self.assertEquals(mock_execvp.call_count, 1)

class AcceptTests(unittest.TestCase):
    def test_constructor_bad_socket(self):
        with mock.patch('os.dup') as mock_dup:
            mock_socket = mock.Mock()
            mock_socket.accept.side_effect = IOError()
            with self.assertRaises(IOError):
                accept = connection.Accept(mock_socket)

    def test_constructor_success(self):
        with mock.patch('os.dup') as mock_dup:
            mock_connsock = mock.Mock()
            mock_connsock.fileno.return_value = FAKE_SOCK_FD
            mock_socket = mock.Mock()
            mock_socket.accept.return_value = (mock_connsock, FAKE_CLIENT_SOCKNAME)
            mock_socket.getsockname.return_value = FAKE_SOCKNAME
            mock_dup.return_value = FAKE_CLIENT_FD
            accept = connection.Accept(mock_socket)
            accept.drop = lambda: True
            self.assertEquals(accept.fd, FAKE_CLIENT_FD)
            self.assertEquals(accept.src, FAKE_CLIENT_SOCKNAME)
            self.assertEquals(accept.dst, FAKE_SOCKNAME)
            self.assertEquals(mock_connsock._sock.close.call_count, 1)

    def test_drop_bad_socket(self):
        with mock.patch('os.close') as mock_close:
            mock_accept = mock.Mock(spec=connection.Accept)
            mock_accept.fd = FAKE_CLIENT_FD
            mock_accept.src = FAKE_CLIENT_SOCKNAME
            mock_close.side_effect = IOError()
            connection.Accept.drop(mock_accept)
            self.assertEquals(mock_close.call_count, 1)
            self.assertEquals(mock_close.call_args_list[0][0], (FAKE_CLIENT_FD,))
            self.assertIsNone(mock_accept.fd)

    def test_drop_success(self):
        with mock.patch('os.close') as mock_close:
            mock_accept = mock.Mock(spec=connection.Accept)
            mock_accept.fd = FAKE_CLIENT_FD
            connection.Accept.drop(mock_accept)
            self.assertEquals(mock_close.call_count, 1)
            self.assertEquals(mock_close.call_args_list[0][0], (FAKE_CLIENT_FD,))
            self.assertIsNone(mock_accept.fd)

    def test_redirect_fork_failed(self):
        with mock.patch('os.close') as mock_close,\
                mock.patch(connection.__name__ + '.fork_and_exec') as mock_fe:
            mock_accept = mock.Mock(spec=connection.Accept)
            mock_accept.fd = FAKE_CLIENT_FD
            mock_accept.src = FAKE_CLIENT_SOCKNAME
            mock_accept.dst = FAKE_SOCKNAME
            mock_fe.return_value = None
            child = connection.Accept.redirect(mock_accept, FAKE_BACKEND_IP, FAKE_BACKEND_PORT)
            self.assertIsNone(child)
            self.assertEquals(mock_fe.call_count, 1)
            self.assertIsNotNone(mock_accept.fd)
            self.assertEquals(mock_close.call_count, 0)

    def test_redirect_success(self):
        with mock.patch('os.close') as mock_close,\
                mock.patch(connection.__name__ + '.fork_and_exec') as mock_fe:
            mock_accept = mock.Mock(spec=connection.Accept)
            mock_accept.fd = FAKE_CLIENT_FD
            mock_accept.src = FAKE_CLIENT_SOCKNAME
            mock_accept.dst = FAKE_SOCKNAME
            mock_fe.return_value = FAKE_GRANDCHILD_PID
            child = connection.Accept.redirect(mock_accept, FAKE_BACKEND_IP, FAKE_BACKEND_PORT)
            self.assertEquals(child, FAKE_GRANDCHILD_PID)
            self.assertEquals(mock_fe.call_count, 1)
            self.assertIsNone(mock_accept.fd)
            self.assertEquals(mock_close.call_count, 1)
            self.assertEquals(mock_close.call_args_list[0][0], (FAKE_CLIENT_FD,))

class ConnectionConsumerTests(unittest.TestCase):
    def test_constructor(self):
        # There's no logic in the constructor
        pass

    def test_set(self):
        mock_consumer = mock.Mock(spec=connection.ConnectionConsumer)
        mock_consumer.cond = mock.Mock()
        connection.ConnectionConsumer.set(mock_consumer, FAKE_PORTS)
        self.assertEquals(mock_consumer.portmap, FAKE_PORTS)

    def test_stop(self):
        mock_producer = mock.Mock(spec=connection.ConnectionProducer)
        mock_consumer = mock.Mock(spec=connection.ConnectionConsumer)
        mock_consumer.cond = mock.Mock()
        mock_consumer.producer = mock_producer
        connection.ConnectionConsumer.stop(mock_consumer)
        self.assertFalse(mock_consumer.execute)

    def test_handle_exclusive_locked(self):
        mock_accept = mock.Mock(spec=connection.Accept)
        mock_accept.fd = FAKE_CLIENT_FD
        mock_accept.src = FAKE_CLIENT_SOCKNAME
        mock_accept.dst = FAKE_SOCKNAME
        mock_accept.redirect.return_value = FAKE_GRANDCHILD_PID
        mock_consumer = mock.Mock(spec=connection.ConnectionConsumer)
        mock_consumer.cond = mock.Mock()
        mock_consumer.locks = mock.Mock()
        mock_consumer.locks.find.return_value = ["%s:%d" % (FAKE_BACKEND_IP, FAKE_PORT)]
        mock_consumer.portmap = {}
        mock_consumer.portmap[FAKE_PORT] = (FAKE_URL, True, FAKE_RECONNECT, [FAKE_BACKEND], [])
        mock_consumer.children = {}
        mock_consumer.standby = {}
        handled = connection.ConnectionConsumer.handle(mock_consumer, mock_accept)
        self.assertTrue(handled)
        self.assertEquals(mock_accept.redirect.call_count, 1)
        self.assertIn(FAKE_GRANDCHILD_PID, mock_consumer.children)
        self.assertEquals(mock_consumer.children[FAKE_GRANDCHILD_PID], (FAKE_BACKEND_IP, FAKE_PORT, mock_accept, FAKE_RECONNECT))

    def test_handle_exclusive_unlocked(self):
        mock_accept = mock.Mock(spec=connection.Accept)
        mock_accept.fd = FAKE_CLIENT_FD
        mock_accept.src = FAKE_CLIENT_SOCKNAME
        mock_accept.dst = FAKE_SOCKNAME
        mock_accept.redirect.return_value = FAKE_GRANDCHILD_PID
        mock_consumer = mock.Mock(spec=connection.ConnectionConsumer)
        mock_consumer.cond = mock.Mock()
        mock_consumer.locks = mock.Mock()
        mock_consumer.locks.find.return_value = []
        mock_consumer.locks.lock.return_value = FAKE_BACKEND_ID
        mock_consumer.portmap = {}
        mock_consumer.portmap[FAKE_PORT] = (FAKE_URL, True, FAKE_RECONNECT, [FAKE_BACKEND], [])
        mock_consumer.children = {}
        handled = connection.ConnectionConsumer.handle(mock_consumer, mock_accept)
        self.assertTrue(handled)
        self.assertEquals(mock_accept.redirect.call_count, 1)
        self.assertIn(FAKE_GRANDCHILD_PID, mock_consumer.children)
        self.assertEquals(mock_consumer.children[FAKE_GRANDCHILD_PID], (FAKE_BACKEND_IP, FAKE_BACKEND_PORT, mock_accept, FAKE_RECONNECT))

    def test_handle_exclusive_no_hosts(self):
        mock_accept = mock.Mock(spec=connection.Accept)
        mock_accept.fd = FAKE_CLIENT_FD
        mock_accept.src = FAKE_CLIENT_SOCKNAME
        mock_accept.dst = FAKE_SOCKNAME
        mock_consumer = mock.Mock(spec=connection.ConnectionConsumer)
        mock_consumer.cond = mock.Mock()
        mock_consumer.locks = mock.Mock()
        mock_consumer.locks.find.return_value = []
        mock_consumer.locks.lock.return_value = None
        mock_consumer.portmap = {}
        mock_consumer.portmap[FAKE_PORT] = (FAKE_URL, True, FAKE_RECONNECT, [FAKE_BACKEND], [])
        mock_consumer.children = {}
        handled = connection.ConnectionConsumer.handle(mock_consumer, mock_accept)
        self.assertFalse(handled)
        self.assertEquals(mock_accept.redirect.call_count, 0)

    def test_handle_unexclusive(self):
        mock_accept = mock.Mock(spec=connection.Accept)
        mock_accept.fd = FAKE_CLIENT_FD
        mock_accept.src = FAKE_CLIENT_SOCKNAME
        mock_accept.dst = FAKE_SOCKNAME
        mock_accept.redirect.return_value = FAKE_GRANDCHILD_PID
        mock_consumer = mock.Mock(spec=connection.ConnectionConsumer)
        mock_consumer.cond = mock.Mock()
        mock_consumer.portmap = {}
        mock_consumer.portmap[FAKE_PORT] = (FAKE_URL, False, 0, [FAKE_BACKEND], [])
        mock_consumer.children = {}
        handled = connection.ConnectionConsumer.handle(mock_consumer, mock_accept)
        self.assertTrue(handled)
        self.assertEquals(mock_accept.redirect.call_count, 1)
        self.assertIn(FAKE_GRANDCHILD_PID, mock_consumer.children)
        self.assertEquals(mock_consumer.children[FAKE_GRANDCHILD_PID], (FAKE_BACKEND_IP, FAKE_BACKEND_PORT, mock_accept, False))

    def test_handle_unexclusive_no_hosts(self):
        mock_accept = mock.Mock(spec=connection.Accept)
        mock_accept.fd = FAKE_CLIENT_FD
        mock_accept.src = FAKE_CLIENT_SOCKNAME
        mock_accept.dst = FAKE_SOCKNAME
        mock_consumer = mock.Mock(spec=connection.ConnectionConsumer)
        mock_consumer.cond = mock.Mock()
        mock_consumer.portmap = {}
        mock_consumer.children = {}
        handled = connection.ConnectionConsumer.handle(mock_consumer, mock_accept)
        self.assertTrue(handled)
        self.assertEquals(mock_accept.redirect.call_count, 0)
        self.assertEquals(mock_accept.drop.call_count, 1)

    def test_handle_unexclusive_redirect_failed(self):
        mock_accept = mock.Mock(spec=connection.Accept)
        mock_accept.fd = FAKE_CLIENT_FD
        mock_accept.src = FAKE_CLIENT_SOCKNAME
        mock_accept.dst = FAKE_SOCKNAME
        mock_accept.redirect.return_value = None
        mock_consumer = mock.Mock(spec=connection.ConnectionConsumer)
        mock_consumer.cond = mock.Mock()
        mock_consumer.portmap = {}
        mock_consumer.portmap[FAKE_PORT] = (FAKE_URL, False, 0, [FAKE_BACKEND], [])
        mock_consumer.children = {}
        handled = connection.ConnectionConsumer.handle(mock_consumer, mock_accept)
        self.assertFalse(handled)
        self.assertEquals(mock_accept.redirect.call_count, 1)
        self.assertNotIn(FAKE_GRANDCHILD_PID, mock_consumer.children)

    def test_wait(self):
        # No logic in wait
        pass

    def test_wakeup(self):
        # No logic in wakeup
        pass

    def test_run_handle_one(self):
        with mock.patch('os.kill') as mock_kill:
            mock_accept = mock.Mock(spec=connection.Accept)
            mock_accept.fd = FAKE_CLIENT_FD
            mock_accept.src = FAKE_CLIENT_SOCKNAME
            mock_accept.dst = FAKE_SOCKNAME
            mock_consumer = mock.Mock(spec=connection.ConnectionConsumer)
            mock_consumer.execute = True
            mock_consumer.handle.return_value = True
            mock_consumer.producer = mock.Mock()
            mock_consumer.producer.next.side_effect = [ mock_accept, None ]
            mock_consumer.postponed = []
            mock_consumer.cond = mock.Mock()
            mock_consumer.locks = mock.Mock()
            type(mock_consumer).execute = mock.PropertyMock(side_effect = [True, True, False])
            mock_consumer.children = {}
            connection.ConnectionConsumer.run(mock_consumer)
            self.assertEquals(mock_consumer.handle.call_count, 1)
            self.assertEquals(mock_consumer.reap_children.call_count, 0)
            self.assertEquals(mock_consumer.producer.next.call_count, 2)
            self.assertEquals(len(mock_consumer.postponed), 0)

    def test_run_push_one(self):
        with mock.patch('os.kill') as mock_kill:
            mock_accept = mock.Mock(spec=connection.Accept)
            mock_accept.fd = FAKE_CLIENT_FD
            mock_accept.src = FAKE_CLIENT_SOCKNAME
            mock_accept.dst = FAKE_SOCKNAME
            mock_consumer = mock.Mock(spec=connection.ConnectionConsumer)
            type(mock_consumer).execute = mock.PropertyMock(side_effect = [True, False])
            mock_consumer.handle.return_value = False
            mock_consumer.producer = mock.Mock()
            mock_consumer.producer.next.side_effect = [ mock_accept, None ]
            mock_consumer.children = {}
            mock_consumer.postponed = []
            mock_consumer.cond = mock.Mock()
            connection.ConnectionConsumer.run(mock_consumer)
            self.assertEquals(mock_consumer.handle.call_count, 1)
            self.assertEquals(mock_consumer.producer.next.call_count, 1)
            self.assertEquals(len(mock_consumer.postponed), 1)

    def test_run_clean_all(self):
        mock_producer = mock.Mock(spec=connection.ConnectionProducer)
        mock_accept = mock.Mock(spec=connection.Accept)
        mock_accept.fd = FAKE_CLIENT_FD
        mock_accept.src = FAKE_CLIENT_SOCKNAME
        mock_accept.dst = FAKE_SOCKNAME
        mock_consumer = mock.Mock(spec=connection.ConnectionConsumer)
        mock_consumer.children = { FAKE_GRANDCHILD_PID : ( FAKE_BACKEND_IP, FAKE_BACKEND_PORT, mock_accept, 0 ) }
        mock_consumer.producer = mock_producer
        mock_consumer.cond = mock.Mock()
        connection.ConnectionConsumer.stop(mock_consumer)
        self.assertEquals(mock_consumer.kill_children.call_count, 1)

    def test_run_reap_all(self):
        with mock.patch('os.kill') as mock_kill:
            mock_accept = mock.Mock(spec=connection.Accept)
            mock_accept.fd = FAKE_CLIENT_FD
            mock_accept.src = FAKE_CLIENT_SOCKNAME
            mock_accept.dst = FAKE_SOCKNAME
            mock_consumer = mock.Mock(spec=connection.ConnectionConsumer)
            mock_consumer.children = { FAKE_GRANDCHILD_PID : ( FAKE_BACKEND_IP, FAKE_BACKEND_PORT, mock_accept, 0 ) }
            connection.ConnectionConsumer.kill_children(mock_consumer)
            self.assertEquals(mock_kill.call_count, 1)
            self.assertEquals(mock_kill.call_args_list[0][0][0], FAKE_GRANDCHILD_PID)

    def test_reap_children(self):
        with mock.patch('os.kill') as mock_kill:
            mock_accept = mock.Mock(spec=connection.Accept)
            mock_accept.fd = FAKE_CLIENT_FD
            mock_accept.src = FAKE_CLIENT_SOCKNAME
            mock_accept.dst = FAKE_SOCKNAME
            mock_consumer = mock.Mock(spec=connection.ConnectionConsumer)
            mock_consumer.cond = mock.Mock()
            mock_consumer.locks = mock.Mock()
            mock_consumer.children = { FAKE_GRANDCHILD_PID : ( FAKE_BACKEND_IP, FAKE_BACKEND_PORT, mock_accept, 0 ) }
            mock_kill.side_effect = OSError()
            connection.ConnectionConsumer.reap_children(mock_consumer)
            self.assertNotIn(FAKE_GRANDCHILD_PID, mock_consumer.children)

    def test_reap_children_no_children(self):
        with mock.patch('os.kill') as mock_kill:
            mock_consumer = mock.Mock(spec=connection.ConnectionConsumer)
            mock_consumer.cond = mock.Mock()
            mock_consumer.locks = mock.Mock()
            mock_consumer.children = {}
            connection.ConnectionConsumer.reap_children(mock_consumer)
            self.assertEquals(mock_kill.call_count, 0)

    def test_sessions(self):
        with mock.patch(connection.__name__ + '._as_client') as mock_ac:
            mock_accept = mock.Mock(spec=connection.Accept)
            mock_accept.fd = FAKE_CLIENT_FD
            mock_accept.src = FAKE_CLIENT_SOCKNAME
            mock_accept.dst = FAKE_SOCKNAME
            mock_consumer = mock.Mock(spec=connection.ConnectionConsumer)
            mock_consumer.cond = mock.Mock()
            mock_consumer.children = { FAKE_GRANDCHILD_PID : ( FAKE_BACKEND_IP, FAKE_BACKEND_PORT, mock_accept, 0 ) }
            mock_ac.return_value = FAKE_CLIENT_SESSION
            sessions = connection.ConnectionConsumer.sessions(mock_consumer)
            self.assertIn(FAKE_BACKEND_ID, sessions)
            self.assertEquals(sessions[FAKE_BACKEND_ID], [FAKE_CLIENT_SESSION])

    def test_sessions_no_clients(self):
        mock_consumer = mock.Mock(spec=connection.ConnectionConsumer)
        mock_consumer.cond = mock.Mock()
        mock_consumer.children = {}
        sessions = connection.ConnectionConsumer.sessions(mock_consumer)
        self.assertEquals(sessions, {})

    def test_drop_session(self):
        with mock.patch('os.kill') as mock_kill,\
                mock.patch(connection.__name__ + '._as_client') as mock_ac:
            mock_accept = mock.Mock(spec=connection.Accept)
            mock_accept.fd = FAKE_CLIENT_FD
            mock_accept.src = FAKE_CLIENT_SOCKNAME
            mock_accept.dst = FAKE_SOCKNAME
            mock_consumer = mock.Mock(spec=connection.ConnectionConsumer)
            mock_consumer.cond = mock.Mock()
            mock_consumer.children = { FAKE_GRANDCHILD_PID : ( FAKE_BACKEND_IP, FAKE_BACKEND_PORT, mock_accept, 0 ) }
            mock_ac.return_value = FAKE_CLIENT_SESSION
            connection.ConnectionConsumer.drop_session(mock_consumer, FAKE_CLIENT_SESSION, FAKE_BACKEND_ID)
            self.assertEquals(mock_kill.call_count, 1)
            self.assertEquals(mock_kill.call_args_list[0][0][0], FAKE_GRANDCHILD_PID)

    def test_drop_session_nonexistant(self):
        with mock.patch('os.kill') as mock_kill,\
                mock.patch(connection.__name__ + '._as_client') as mock_ac:
            mock_accept = mock.Mock(spec=connection.Accept)
            mock_accept.fd = FAKE_CLIENT_FD
            mock_accept.src = FAKE_CLIENT_SOCKNAME
            mock_accept.dst = FAKE_SOCKNAME
            mock_consumer = mock.Mock(spec=connection.ConnectionConsumer)
            mock_consumer.cond = mock.Mock()
            mock_consumer.children = { FAKE_GRANDCHILD_PID : ( FAKE_BACKEND_IP, FAKE_BACKEND_PORT, mock_accept, 0 ) }
            mock_ac.return_value = FAKE_CLIENT_SESSION
            connection.ConnectionConsumer.drop_session(mock_consumer, FAKE_CLIENT_SESSION_BOGUS, FAKE_BACKEND_ID)
            self.assertEquals(mock_kill.call_count, 0)
            self.assertIn(FAKE_GRANDCHILD_PID, mock_consumer.children)

class ConnectionProducerTests(unittest.TestCase):
    def test_constructor(self):
        # No logic in the ConnectionProducer constructor
        pass

    def test_stop(self):
        mock_producer = mock.Mock(spec=connection.ConnectionProducer)
        mock_producer.execute = True
        connection.ConnectionProducer.stop(mock_producer)
        self.assertFalse(mock_producer.execute)

    def test_set_add_one(self):
        with mock.patch('socket.socket') as mock_socket:
            mock_producer = mock.Mock(spec=connection.ConnectionProducer)
            mock_producer.cond = mock.Mock()
            mock_producer.sockets = {}
            mock_producer.filemap = {}
            mock_socket_obj = mock.Mock()
            mock_socket_obj.fileno.return_value = FAKE_SOCK_FD
            mock_socket.return_value = mock_socket_obj
            connection.ConnectionProducer.set(mock_producer, FAKE_PORTS)
            self.assertIn(FAKE_PORT, mock_producer.sockets)
            self.assertEquals(mock_producer.sockets[FAKE_PORT], mock_socket_obj)
            self.assertIn(FAKE_SOCK_FD, mock_producer.filemap)
            self.assertEquals(mock_producer.filemap[FAKE_SOCK_FD], mock_socket_obj)
            self.assertEquals(mock_socket_obj.bind.call_count, 1)
            self.assertEquals(mock_socket_obj.listen.call_count, 1)

    def test_set_add_one_cant_bind(self):
        with mock.patch('socket.socket') as mock_socket:
            mock_producer = mock.Mock(spec=connection.ConnectionProducer)
            mock_producer.cond = mock.Mock()
            mock_producer.sockets = {}
            mock_producer.filemap = {}
            mock_socket_obj = mock.Mock()
            mock_socket_obj.bind.side_effect = IOError()
            mock_socket.return_value = mock_socket_obj
            connection.ConnectionProducer.set(mock_producer, FAKE_PORTS)
            self.assertNotIn(FAKE_PORT, mock_producer.sockets)
            self.assertNotIn(FAKE_SOCK_FD, mock_producer.filemap)
            self.assertEquals(mock_socket_obj.bind.call_count, 1)
            self.assertEquals(mock_socket_obj.listen.call_count, 0)

    def test_set_add_two_cant_bind(self):
        with mock.patch('socket.socket') as mock_socket:
            mock_producer = mock.Mock(spec=connection.ConnectionProducer)
            mock_producer.cond = mock.Mock()
            mock_producer.sockets = {}
            mock_producer.filemap = {}
            mock_socket_obj = mock.Mock()
            mock_socket_obj.bind.side_effect = [IOError(), None]
            mock_socket_obj.fileno.return_value = FAKE_SOCK_FD
            mock_socket.return_value = mock_socket_obj
            connection.ConnectionProducer.set(mock_producer, FAKE_PORTS_MULT)
            self.assertIn(FAKE_PORT_2, mock_producer.sockets)
            self.assertEquals(mock_producer.sockets[FAKE_PORT_2], mock_socket_obj)
            self.assertIn(FAKE_SOCK_FD, mock_producer.filemap)
            self.assertEquals(mock_producer.filemap[FAKE_SOCK_FD], mock_socket_obj)
            self.assertEquals(mock_socket_obj.bind.call_count, 2)
            self.assertEquals(mock_socket_obj.listen.call_count, 1)

    def test_set_del_one(self):
        with mock.patch('socket.socket') as mock_socket:
            mock_socket_obj = mock.Mock()
            mock_socket_obj.fileno.return_value = FAKE_SOCK_FD
            mock_socket.return_value = mock_socket_obj
            mock_producer = mock.Mock(spec=connection.ConnectionProducer)
            mock_producer.cond = mock.Mock()
            mock_producer.sockets = { FAKE_PORT : mock_socket_obj }
            mock_producer.filemap = { FAKE_SOCK_FD : mock_socket_obj }
            connection.ConnectionProducer.set(mock_producer, [] )
            self.assertNotIn(FAKE_PORT, mock_producer.sockets)
            self.assertNotIn(FAKE_SOCK_FD, mock_producer.filemap)
            self.assertEquals(mock_socket_obj.bind.call_count, 0)
            self.assertEquals(mock_socket_obj.listen.call_count, 0)
            self.assertEquals(mock_socket_obj.close.call_count, 1)

    def test_set_add_one_del_one(self):
        with mock.patch('socket.socket') as mock_socket:
            mock_socket_obj = mock.Mock()
            mock_socket_obj.fileno.return_value = FAKE_SOCK_FD
            mock_socket_obj_2 = mock.Mock()
            mock_socket_obj_2.fileno.return_value = FAKE_SOCK_FD_2
            mock_socket.return_value = mock_socket_obj_2
            mock_producer = mock.Mock(spec=connection.ConnectionProducer)
            mock_producer.cond = mock.Mock()
            mock_producer.sockets = { FAKE_PORT : mock_socket_obj }
            mock_producer.filemap = { FAKE_SOCK_FD : mock_socket_obj }
            connection.ConnectionProducer.set(mock_producer, [FAKE_PORT_2] )
            self.assertNotIn(FAKE_PORT, mock_producer.sockets)
            self.assertNotIn(FAKE_SOCK_FD, mock_producer.filemap)
            self.assertIn(FAKE_PORT_2, mock_producer.sockets)
            self.assertEquals(mock_producer.sockets[FAKE_PORT_2], mock_socket_obj_2)
            self.assertIn(FAKE_SOCK_FD_2, mock_producer.filemap)
            self.assertEquals(mock_producer.filemap[FAKE_SOCK_FD_2], mock_socket_obj_2)
            self.assertEquals(mock_socket_obj.bind.call_count, 0)
            self.assertEquals(mock_socket_obj.listen.call_count, 0)
            self.assertEquals(mock_socket_obj.close.call_count, 1)
            self.assertEquals(mock_socket_obj_2.bind.call_count, 1)
            self.assertEquals(mock_socket_obj_2.listen.call_count, 1)
            self.assertEquals(mock_socket_obj_2.close.call_count, 0)

    def test_set_add_one_del_one_cant_bind(self):
        with mock.patch('socket.socket') as mock_socket:
            mock_socket_obj = mock.Mock()
            mock_socket_obj.fileno.return_value = FAKE_SOCK_FD
            mock_socket_obj_2 = mock.Mock()
            mock_socket_obj_2.bind.side_effect = IOError()
            mock_socket.return_value = mock_socket_obj_2
            mock_producer = mock.Mock(spec=connection.ConnectionProducer)
            mock_producer.cond = mock.Mock()
            mock_producer.sockets = { FAKE_PORT : mock_socket_obj }
            mock_producer.filemap = { FAKE_SOCK_FD : mock_socket_obj }
            connection.ConnectionProducer.set(mock_producer, [FAKE_PORT_2] )
            self.assertNotIn(FAKE_PORT, mock_producer.sockets)
            self.assertNotIn(FAKE_SOCK_FD, mock_producer.filemap)
            self.assertNotIn(FAKE_PORT_2, mock_producer.sockets)
            self.assertNotIn(FAKE_SOCK_FD_2, mock_producer.filemap)
            self.assertEquals(mock_socket_obj.bind.call_count, 0)
            self.assertEquals(mock_socket_obj.listen.call_count, 0)
            self.assertEquals(mock_socket_obj.close.call_count, 1)
            self.assertEquals(mock_socket_obj_2.bind.call_count, 1)
            self.assertEquals(mock_socket_obj_2.listen.call_count, 0)
            self.assertEquals(mock_socket_obj_2.close.call_count, 0)

    def test__update_epoll(self):
        # Some systems, e.g. OS X, don't have epoll, hence create=True
        # for select.epoll, and we need to mock the select.EPOLLIN
        # constant as well.
        with mock.patch('select.epoll', create=True) as mock_epoll,\
                mock.patch('select.EPOLLIN', create=True) as mock_epollin:
            mock_socket_obj = mock.Mock()
            mock_socket_obj.fileno.return_value = FAKE_SOCK_FD
            mock_producer = mock.Mock(spec=connection.ConnectionProducer)
            mock_producer.cond = mock.Mock()
            mock_producer.sockets = { FAKE_PORT : mock_socket_obj }
            mock_producer.filemap = { FAKE_SOCK_FD : mock_socket_obj }
            connection.ConnectionProducer._update_epoll(mock_producer)
            self.assertEquals(mock_epoll.call_count, 1)
            self.assertEquals(mock_producer.epoll.register.call_count, 1)

    def test_run_epoll_accept_one(self):
        with mock.patch(connection.__name__ + ".Accept") as mock_accept:
            mock_socket_obj = mock.Mock()
            mock_producer = mock.Mock(spec=connection.ConnectionProducer)
            mock_producer.cond = mock.Mock()
            mock_producer.queue = Queue.Queue()
            mock_producer.notifiers = []
            mock_producer.sockets = { FAKE_PORT : mock_socket_obj }
            mock_producer.filemap = { FAKE_SOCK_FD : mock_socket_obj }
            type(mock_producer).execute = mock.PropertyMock(side_effect = [True, False])
            mock_producer.epoll = mock.Mock()
            mock_producer.epoll.poll.return_value = [(FAKE_SOCK_FD, GARBAGE)]
            connection.ConnectionProducer.run(mock_producer)
            self.assertEquals(mock_producer.epoll.poll.call_count, 1)
            self.assertEquals(mock_accept.call_count, 1)

    def test_run_epoll_stale_sock(self):
        mock_producer = mock.Mock(spec=connection.ConnectionProducer)
        mock_producer.cond = mock.Mock()
        mock_producer.sockets = {}
        mock_producer.filemap = {}
        type(mock_producer).execute = mock.PropertyMock(side_effect = [True, False])
        mock_producer.epoll = mock.Mock()
        mock_producer.epoll.poll.return_value = [(FAKE_SOCK_FD, GARBAGE)]
        connection.ConnectionProducer.run(mock_producer)
        self.assertEquals(mock_producer.epoll.poll.call_count, 1)
        self.assertEquals(mock_producer._update_epoll.call_count, 1)

class ConnectionTests(unittest.TestCase):
    def test_constructor(self):
        # No logic in the constructor.
        pass

    def test_destructor(self):
        # No logic in the destructor.
        pass

    def test_delete(self):
        mock_conn = mock.Mock(spec=connection.Connection)
        mock_conn.producer = mock.Mock()
        mock_conn.consumer = mock.Mock()
        mock_conn.locks = mock.Mock()
        connection.Connection.__del__(mock_conn)
        self.assertEquals(mock_conn.producer.set.call_count, 1)
        self.assertEquals(mock_conn.producer.stop.call_count, 1)
        self.assertEquals(mock_conn.consumer.set.call_count, 1)
        self.assertEquals(mock_conn.consumer.stop.call_count, 1)

    def test_change_no_ips(self):
        mock_conn = mock.Mock(spec=connection.Connection)
        mock_conn.portmap = {}
        mock_conn.url_info.return_value = FAKE_PORT
        connection.Connection.change(mock_conn, FAKE_URL, [])
        self.assertEquals(mock_conn.portmap, {})

    def test_change_remove_ip(self):
        mock_conn = mock.Mock(spec=connection.Connection)
        mock_conn.url_info.return_value = FAKE_PORT
        mock_conn.portmap = { FAKE_PORT : (FAKE_URL, True, FAKE_RECONNECT, [(FAKE_BACKEND_IP, FAKE_BACKEND_PORT)], []) }
        connection.Connection.change(mock_conn, FAKE_URL, [])
        self.assertEquals(mock_conn.portmap, {})

    def test_change_add_ip(self):
        mock_backend = mock.Mock()
        mock_backend.ip = FAKE_BACKEND_IP
        mock_backend.port = FAKE_BACKEND_PORT
        mock_config = mock.Mock()
        mock_config.exclusive = True
        mock_config.reconnect = FAKE_RECONNECT
        mock_config.client_subnets = []
        mock_conn = mock.Mock(spec=connection.Connection)
        mock_conn.portmap = {}
        mock_conn.url_info.return_value = FAKE_PORT
        mock_conn._endpoint_config.return_value = mock_config
        connection.Connection.change(mock_conn, FAKE_URL, [mock_backend])
        self.assertIn(FAKE_PORT, mock_conn.portmap)
        self.assertEquals(mock_conn.portmap[FAKE_PORT], (FAKE_URL, True, FAKE_RECONNECT, [(FAKE_BACKEND_IP, FAKE_BACKEND_PORT)], []))

    def test_save(self):
        # No logic in save.
        pass

    def test_handle_no_subnet(self):
        mock_accept = mock.Mock(spec=connection.Accept)
        mock_accept.fd = FAKE_CLIENT_FD
        mock_accept.src = FAKE_CLIENT_SOCKNAME
        mock_accept.dst = FAKE_SOCKNAME
        mock_consumer = mock.Mock(spec=connection.ConnectionConsumer)
        mock_consumer.cond = mock.Mock()
        mock_consumer.locks = mock.Mock()
        mock_consumer.locks.find.return_value = [FAKE_BACKEND_ID]
        mock_consumer.portmap = {}
        mock_consumer.portmap[FAKE_PORT] = (FAKE_URL, True, FAKE_RECONNECT, [FAKE_BACKEND], [])
        mock_consumer.children = {}
        mock_consumer.standby = {}
        handled = connection.ConnectionConsumer.handle(mock_consumer, mock_accept)
        self.assertTrue(handled)
        self.assertEquals(mock_accept.redirect.call_count, 1)
        self.assertEquals(mock_accept.drop.call_count, 0)

    def test_handle_in_single_subnet(self):
        mock_accept = mock.Mock(spec=connection.Accept)
        mock_accept.fd = FAKE_CLIENT_FD
        mock_accept.src = FAKE_CLIENT_SOCKNAME
        mock_accept.dst = FAKE_SOCKNAME
        mock_consumer = mock.Mock(spec=connection.ConnectionConsumer)
        mock_consumer.cond = mock.Mock()
        mock_consumer.locks = mock.Mock()
        mock_consumer.locks.find.return_value = ["%s:%d" % (FAKE_BACKEND_IP, FAKE_PORT)]
        mock_consumer.portmap = {}
        mock_consumer.portmap[FAKE_PORT] = (FAKE_URL, True, FAKE_RECONNECT, [FAKE_BACKEND], ["%s/32" % FAKE_CLIENT_IP])
        mock_consumer.children = {}
        mock_consumer.standby = {}
        handled = connection.ConnectionConsumer.handle(mock_consumer, mock_accept)
        self.assertTrue(handled)
        self.assertEquals(mock_accept.redirect.call_count, 1)
        self.assertEquals(mock_accept.drop.call_count, 0)

    def test_handle_in_multi_subnet(self):
        mock_accept = mock.Mock(spec=connection.Accept)
        mock_accept.fd = FAKE_CLIENT_FD
        mock_accept.src = FAKE_CLIENT_SOCKNAME
        mock_accept.dst = FAKE_SOCKNAME
        mock_consumer = mock.Mock(spec=connection.ConnectionConsumer)
        mock_consumer.cond = mock.Mock()
        mock_consumer.locks = mock.Mock()
        mock_consumer.locks.find.return_value = ["%s:%d" % (FAKE_BACKEND_IP, FAKE_PORT)]
        mock_consumer.portmap = {}
        mock_consumer.portmap[FAKE_PORT] = (FAKE_URL, True, FAKE_RECONNECT, [FAKE_BACKEND], ["1.2.3.4/24", "%s/32" % FAKE_CLIENT_IP])
        mock_consumer.children = {}
        mock_consumer.standby = {}
        handled = connection.ConnectionConsumer.handle(mock_consumer, mock_accept)
        self.assertTrue(handled)
        self.assertEquals(mock_accept.redirect.call_count, 1)
        self.assertEquals(mock_accept.drop.call_count, 0)

    def test_handle_not_in_single_subnet(self):
        mock_accept = mock.Mock(spec=connection.Accept)
        mock_accept.fd = FAKE_CLIENT_FD
        mock_accept.src = FAKE_CLIENT_SOCKNAME
        mock_accept.dst = FAKE_SOCKNAME
        mock_consumer = mock.Mock(spec=connection.ConnectionConsumer)
        mock_consumer.cond = mock.Mock()
        mock_consumer.portmap = {}
        mock_consumer.portmap[FAKE_PORT] = (FAKE_URL, True, FAKE_RECONNECT, [FAKE_BACKEND], ["1.2.3.4/24"])
        mock_consumer.children = {}
        mock_consumer.standby = {}
        handled = connection.ConnectionConsumer.handle(mock_consumer, mock_accept)
        self.assertTrue(handled)
        self.assertEquals(mock_accept.redirect.call_count, 0)
        self.assertEquals(mock_accept.drop.call_count, 1)

    def test_handle_not_in_multi_subnet(self):
        mock_accept = mock.Mock(spec=connection.Accept)
        mock_accept.fd = FAKE_CLIENT_FD
        mock_accept.src = FAKE_CLIENT_SOCKNAME
        mock_accept.dst = FAKE_SOCKNAME
        mock_consumer = mock.Mock(spec=connection.ConnectionConsumer)
        mock_consumer.cond = mock.Mock()
        mock_consumer.portmap = {}
        mock_consumer.portmap[FAKE_PORT] = (FAKE_URL, True, FAKE_RECONNECT, [FAKE_BACKEND], ["1.2.3.4/24", "5.6.7.8/16"])
        mock_consumer.children = {}
        mock_consumer.standby = {}
        handled = connection.ConnectionConsumer.handle(mock_consumer, mock_accept)
        self.assertTrue(handled)
        self.assertEquals(mock_accept.redirect.call_count, 0)
        self.assertEquals(mock_accept.drop.call_count, 1)

    def test_handle_unexclusive_no_hosts(self):
        mock_accept = mock.Mock(spec=connection.Accept)
        mock_accept.fd = FAKE_CLIENT_FD
        mock_accept.src = FAKE_CLIENT_SOCKNAME
        mock_accept.dst = FAKE_SOCKNAME
        mock_consumer = mock.Mock(spec=connection.ConnectionConsumer)
        mock_consumer.cond = mock.Mock()
        mock_consumer.portmap = {}
        mock_consumer.children = {}
        mock_consumer.standby = {}
        handled = connection.ConnectionConsumer.handle(mock_consumer, mock_accept)
        self.assertTrue(handled)
        self.assertEquals(mock_accept.redirect.call_count, 0)
        self.assertEquals(mock_accept.drop.call_count, 1)

    def test_sessions(self):
        # No logic in sessions.
        pass

    def test_drop_session(self):
        # No logic in drop_sessions.
        pass
