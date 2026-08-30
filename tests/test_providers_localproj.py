import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

from pyminidash.config import ConfigError, load_config
from pyminidash.providers.localproj import local_projects
from pyminidash.providers.localproj.record import KNOWN_FIELDS


def _touch(p: Path, content: str = "x"):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


@pytest.fixture
def tree(tmp_path):
    _touch(tmp_path / "svc" / "pom.xml",
           '<project xmlns="http://maven.apache.org/POM/4.0.0">'
           '<groupId>g</groupId><artifactId>svc</artifactId>'
           '<version>1.0</version></project>')
    _touch(tmp_path / "front" / "package.json",
           '{"name": "front", "version": "2.0.0"}')
    _touch(tmp_path / "tool" / "go.mod", "module ex.com/tool\ngo 1.22\n")
    return tmp_path


def test_returns_homogeneous_records(tree):
    recs = local_projects([str(tree)])
    assert len(recs) == 3
    assert all(r.keys() == KNOWN_FIELDS for r in recs)


def test_sorted_by_name(tree):
    recs = local_projects([str(tree)])
    names = [next(f.value for f in r.fields if f.key == "name") for r in recs]
    assert names == sorted(names, key=str.lower)


def test_show_restricts_columns(tree):
    recs = local_projects([str(tree)], show=["version", "branch"])
    assert all(r.keys() == ("name", "version", "branch") for r in recs)


def test_missing_root_is_provider_error(tmp_path):
    from pyminidash.errors import ProviderError
    with pytest.raises(ProviderError):
        local_projects([str(tmp_path / "absent")])


@pytest.mark.skipif(shutil.which("git") is None, reason="git absent")
def test_git_fields_populated(tmp_path):
    r = tmp_path / "repo"
    _touch(r / "go.mod", "module ex.com/r\ngo 1.21\n")
    for args in (("init", "-b", "main"), ("config", "user.email", "a@a.aa"),
                 ("config", "user.name", "A"), ("add", "."),
                 ("commit", "-m", "init")):
        subprocess.run(("git", *args), cwd=r, check=True, capture_output=True)
    rec = local_projects([str(tmp_path)])[0]
    by = {f.key: f.value for f in rec.fields}
    assert by["branch"] == "main"
    assert by["dirty"] == "propre"


def _write_cfg(tmp_path, body):
    p = tmp_path / "config.toml"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


def test_config_rejects_unknown_show_key(tmp_path):
    p = _write_cfg(tmp_path, """
        [[groups]]
        id = "g"
        title = "G"
        type = "cards"
          [[groups.blocks]]
          provider = "local_projects"
          params = { roots = ["."], show = ["version", "bogus"] }
    """)
    with pytest.raises(ConfigError, match="bogus"):
        load_config(p)


def test_config_requires_roots(tmp_path):
    p = _write_cfg(tmp_path, """
        [[groups]]
        id = "g"
        title = "G"
        type = "cards"
          [[groups.blocks]]
          provider = "local_projects"
          params = { }
    """)
    with pytest.raises(ConfigError):
        load_config(p)
