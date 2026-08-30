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


def _config_multi():
    return Config.model_validate({
        "connections": {
            "jira": {"base_url": "https://jira.example.com", "token": "jira"},
            "bamboo": {"base_url": "https://bamboo.example.com", "token": "bamboo"},
        },
        "groups": [{"id": "g", "title": "G", "type": "table",
                    "blocks": [{"provider": "disk_usage", "params": {"paths": ["."]}}]}],
    })


def test_build_resolves_token():
    conns = build_connections(_config(), {"jira": "SECRET-PAT"})
    assert conns["jira"].token == "SECRET-PAT"
    assert conns["jira"].base_url == "https://jira.example.com"


def test_missing_token_disables_connection(caplog):
    # token absent de secrets.toml → connexion ignorée, serveur démarre quand même
    with caplog.at_level(logging.WARNING, logger="pyminidash.connection"):
        conns = build_connections(_config(), {})
    assert "jira" not in conns
    assert any(
        "jira" in r.getMessage() and r.levelno == logging.WARNING
        for r in caplog.records
    )


def test_empty_token_value_disables_connection(caplog):
    with caplog.at_level(logging.WARNING, logger="pyminidash.connection"):
        conns = build_connections(_config(), {"jira": "   "})
    assert "jira" not in conns
    assert any("jira" in r.getMessage() for r in caplog.records)


def test_partial_secrets_build_available_connections(caplog):
    # une connexion renseignée, l'autre non → seule la renseignée est construite
    with caplog.at_level(logging.WARNING, logger="pyminidash.connection"):
        conns = build_connections(_config_multi(), {"jira": "PAT"})
    assert set(conns) == {"jira"}
    assert conns["jira"].token == "PAT"
    assert any("bamboo" in r.getMessage() for r in caplog.records)


def test_no_missing_token_no_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="pyminidash.connection"):
        build_connections(_config_multi(), {"jira": "a", "bamboo": "b"})
    assert not any(
        "désactivée" in r.getMessage() or "token absent" in r.getMessage()
        for r in caplog.records
    )


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
