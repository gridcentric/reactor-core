#
# Reactor unittesting harness.
#
# This module MUST be imported before any other reactor modules from
# the toplevel unit test source file. This is because we manually set
# up some import paths before the rest of reactor starts importing
# reactor modules.
#

import time
import inspect
import os
import sys
import logging
from threading import Condition
from functools import wraps
from uuid import uuid4

# Patch up python module path.
sys.path.insert(0, os.path.abspath("../.."))

# Manually load the python-zookeeper library. We need to resort to
# doing this to avoid having the reactor zookeeper module load
# instead, since we just added the entire reactor tree to the modules
# path.
import imp
zookeeper = imp.load_dynamic("zookeeper",
    "/usr/lib/python2.7/dist-packages/zookeeper.so")

# Important: Load all reactor modules below this point, now that it's safe to
# import reactor's zookeeper module.
from reactor.zookeeper import connection
from reactor.testing.mock_cloud import MockCloudConnection

# Enable debug-level logging.
logging.basicConfig(format="%(asctime)s %(levelname)s: %(message)s",
    level=logging.DEBUG)

# Open the testing zookeeper handle. We'll just take advantage of the
# reactor zookeeper code to do this for now.
LOCAL_ZK_ADDRESS = "localhost:2181"
LOCAL_ZK_HANDLE = connection.connect([LOCAL_ZK_ADDRESS])
REACTOR_ZK_ROOT_PREFIX = "/reactor-unittest-"

# Enable debug-level logging
logging.basicConfig(format="%(asctime)s %(levelname)s: %(message)s",
    level=logging.DEBUG)

def zookeeper_recursive_delete(path):
    logging.debug("Recursively deleting zk path %s" % path)
    if not zookeeper.exists(LOCAL_ZK_HANDLE, path):
        return

    def recursive_delete(target_path):
        for child in zookeeper.get_children(LOCAL_ZK_HANDLE, target_path):
            recursive_delete(os.path.join(target_path, child))
        zookeeper.delete(LOCAL_ZK_HANDLE, target_path)
    recursive_delete(path)

def zookeeper_global_testroot_cleanup():
    ROOT = "/"
    for path in [ os.path.join(ROOT, p) for p in \
        zookeeper.get_children(LOCAL_ZK_HANDLE, ROOT) ]:
        if path.startswith(REACTOR_ZK_ROOT_PREFIX):
            logging.debug("Deleting stale zk root %s")
            zookeeper_recursive_delete(path)

# Delete all stale test roots we find (probably left over from previously
# failed/crashed tests). If we collide with a stale name, the test will fail
# since the resulting zookeeper state is ambiguous.
zookeeper_global_testroot_cleanup()

def make_zk_testroot(idstr):
    path = REACTOR_ZK_ROOT_PREFIX + idstr + "-" + str(uuid4())
    zookeeper.create(LOCAL_ZK_HANDLE, path, '',
                     [connection.ZOO_OPEN_ACL_UNSAFE],
                     0)
    return path

def start_instance(scale_manager, endpoint, ip=None, instance_id=None, name=None):
    # We only know how to start instances on a mock cloud.
    assert isinstance(endpoint.cloud_conn, MockCloudConnection)
    instance = endpoint.cloud_conn.start_instance(
        endpoint.config,
        ip=ip,
        instance_id=instance_id,
        name=name)
    scale_manager.add_endpoint_instance(
        endpoint.name,
        endpoint.cloud_conn.id(endpoint.config, instance),
        endpoint.cloud_conn.name(endpoint.config, instance))
    return instance

class ZkEvent(object):
    def __init__(self, zk_conn, path, expt_value=None):
        self.zk_conn = zk_conn
        self.path = path
        self.cond = Condition()
        self.result = None
        self.expt_value = expt_value

    def __call__(self, result):
        self.cond.acquire()
        try:
            if self.expt_value is not None:
                if result != self.expt_value:
                    logging.warning(
                        "Got zk event with result %s, didn't match expt result %s." % \
                            (str(result), str(self.expt_value)))
                    return
            self.result = result
            self.cond.notifyAll()
        finally:
            self.cond.release()

    def __enter__(self):
        # Since we're running a test where we expect a particular zookeeper
        # event, there better be reactor callbacks registered for the path.
        self.zk_conn.watches[self.path].append(self)
        return self

    def __exit__(self, *args):
        self.wait()
        self.zk_conn.watches[self.path] = \
            [ fn for fn in self.zk_conn.watches[self.path] if fn != self ]

    def wait(self):
        self.cond.acquire()
        logging.debug("Waiting for zk event on path '%s'." % self.path)
        while self.result is None:
            self.cond.wait()
        logging.debug("Observed zk event on path '%s'." % self.path)
        self.cond.release()

