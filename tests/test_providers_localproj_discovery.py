from pathlib import Path

import pytest

from pyminidash.errors import ProviderError
from pyminidash.providers.localproj.discovery import find_projects, markers


def _touch(p: Path):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x", encoding="utf-8")


def test_markers_priority_order(tmp_path):
    _touch(tmp_path / "pom.xml")
    _touch(tmp_path / "package.json")
    assert markers(tmp_path) == ("maven", "npm")


def test_markers_python_via_venv_dir(tmp_path):
    (tmp_path / ".venv2").mkdir()
    assert markers(tmp_path) == ("python",)


def test_finds_nested_project_and_stops_descending(tmp_path):
    _touch(tmp_path / "a" / "pom.xml")
    _touch(tmp_path / "a" / "sub" / "pom.xml")     # ne doit PAS produire un 2e record
    found = find_projects([str(tmp_path)], [], max_depth=5)
    assert [p.path for p in found] == [tmp_path / "a"]


def test_hardcoded_ignores_are_skipped(tmp_path):
    _touch(tmp_path / "node_modules" / "pkg" / "package.json")
    _touch(tmp_path / "real" / "package.json")
    found = find_projects([str(tmp_path)], [], max_depth=5)
    assert [p.name for p in found] == ["real"]


def test_ignore_glob_on_dir_name(tmp_path):
    _touch(tmp_path / "archive-2019" / "pom.xml")
    _touch(tmp_path / "keep" / "pom.xml")
    found = find_projects([str(tmp_path)], ["archive-*"], max_depth=5)
    assert [p.name for p in found] == ["keep"]


def test_max_depth_cutoff(tmp_path):
    _touch(tmp_path / "x" / "y" / "z" / "pom.xml")
    assert find_projects([str(tmp_path)], [], max_depth=2) == []
    assert len(find_projects([str(tmp_path)], [], max_depth=3)) == 1


def test_overlapping_roots_dedup(tmp_path):
    _touch(tmp_path / "proj" / "go.mod")
    found = find_projects([str(tmp_path), str(tmp_path / "proj")], [], max_depth=5)
    assert len(found) == 1


def test_missing_root_raises_providererror(tmp_path):
    with pytest.raises(ProviderError, match="introuvable"):
        find_projects([str(tmp_path / "nope")], [], max_depth=3)


def test_results_sorted_by_name(tmp_path):
    _touch(tmp_path / "zeta" / "go.mod")
    _touch(tmp_path / "alpha" / "go.mod")
    found = find_projects([str(tmp_path)], [], max_depth=5)
    assert [p.name for p in found] == ["alpha", "zeta"]
