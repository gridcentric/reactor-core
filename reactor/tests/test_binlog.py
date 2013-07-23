import sys
import unittest2 as unittest
import mock

import reactor.binlog as binlog

# Some dummy data
FAKE_TIMESTAMP = 123456789
TEST_ENTRY1 = binlog.BinaryLogRecord(lambda args: "T1 %d %d" % (args[0], args[1]))
TEST_ENTRY2 = binlog.BinaryLogRecord(lambda args: "T2 %d %d" % (args[0], args[1]))

# Some stubb classes
class FakeStore:
    def __init__(self):
        self.data = None
    def store_cb(self, _data):
        self.data = _data
    def retrieve_cb(self):
        return self.data

class BinLogTests(unittest.TestCase):
    def test_ConstructorWithSizeTooSmall(self):
        # Check that we raise an exception when passed
        # an inappropriate log size
        entsize = binlog.ENTRY_SIZE
        with self.assertRaises(ValueError):
            log = binlog.BinaryLog(entsize-1)

    def test_ConstructorWithoutRecordTypes(self):
        entsize = binlog.ENTRY_SIZE
        log = binlog.BinaryLog(entsize)
        entries = log.get()
        # Make sure the log is empty
        self.assertEqual(len(entries), 0)
        # Make an entry
        with self.assertRaises(KeyError):
            log.info(TEST_ENTRY1, 1, -1)

    def test_ConstructorWithRecordTypes(self):
        record_types = [ TEST_ENTRY1 ]
        entsize = binlog.ENTRY_SIZE
        log = binlog.BinaryLog(entsize, record_types=record_types)
        entries = log.get()
        # Make sure the log is empty
        self.assertEqual(len(entries), 0)
        # Make an entry
        with mock.patch('time.time', return_value=FAKE_TIMESTAMP):
            log.info(TEST_ENTRY1, 1, -1)
        entries = log.get()
        # Make sure the log contains our entry
        self.assertEqual(len(entries), 1)
        self.assertIn([FAKE_TIMESTAMP, "INFO", "T1 1 -1"], entries)

    def test_ConstructorWithCallbacks(self):
        record_types = [ TEST_ENTRY1 ]
        entsize = binlog.ENTRY_SIZE
        store = FakeStore()
        log = binlog.BinaryLog(entsize, record_types=record_types,
                               store_cb=store.store_cb,
                               retrieve_cb=store.retrieve_cb)
        entries = log.get()
        # Make sure the log is empty
        self.assertEqual(len(entries), 0)
        # Make an entry
        with mock.patch('time.time', return_value=FAKE_TIMESTAMP):
            log.info(TEST_ENTRY1, 1, -1)
        # Make sure the length of the stored data is correct
        self.assertEqual(len(store.retrieve_cb()), entsize)
        # Make sure the log contains our entry
        entries = log.get()
        self.assertEqual(len(entries), 1)
        self.assertIn([FAKE_TIMESTAMP, "INFO", "T1 1 -1"], entries)
        # Recreate the log
        log = binlog.BinaryLog(entsize, record_types=record_types,
                               store_cb=store.store_cb,
                               retrieve_cb=store.retrieve_cb)
        # Make sure the log still contains our entry
        entries = log.get()
        self.assertEqual(len(entries), 1)
        self.assertIn([FAKE_TIMESTAMP, "INFO", "T1 1 -1"], entries)

    def test_AddRecordType(self):
        entsize = binlog.ENTRY_SIZE
        log = binlog.BinaryLog(entsize)
        # Make an entry
        with mock.patch('time.time', return_value=FAKE_TIMESTAMP),\
                self.assertRaises(KeyError):
            log.info(TEST_ENTRY1, 1, -1)
        # Add record types
        log.add_record_type(TEST_ENTRY1)
        # Make an entry
        with mock.patch('time.time', return_value=FAKE_TIMESTAMP):
            log.info(TEST_ENTRY1, 1, -1)
        # Make sure the log contains our entry
        entries = log.get()
        self.assertEqual(len(entries), 1)
        self.assertIn([FAKE_TIMESTAMP, "INFO", "T1 1 -1"], entries)
        # Add more record types
        log.add_record_type(TEST_ENTRY2)
        # Make an entry
        with mock.patch('time.time', return_value=FAKE_TIMESTAMP+1):
            log.info(TEST_ENTRY2, 1, -1)
        # Make sure the log contains our entry
        entries = log.get()
        self.assertEqual(len(entries), 1)
        self.assertIn([FAKE_TIMESTAMP+1, "INFO", "T2 1 -1"], entries)

    def test_AddRecordTypes(self):
        entsize = binlog.ENTRY_SIZE
        log = binlog.BinaryLog(entsize)
        # Make an entry
        with mock.patch('time.time', return_value=FAKE_TIMESTAMP),\
                self.assertRaises(KeyError):
            log.info(TEST_ENTRY1, 1, -1)
        # Add record types
        record_types = [ TEST_ENTRY1 ]
        log.add_record_types(record_types)
        # Make an entry
        with mock.patch('time.time', return_value=FAKE_TIMESTAMP):
            log.info(TEST_ENTRY1, 1, -1)
        # Make sure the log contains our entry
        entries = log.get()
        self.assertEqual(len(entries), 1)
        self.assertIn([FAKE_TIMESTAMP, "INFO", "T1 1 -1"], entries)
        # Add more record types
        record_types = [ TEST_ENTRY2 ]
        log.add_record_types(record_types)
        # Make an entry
        with mock.patch('time.time', return_value=FAKE_TIMESTAMP+1):
            log.info(TEST_ENTRY2, 1, -1)
        # Make sure the log contains our entry
        entries = log.get()
        self.assertEqual(len(entries), 1)
        self.assertIn([FAKE_TIMESTAMP+1, "INFO", "T2 1 -1"], entries)

    def test_LogWrapsProperly(self):
        record_types = [ TEST_ENTRY1, TEST_ENTRY2 ]
        entsize = binlog.ENTRY_SIZE
        log = binlog.BinaryLog(entsize, record_types=record_types)
        # Make an entry
        with mock.patch('time.time', return_value=FAKE_TIMESTAMP):
            log.info(TEST_ENTRY1, 1, -1)
        # Make sure the log contains our entry
        entries = log.get()
        self.assertEqual(len(entries), 1)
        self.assertIn([FAKE_TIMESTAMP, "INFO", "T1 1 -1"], entries)
        # Make an entry
        with mock.patch('time.time', return_value=FAKE_TIMESTAMP+1):
            log.info(TEST_ENTRY2, 1, -1)
        # Make sure the log contains our entry
        entries = log.get()
        self.assertEqual(len(entries), 1)
        self.assertIn([FAKE_TIMESTAMP+1, "INFO", "T2 1 -1"], entries)
        # Make sure the log doesn't contain the old entry
        self.assertNotIn([FAKE_TIMESTAMP, "INFO", "T1 1 -1"], entries)

    def test_LogReloads(self):
        record_types = [ TEST_ENTRY1 ]
        entsize = binlog.ENTRY_SIZE
        store = FakeStore()
        log = binlog.BinaryLog(entsize, record_types=record_types,
                               store_cb=store.store_cb,
                               retrieve_cb=store.retrieve_cb)
        # Make an entry
        with mock.patch('time.time', return_value=FAKE_TIMESTAMP):
            log.info(TEST_ENTRY1, 1, -1)
        # Get the data and clear the store
        data = store.retrieve_cb()
        store.store_cb(None)
        # Recreate the log
        log = binlog.BinaryLog(entsize, record_types=record_types,
                               store_cb=store.store_cb,
                               retrieve_cb=store.retrieve_cb)
        # Make sure the log is empty
        entries = log.get()
        self.assertEqual(len(entries), 0)
        # Reload the log
        store.store_cb(data)
        log.reload()
        # Make sure the log contains our entry
        entries = log.get()
        self.assertEqual(len(entries), 1)
        self.assertIn([FAKE_TIMESTAMP, "INFO", "T1 1 -1"], entries)

    def test_SeverityLevels(self):
        record_types = [ TEST_ENTRY1 ]
        entsize = binlog.ENTRY_SIZE
        log = binlog.BinaryLog(entsize, record_types=record_types)
        # Make an info entry
        with mock.patch('time.time', return_value=FAKE_TIMESTAMP):
            log.info(TEST_ENTRY1, 1, -1)
        # Make sure the log contains our entry
        entries = log.get()
        self.assertEqual(len(entries), 1)
        self.assertIn([FAKE_TIMESTAMP, "INFO", "T1 1 -1"], entries)
        # Make a warning entry
        with mock.patch('time.time', return_value=FAKE_TIMESTAMP):
            log.warn(TEST_ENTRY1, 1, -1)
        # Make sure the log contains our entry
        entries = log.get()
        self.assertEqual(len(entries), 1)
        self.assertIn([FAKE_TIMESTAMP, "WARNING", "T1 1 -1"], entries)
        # Make an error entry
        with mock.patch('time.time', return_value=FAKE_TIMESTAMP):
            log.error(TEST_ENTRY1, 1, -1)
        # Make sure the log contains our entry
        entries = log.get()
        self.assertEqual(len(entries), 1)
        self.assertIn([FAKE_TIMESTAMP, "ERROR", "T1 1 -1"], entries)
