import textwrap

import pytest

from pyminidash.config import ConfigError, load_config
from pyminidash.models import Record, text, title
from pyminidash.registry import provider


@pytest.fixture
def conn_providers():
    @provider("needs_conn")
    def needs_conn(connection, q: str):
        return [Record(title("k", "K", q))]

    @provider("opt_conn")
    def opt_conn(connection=None, q: str = "x"):
        return [Record(title("k", "K", q))]

    return ["needs_conn", "opt_conn"]


def _write(tmp_path, body):
    p = tmp_path / "config.toml"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


def test_valid_connection_and_block(tmp_path, conn_providers):
    p = _write(tmp_path, """
        [connections.jira]
        base_url = "https://jira.example.com/"
        token = "jira"

        [[groups]]
        id = "g"
        title = "G"
        type = "table"
          [[groups.blocks]]
          provider = "needs_conn"
          connection = "jira"
          params = { q = "hi" }
    """)
    cfg = load_config(p)
    assert cfg.connections["jira"].base_url == "https://jira.example.com"  # slash retiré
    assert cfg.groups[0].blocks[0].connection == "jira"


def test_bad_base_url(tmp_path, conn_providers):
    p = _write(tmp_path, """
        [connections.jira]
        base_url = "pas-une-url"
        token = "jira"
        [[groups]]
        id = "g"
        title = "G"
        type = "table"
          [[groups.blocks]]
          provider = "opt_conn"
    """)
    with pytest.raises(ConfigError, match="base_url"):
        load_config(p)


def test_provider_requires_connection(tmp_path, conn_providers):
    p = _write(tmp_path, """
        [[groups]]
        id = "g"
        title = "G"
        type = "table"
          [[groups.blocks]]
          provider = "needs_conn"
          params = { q = "hi" }
    """)
    with pytest.raises(ConfigError, match="exige connection"):
        load_config(p)


def test_unknown_connection(tmp_path, conn_providers):
    p = _write(tmp_path, """
        [[groups]]
        id = "g"
        title = "G"
        type = "table"
          [[groups.blocks]]
          provider = "needs_conn"
          connection = "nope"
          params = { q = "hi" }
    """)
    with pytest.raises(ConfigError, match="connexion inconnue 'nope'"):
        load_config(p)


def test_connection_on_provider_that_refuses_it(tmp_path, conn_providers):
    p = _write(tmp_path, """
        [connections.jira]
        base_url = "https://jira.example.com"
        token = "jira"
        [[groups]]
        id = "g"
        title = "G"
        type = "table"
          [[groups.blocks]]
          provider = "disk_usage"
          connection = "jira"
          params = { paths = ["."] }
    """)
    with pytest.raises(ConfigError, match="n'utilise pas de connexion"):
        load_config(p)


def test_connection_in_params_is_rejected(tmp_path, conn_providers):
    p = _write(tmp_path, """
        [connections.jira]
        base_url = "https://jira.example.com"
        token = "jira"
        [[groups]]
        id = "g"
        title = "G"
        type = "table"
          [[groups.blocks]]
          provider = "needs_conn"
          connection = "jira"
          params = { connection = "jira", q = "hi" }
    """)
    with pytest.raises(ConfigError, match="injecté"):
        load_config(p)


def test_optional_connection_block_without_connection_ok(tmp_path, conn_providers):
    p = _write(tmp_path, """
        [[groups]]
        id = "g"
        title = "G"
        type = "table"
          [[groups.blocks]]
          provider = "opt_conn"
    """)
    load_config(p)  # ne lève pas
