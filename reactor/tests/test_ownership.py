import sys
import unittest

import reactor.endpoint as endpoint

def test_single_manager(endpoint, manager):
    assert manager.endpoint_owned(endpoint)

def test_multiple_managers(endpoint, managers):
    assert len(managers) > 1
    owners = [m for m in managers if m.endpoint_owned(endpoint)]
    assert len(owners) == 1
