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


def test_count_record_thresholds():
    r_ok = count_record("Total", 3, warn_above=5, error_above=10)
    assert r_ok.fields[0].type is FieldType.STATUS
    assert r_ok.fields[0].level is StatusLevel.OK
    assert r_ok.fields[0].value == "3"
    assert count_record("T", 7, warn_above=5, error_above=10).fields[0].level is StatusLevel.WARN
    assert count_record("T", 12, warn_above=5, error_above=10).fields[0].level is StatusLevel.ERROR
    assert count_record("T", 99).fields[0].level is StatusLevel.OK  # pas de seuil
