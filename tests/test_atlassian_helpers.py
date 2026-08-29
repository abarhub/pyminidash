import httpx
import pytest
import respx

from pyminidash.connection import Connection
from pyminidash.models import FieldType, StatusLevel
from pyminidash.providers._atlassian import (
    ApiError, AuthError, ConnError, NotFoundError, count_record, get_json,
)

CONN = Connection(name="jira", base_url="https://jira.example.com", token="PAT")


@respx.mock
def test_get_json_ok():
    respx.get("https://jira.example.com/x").mock(
        return_value=httpx.Response(200, json={"a": 1})
    )
    assert get_json(CONN, "/x") == {"a": 1}


@respx.mock
def test_get_json_401_is_auth_error_without_token():
    respx.get("https://jira.example.com/x").mock(return_value=httpx.Response(401))
    with pytest.raises(AuthError) as exc:
        get_json(CONN, "/x")
    assert "jira" in str(exc.value)
    assert "PAT" not in str(exc.value)


@respx.mock
def test_get_json_404():
    respx.get("https://jira.example.com/x").mock(return_value=httpx.Response(404))
    with pytest.raises(NotFoundError):
        get_json(CONN, "/x")


@respx.mock
def test_get_json_400_uses_api_message():
    respx.get("https://jira.example.com/x").mock(return_value=httpx.Response(
        400, json={"errorMessages": ["JQL invalide : champ 'foo' inconnu"]}
    ))
    with pytest.raises(ApiError, match="JQL invalide"):
        get_json(CONN, "/x")


@respx.mock
def test_get_json_connect_error():
    respx.get("https://jira.example.com/x").mock(
        side_effect=httpx.ConnectError("refused")
    )
    with pytest.raises(ConnError):
        get_json(CONN, "/x")


def test_get_json_ssl_error_mentions_tls():
    # respx overwrites __cause__/__context__ of any exception it raises (it
    # chains its own SideEffectError), so the SSL cause cannot survive a respx
    # side_effect. Use a fake client that raises the ConnectError directly, the
    # way real httpx wraps an ssl.SSLError on certificate rejection.
    import ssl

    err = httpx.ConnectError("tls")
    err.__cause__ = ssl.SSLError("bad cert")

    class _FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get(self, path, params=None):
            raise err

    class _FakeConn:
        name = "jira"
        base_url = "https://jira.example.com"

        def client(self, timeout=15.0):
            return _FakeClient()

    with pytest.raises(ConnError, match="TLS"):
        get_json(_FakeConn(), "/x")


@respx.mock
def test_get_json_timeout_is_conn_error():
    respx.get("https://jira.example.com/x").mock(
        side_effect=httpx.ReadTimeout("slow")
    )
    with pytest.raises(ConnError) as exc:
        get_json(CONN, "/x")
    assert "délai" in str(exc.value)
    assert "jira" in str(exc.value)


@respx.mock
def test_get_json_500_is_generic_api_error():
    respx.get("https://jira.example.com/x").mock(return_value=httpx.Response(500))
    with pytest.raises(ApiError) as exc:
        get_json(CONN, "/x")
    assert "500" in str(exc.value)
    assert not isinstance(exc.value, (AuthError, NotFoundError))


@respx.mock
def test_get_json_400_errors_dict_branch():
    respx.get("https://jira.example.com/x").mock(return_value=httpx.Response(
        400, json={"errors": {"jql": "champ inconnu"}}
    ))
    with pytest.raises(ApiError, match="jql"):
        get_json(CONN, "/x")


@respx.mock
def test_get_json_400_message_string_branch():
    respx.get("https://jira.example.com/x").mock(return_value=httpx.Response(
        400, json={"message": "requête malformée"}
    ))
    with pytest.raises(ApiError, match="malformée"):
        get_json(CONN, "/x")


@respx.mock
def test_get_json_non_json_2xx():
    respx.get("https://jira.example.com/x").mock(
        return_value=httpx.Response(200, text="<html>not json</html>")
    )
    with pytest.raises(ApiError, match="non-JSON"):
        get_json(CONN, "/x")


@respx.mock
def test_get_json_3xx_redirect_is_api_error():
    respx.get("https://jira.example.com/x").mock(
        return_value=httpx.Response(302, headers={"Location": "/login"})
    )
    with pytest.raises(ApiError, match="redirection"):
        get_json(CONN, "/x")


def test_count_record_thresholds():
    r_ok = count_record("Total", 3, warn_above=5, error_above=10)
    assert r_ok.fields[0].type is FieldType.STATUS
    assert r_ok.fields[0].level is StatusLevel.OK
    assert r_ok.fields[0].value == "3"
    assert count_record("T", 7, warn_above=5, error_above=10).fields[0].level is StatusLevel.WARN
    assert count_record("T", 12, warn_above=5, error_above=10).fields[0].level is StatusLevel.ERROR
    assert count_record("T", 99).fields[0].level is StatusLevel.OK  # pas de seuil


from datetime import datetime, timezone

from pyminidash.providers._atlassian import (
    epoch_ms_to_dt, paginate_v1, parse_iso, strip_html,
)


def test_strip_html():
    assert strip_html('Manual run by <a href="x">Jean Dupont</a>') == "Manual run by Jean Dupont"
    assert strip_html("d&eacute;clench&eacute;") == "déclenché"
    assert strip_html("") == ""
    assert strip_html(None) == ""


def test_epoch_ms_to_dt():
    dt = epoch_ms_to_dt(1_724_500_000_000)
    assert dt is not None and dt.tzinfo is timezone.utc and dt.year == 2024
    assert epoch_ms_to_dt("1724500000000").year == 2024
    assert epoch_ms_to_dt(None) is None
    assert epoch_ms_to_dt("nope") is None


def test_parse_iso():
    assert parse_iso("") is None
    assert parse_iso("2026-08-20T14:30:00Z").hour == 14
    dt = parse_iso("2026-08-20T14:30:00.000+0200")
    assert dt.year == 2026 and dt.hour == 14
    assert parse_iso("pas une date") == "pas une date"


@respx.mock
def test_paginate_v1_walks_pages():
    route = respx.get("https://jira.example.com/x")
    route.side_effect = [
        httpx.Response(200, json={"values": [{"id": 1}, {"id": 2}], "isLastPage": False, "nextPageStart": 2}),
        httpx.Response(200, json={"values": [{"id": 3}], "isLastPage": True}),
    ]
    got = list(paginate_v1(CONN, "/x"))
    assert [v["id"] for v in got] == [1, 2, 3]
    assert route.call_count == 2


@respx.mock
def test_paginate_v1_rejects_non_dict_page():
    respx.get("https://jira.example.com/x").mock(
        return_value=httpx.Response(200, json=[1, 2, 3])
    )
    with pytest.raises(ApiError, match="réponse inattendue"):
        list(paginate_v1(CONN, "/x"))


@respx.mock
def test_paginate_v1_respects_hard_cap():
    respx.get("https://jira.example.com/x").mock(return_value=httpx.Response(
        200, json={"values": [{"id": i} for i in range(100)], "isLastPage": False, "nextPageStart": 100}
    ))
    got = list(paginate_v1(CONN, "/x", hard_cap=5))
    assert len(got) == 5
