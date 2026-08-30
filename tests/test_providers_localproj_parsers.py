from pathlib import Path

from pyminidash.providers.localproj.cargo import parse_cargo
from pyminidash.providers.localproj.gomod import parse_gomod
from pyminidash.providers.localproj.node import parse_node
from pyminidash.providers.localproj.python import parse_python


def _w(p: Path, text: str):
    p.write_text(text, encoding="utf-8")


def test_parse_node_nominal(tmp_path):
    _w(tmp_path / "package.json", """
      {"name": "front", "version": "2.1.0",
       "dependencies": {"@angular/core": "^17.0.3"},
       "devDependencies": {"@angular/material": "~17.0.1"}}
    """)
    info = parse_node(tmp_path)
    assert info.readable is True
    assert (info.name, info.version) == ("front", "2.1.0")
    assert info.angular_version == "17.0.3"
    assert info.angular_material_version == "17.0.1"


def test_parse_node_malformed(tmp_path):
    _w(tmp_path / "package.json", "{ not json")
    info = parse_node(tmp_path)
    assert info.readable is False
    assert info.name is None


def test_parse_cargo_package(tmp_path):
    _w(tmp_path / "Cargo.toml", """
      [package]
      name = "mycrate"
      version = "0.4.2"
      edition = "2021"
      rust-version = "1.74"
    """)
    info = parse_cargo(tmp_path)
    assert (info.name, info.version, info.edition, info.rust_version) == (
        "mycrate", "0.4.2", "2021", "1.74")


def test_parse_cargo_workspace(tmp_path):
    _w(tmp_path / "Cargo.toml", """
      [workspace]
      members = ["crates/a", "crates/b"]
    """)
    info = parse_cargo(tmp_path)
    assert info.name == tmp_path.name
    assert info.members == ("crates/a", "crates/b")


def test_parse_cargo_malformed(tmp_path):
    _w(tmp_path / "Cargo.toml", "[package\nname =")
    assert parse_cargo(tmp_path).readable is False


def test_parse_gomod(tmp_path):
    _w(tmp_path / "go.mod", "module github.com/me/thing\n\ngo 1.22\n")
    info = parse_gomod(tmp_path)
    assert info.module == "github.com/me/thing"
    assert info.name == "thing"
    assert info.go_version == "1.22"


def test_parse_python_pep621(tmp_path):
    _w(tmp_path / "pyproject.toml", '[project]\nname = "pkg"\nversion = "1.2.3"\n')
    info = parse_python(tmp_path)
    assert (info.name, info.version) == ("pkg", "1.2.3")


def test_parse_python_poetry(tmp_path):
    _w(tmp_path / "pyproject.toml",
       '[tool.poetry]\nname = "poetrypkg"\nversion = "9.9.9"\n')
    info = parse_python(tmp_path)
    assert (info.name, info.version) == ("poetrypkg", "9.9.9")


def test_parse_python_venv_only(tmp_path):
    (tmp_path / ".venv").mkdir()
    info = parse_python(tmp_path)
    assert info.name == tmp_path.name
    assert info.version is None


# --- C2 : fichiers non-UTF-8 -> les parsers ne lèvent jamais (spec §5) ---

def test_parse_gomod_latin1_does_not_raise(tmp_path):
    (tmp_path / "go.mod").write_bytes(
        "module ex.com/caf\xe9\n\ngo 1.22\n".encode("latin-1"))
    info = parse_gomod(tmp_path)  # ne doit pas lever
    assert info.go_version == "1.22"


def test_parse_python_setup_latin1_does_not_raise(tmp_path):
    (tmp_path / "setup.py").write_bytes(
        "# accent \xe9\nname='pkg'\nversion='1.0'\n".encode("latin-1"))
    info = parse_python(tmp_path)  # ne doit pas lever
    assert info.readable is True


def test_parse_python_pyproject_latin1_does_not_raise(tmp_path):
    (tmp_path / "pyproject.toml").write_bytes(
        "# accent \xe9\n[project]\nname = \"pkg\"\nversion = \"1.0\"\n".encode("latin-1"))
    info = parse_python(tmp_path)  # ne doit pas lever
    assert info.readable is True


def test_parse_cargo_latin1_does_not_raise(tmp_path):
    (tmp_path / "Cargo.toml").write_bytes(
        "# accent \xe9\n[package]\nname = \"c\"\nversion = \"0.1.0\"\n".encode("latin-1"))
    info = parse_cargo(tmp_path)  # ne doit pas lever
    assert info.readable is True


def test_parse_cargo_version_workspace_inheritance(tmp_path):
    # Minor cargo : version.workspace = true -> dict, doit devenir None.
    _w(tmp_path / "Cargo.toml", """
      [package]
      name = "c"
      version.workspace = true
      edition.workspace = true
    """)
    info = parse_cargo(tmp_path)
    assert info.readable is True
    assert info.version is None
    assert info.edition is None
    assert info.name == "c"
