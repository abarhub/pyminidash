import textwrap

import pytest

from pyminidash.config import ConfigError, load_config


def _write(tmp_path, body: str):
    p = tmp_path / "config.toml"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


def test_missing_file(tmp_path):
    with pytest.raises(ConfigError, match="introuvable"):
        load_config(tmp_path / "absent.toml")


def test_invalid_toml(tmp_path, dummy_providers):
    p = _write(tmp_path, "this is = = not toml")
    with pytest.raises(ConfigError, match="TOML"):
        load_config(p)


def test_valid_config_resolves_defaults(tmp_path, dummy_providers):
    p = _write(tmp_path, """
        [[groups]]
        id = "g1"
        title = "Groupe 1"
        type = "table"
          [[groups.blocks]]
          provider = "dummy_rows"
          params = { n = 3 }
    """)
    cfg = load_config(p)
    assert cfg.app.title == "pyminidash"
    assert cfg.app.default_group == "g1"          # défaut = 1er groupe
    assert cfg.groups[0].blocks[0].title == "dummy_rows"  # défaut = nom du provider


def test_duplicate_group_id(tmp_path, dummy_providers):
    p = _write(tmp_path, """
        [[groups]]
        id = "dup"
        title = "A"
        type = "table"
          [[groups.blocks]]
          provider = "dummy_rows"
        [[groups]]
        id = "dup"
        title = "B"
        type = "cards"
          [[groups.blocks]]
          provider = "dummy_rows"
    """)
    with pytest.raises(ConfigError, match="double"):
        load_config(p)


def test_unknown_default_group(tmp_path, dummy_providers):
    p = _write(tmp_path, """
        [app]
        default_group = "nope"
        [[groups]]
        id = "g1"
        title = "A"
        type = "table"
          [[groups.blocks]]
          provider = "dummy_rows"
    """)
    with pytest.raises(ConfigError, match="default_group"):
        load_config(p)


def test_unknown_provider(tmp_path, dummy_providers):
    p = _write(tmp_path, """
        [[groups]]
        id = "g1"
        title = "A"
        type = "table"
          [[groups.blocks]]
          provider = "does_not_exist"
    """)
    with pytest.raises(ConfigError, match="does_not_exist"):
        load_config(p)


def test_bad_params(tmp_path, dummy_providers):
    p = _write(tmp_path, """
        [[groups]]
        id = "g1"
        title = "A"
        type = "table"
          [[groups.blocks]]
          provider = "dummy_rows"
          params = { unexpected = 1 }
    """)
    with pytest.raises(ConfigError, match="signature attendue"):
        load_config(p)


def test_bad_group_type(tmp_path, dummy_providers):
    p = _write(tmp_path, """
        [[groups]]
        id = "g1"
        title = "A"
        type = "grid"
          [[groups.blocks]]
          provider = "dummy_rows"
    """)
    with pytest.raises(ConfigError):
        load_config(p)


def test_non_positive_timeout_rejected(tmp_path, dummy_providers):
    p = _write(tmp_path, """
        [[groups]]
        id = "g1"
        title = "A"
        type = "table"
          [[groups.blocks]]
          provider = "dummy_rows"
          timeout = 0
    """)
    with pytest.raises(ConfigError):
        load_config(p)

    p2 = _write(tmp_path, """
        [[groups]]
        id = "g1"
        title = "A"
        type = "table"
          [[groups.blocks]]
          provider = "dummy_rows"
          timeout = -1
    """)
    with pytest.raises(ConfigError):
        load_config(p2)


def test_empty_blocks_rejected(tmp_path, dummy_providers):
    p = _write(tmp_path, """
        [[groups]]
        id = "g1"
        title = "A"
        type = "table"
        blocks = []
    """)
    with pytest.raises(ConfigError):
        load_config(p)
