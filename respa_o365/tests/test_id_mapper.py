import pytest

from respa_o365.id_mapper import IdMapper


def test__reverse_get__return_the_key__when_value_has_been_set():
    d = IdMapper()
    d["a"] = 1
    assert d.reverse[1] == "a"

def test__reverse_get__raises_key_error__when_item_is_deleted():
    d = IdMapper()
    d["a"] = 1
    del d.reverse[1]
    with pytest.raises(KeyError):
        assert d.reverse["a"]

def test__additions__return_items_added():
    d = IdMapper()
    d["a"] = 1
    assert [(k, v) for k, v in d.additions()] == [("a", 1)]

def test__additions__return_items_added__when_added_using_reverse_map():
    d = IdMapper()
    d.reverse[1] = "a"
    assert [(k, v) for k, v in d.additions()] == [("a", 1)]

def test__additions__return_items_added__when_changed_multiple_times():
    d = IdMapper()
    d["a"] = 1
    d["a"] = 2
    d["a"] = 3
    assert [(k, v) for k, v in d.additions()] == [("a", 3)]

def test__removals__return_items_removed():
    d = IdMapper({"b": 2})
    del d["b"]
    assert [(k, v) for k, v in d.removals()] == [("b", 2)]

def test__removals__return_items_removed__when_removed_using_reversed_map():
    d = IdMapper({"b": 2})
    del d.reverse[2]
    assert [(k, v) for k, v in d.removals()] == [("b", 2)]

def test__changes__returns_changed_items():
    d = IdMapper({"b": 2})
    d["b"] = 3
    assert [(k, v) for k, v in d.changes()] == [("b", 3)]

def test__changes__returns_changed_items__when_changed_using_reverse_map():
    d = IdMapper({"b": 2})
    d.reverse[3] = "b"
    assert [(k, v) for k, v in d.changes()] == [("b", 3)]

def test__changes__returns_none__when_value_has_not_changed():
    d = IdMapper({"b": 2})
    d["b"] = 2
    assert [(k, v) for k, v in d.changes()] == []

def test__removals__returns_no_items__when_added_item_is_added_and_removed():
    d = IdMapper()
    d["a"] = 1
    del d["a"]
    assert [(k, v) for k, v in d.removals()] == []
    assert [(k, v) for k, v in d.additions()] == []

def test__changes__returns_item__when_it_is_first_deleted_and_then_changed():
    d = IdMapper({"a": 1})
    del d["a"]
    d["a"] = 2
    assert [(k, v) for k, v in d.removals()] == []
    assert [(k, v) for k, v in d.additions()] == []
    assert [(k, v) for k, v in d.changes()] == [("a", 2)]

def test__removals_nor_changes__returns_no_items__when_item_is_put_back():
    d = IdMapper({"a": 1})
    del d["a"]
    d["a"] = 1
    assert [(k, v) for k, v in d.removals()] == []
    assert [(k, v) for k, v in d.additions()] == []
    assert [(k, v) for k, v in d.changes()] == []



