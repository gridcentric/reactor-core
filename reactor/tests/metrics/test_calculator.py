import pytest

from reactor.metrics.calculator import EndpointCriteria

def test_empty():
    x = EndpointCriteria("")
    assert str(x) == "None => (None,None)"

def test_noop():
    x = EndpointCriteria("foo")
    assert str(x) == "foo => (None,None)"

def test_two_metrics():
    x = EndpointCriteria("foo bahh")
    assert str(x) == "None => (None,None)"

def test_bad_number():
    x = EndpointCriteria("foo < 4.")
    assert str(x) == "None => (None,None)"

def test_bad_op():
    x = EndpointCriteria("foo == 4")
    assert str(x) == "None => (None,None)"

def test_upper_equals():
    x = EndpointCriteria("foo <= 4.0")
    assert str(x) == "foo => (None,4.0]"

def test_upper_less():
    x = EndpointCriteria("foo < 4.0")
    assert str(x) == "foo => (None,4.0)"

def test_lower_equals():
    x = EndpointCriteria("1.0 <= foo")
    assert str(x) == "foo => [1.0,None)"

def test_lower_less():
    x = EndpointCriteria("1.0 < foo")
    assert str(x) == "foo => (1.0,None)"

def test_both_equals():
    x = EndpointCriteria("1.0 <= foo <= 2.0")
    assert str(x) == "foo => [1.0,2.0]"

def test_both_less():
    x = EndpointCriteria("1.0 < foo < 2.0")
    assert str(x) == "foo => (1.0,2.0)"
