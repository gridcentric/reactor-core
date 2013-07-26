import sys
import unittest

import reactor.endpoint as endpoint

def test_single_manager(endpoint, scale_manager):
    assert scale_manager.endpoint_owned(endpoint)

def test_multiple_managers(endpoint, scale_managers):
    assert len(scale_managers) > 1
    owners = [m for m in scale_managers if m.endpoint_owned(endpoint)]
    assert len(owners) == 1
