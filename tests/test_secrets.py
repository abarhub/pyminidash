import sys

import pytest

from pyminidash.secrets import SecretsError, load_secrets


def test_missing_file_returns_empty(tmp_path):
    assert load_secrets(tmp_path / "absent.toml") == {}


def test_reads_flat_table(tmp_path):
    p = tmp_path / "secrets.toml"
    p.write_text('jira = "abc"\nbitbucket = "def"\n', encoding="utf-8")
    assert load_secrets(p) == {"jira": "abc", "bitbucket": "def"}


def test_invalid_toml_raises(tmp_path):
    p = tmp_path / "secrets.toml"
    p.write_text("this is = = broken", encoding="utf-8")
    with pytest.raises(SecretsError, match="TOML"):
        load_secrets(p)


def test_non_string_value_raises(tmp_path):
    p = tmp_path / "secrets.toml"
    p.write_text('jira = 123\n', encoding="utf-8")
    with pytest.raises(SecretsError, match="jira"):
        load_secrets(p)


def test_nested_table_value_raises(tmp_path):
    p = tmp_path / "secrets.toml"
    p.write_text('[jira]\ntoken = "x"\n', encoding="utf-8")
    with pytest.raises(SecretsError, match="jira"):
        load_secrets(p)


@pytest.mark.skipif(sys.platform == "win32", reason="permissions POSIX")
def test_world_readable_warns(tmp_path, caplog):
    import logging
    p = tmp_path / "secrets.toml"
    p.write_text('jira = "abc"\n', encoding="utf-8")
    p.chmod(0o644)
    with caplog.at_level(logging.WARNING, logger="pyminidash.secrets"):
        load_secrets(p)
    assert any("chmod" in r.message or "lisible" in r.message for r in caplog.records)
