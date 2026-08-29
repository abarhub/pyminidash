import httpx
import pytest
import respx

from pyminidash.models import FieldType, StatusLevel
from pyminidash.providers.http import _check_level, _dig, http_check, http_json


def test_dig():
    assert _dig({"a": {"b": 1}}, "$") == {"a": {"b": 1}}
    assert _dig({"a": {"b": 1}}, "a.b") == 1
    assert _dig({"a": {}}, "a.b.c") is None


def test_check_level():
    assert _check_level(None, 0.1) == ("DOWN", StatusLevel.ERROR)
    assert _check_level(503, 0.1) == ("HTTP 503", StatusLevel.ERROR)
    assert _check_level(200, 0.9) == ("SLOW", StatusLevel.WARN)
    assert _check_level(200, 0.05) == ("UP", StatusLevel.OK)


@respx.mock
def test_http_check_up_and_down():
    respx.get("https://ok.test/").mock(return_value=httpx.Response(200))
    respx.get("https://bad.test/").mock(side_effect=httpx.ConnectError("refused"))

    records = http_check(["https://ok.test/", "https://bad.test/"])
    assert records[0].keys() == (
        "host", "state", "code", "latency", "url", "error", "checked_at"
    )
    assert records[0].fields[1].value == "UP"
    assert records[0].fields[1].type is FieldType.STATUS
    assert records[1].fields[1].value == "DOWN"
    assert "refused" in records[1].fields[5].value


@respx.mock
def test_http_json_extracts_rows_and_columns():
    respx.get("https://api.test/users").mock(return_value=httpx.Response(
        200, json=[
            {"name": "Léa", "company": {"name": "Acme"}},
            {"name": "Sam", "company": {"name": "Globex"}},
        ],
    ))
    records = http_json("https://api.test/users", rows_path="$",
                        columns=["name", "company.name"])
    assert len(records) == 2
    assert records[0].keys() == ("name", "company.name")
    assert records[0].fields[0].value == "Léa"
    assert records[0].fields[1].value == "Acme"
    assert records[0].fields[1].label == "name"


@respx.mock
def test_http_json_raises_on_5xx():
    respx.get("https://api.test/boom").mock(return_value=httpx.Response(500))
    with pytest.raises(httpx.HTTPStatusError):
        http_json("https://api.test/boom", rows_path="$", columns=["x"])


@respx.mock
def test_http_json_raises_when_rows_not_a_list():
    respx.get("https://api.test/obj").mock(return_value=httpx.Response(
        200, json={"not": "a list"}))
    with pytest.raises(ValueError):
        http_json("https://api.test/obj", rows_path="$", columns=["x"])
