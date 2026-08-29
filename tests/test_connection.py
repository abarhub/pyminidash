import logging

import httpx
import pytest

from pyminidash.config import Config, ConfigError
from pyminidash.connection import Connection, build_connections


def _config(**conn):
    return Config.model_validate({
        "connections": {"jira": {"base_url": "https://jira.example.com", "token": "jira", **conn}},
        "groups": [{"id": "g", "title": "G", "type": "table",
                    "blocks": [{"provider": "disk_usage", "params": {"paths": ["."]}}]}],
    })


def test_build_resolves_token():
    conns = build_connections(_config(), {"jira": "SECRET-PAT"})
    assert conns["jira"].token == "SECRET-PAT"
    assert conns["jira"].base_url == "https://jira.example.com"


def test_missing_token_raises():
    with pytest.raises(ConfigError, match="absente de secrets.toml"):
        build_connections(_config(), {})


def test_missing_token_error_does_not_echo_field_value():
    # le message ne doit pas ré-afficher une valeur collée dans le champ token
    with pytest.raises(ConfigError) as exc:
        build_connections(_config(), {"autre": "x"})
    assert "clés disponibles : autre" in str(exc.value)


def test_empty_token_value_raises():
    with pytest.raises(ConfigError, match="vide"):
        build_connections(_config(), {"jira": "   "})


def test_verify_false_logs_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="pyminidash.connection"):
        build_connections(_config(verify=False), {"jira": "x"})
    assert any(
        "verify" in r.getMessage() and r.levelno == logging.WARNING
        for r in caplog.records
    )


def test_missing_ca_file_raises(tmp_path):
    with pytest.raises(ConfigError, match="CA"):
        build_connections(_config(verify=str(tmp_path / "absent.pem")), {"jira": "x"})


def test_existing_ca_file_ok(tmp_path):
    ca = tmp_path / "ca.pem"
    ca.write_text("-----BEGIN CERTIFICATE-----\n", encoding="utf-8")
    conns = build_connections(_config(verify=str(ca)), {"jira": "x"})
    assert conns["jira"].verify == str(ca)


def test_repr_hides_token():
    c = Connection(name="jira", base_url="https://x", token="SUPER-SECRET")
    assert "SUPER-SECRET" not in repr(c)
    assert "token=***" in repr(c)


def test_client_sets_bearer_header_and_base_url():
    c = Connection(name="jira", base_url="https://jira.example.com", token="PAT123")
    with c.client() as client:
        assert client.headers["authorization"] == "Bearer PAT123"
        assert client.headers["accept"] == "application/json"
        assert str(client.base_url) == "https://jira.example.com"


def test_client_passes_verify_false():
    c = Connection(name="jira", base_url="https://x", token="t", verify=False)
    with c.client() as client:  # ne lève pas
        assert isinstance(client, httpx.Client)
