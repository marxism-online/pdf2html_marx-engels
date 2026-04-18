import pytest
from pdf2html.cli import parse_pages_spec

def test_pages_none():
    assert parse_pages_spec(None) is None
    assert parse_pages_spec("") is None

def test_pages_single():
    assert parse_pages_spec("5") == {5}

def test_pages_range():
    assert parse_pages_spec("5-7") == {5,6,7}

def test_pages_list_and_ranges():
    assert parse_pages_spec("1,3,10-12") == {1,3,10,11,12}

def test_pages_reverse_range():
    assert parse_pages_spec("7-5") == {5,6,7}

def test_pages_invalid_zero():
    with pytest.raises(ValueError):
        parse_pages_spec("0")

