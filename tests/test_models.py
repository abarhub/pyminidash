from datetime import datetime

from pyminidash.models import (
    Field, FieldRole, FieldType, Record, StatusLevel,
    bytes_, datetime_, duration, link, number, percent, status, text, title,
)


def test_text_helper_defaults():
    f = text("name", "Nom", "chrome")
    assert f == Field(key="name", label="Nom", value="chrome", type=FieldType.TEXT)
    assert f.role is FieldRole.NORMAL
    assert f.summary is False


def test_title_helper_sets_role():
    f = title("mount", "Disque", "C:\\")
    assert f.role is FieldRole.TITLE
    assert f.type is FieldType.TEXT


def test_status_helper_requires_level_and_defaults_to_badge():
    f = status("state", "État", "UP", level=StatusLevel.OK, summary=True)
    assert f.type is FieldType.STATUS
    assert f.level is StatusLevel.OK
    assert f.role is FieldRole.BADGE
    assert f.summary is True


def test_link_helper_carries_url():
    f = link("url", "URL", "voir", "https://example.test")
    assert f.type is FieldType.LINK
    assert f.url == "https://example.test"


def test_typed_helpers_set_their_type():
    assert number("n", "N", 3).type is FieldType.NUMBER
    assert bytes_("b", "B", 1024).type is FieldType.BYTES
    assert percent("p", "P", 50).type is FieldType.PERCENT
    assert datetime_("d", "D", datetime(2026, 1, 1)).type is FieldType.DATETIME
    assert duration("t", "T", 90).type is FieldType.DURATION


def test_record_keys_and_equality():
    r1 = Record(text("a", "A", "1"), text("b", "B", "2"))
    r2 = Record(text("a", "A", "1"), text("b", "B", "2"))
    assert r1 == r2
    assert r1.keys() == ("a", "b")


def test_field_is_frozen():
    import dataclasses
    import pytest
    f = text("a", "A", "1")
    with pytest.raises(dataclasses.FrozenInstanceError):
        f.value = "2"
