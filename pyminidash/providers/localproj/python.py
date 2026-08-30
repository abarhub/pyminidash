"""Lecture de pyproject.toml / setup.py (nom, version) — best effort."""
from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

_SETUP_NAME = re.compile(r"""name\s*=\s*['"]([^'"]+)['"]""")
_SETUP_VERSION = re.compile(r"""version\s*=\s*['"]([^'"]+)['"]""")


@dataclass(frozen=True)
class PythonInfo:
    readable: bool
    name: str | None
    version: str | None


def parse_python(dir: Path) -> PythonInfo:
    pyproject = dir / "pyproject.toml"
    if pyproject.is_file():
        try:
            data = tomllib.loads(pyproject.read_text(
                encoding="utf-8", errors="replace"))
        except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError):
            return PythonInfo(False, None, None)
        proj = data.get("project", {})
        if isinstance(proj, dict) and (proj.get("name") or proj.get("version")):
            return PythonInfo(True, proj.get("name"), proj.get("version"))
        poetry = data.get("tool", {}).get("poetry", {}) if isinstance(
            data.get("tool"), dict) else {}
        if isinstance(poetry, dict) and (poetry.get("name") or poetry.get("version")):
            return PythonInfo(True, poetry.get("name"), poetry.get("version"))
        return PythonInfo(True, dir.name, None)

    setup = dir / "setup.py"
    if setup.is_file():
        try:
            src = setup.read_text(encoding="utf-8", errors="replace")
        except (OSError, UnicodeDecodeError):
            return PythonInfo(False, None, None)
        n = _SETUP_NAME.search(src)
        v = _SETUP_VERSION.search(src)
        return PythonInfo(True, n.group(1) if n else dir.name,
                          v.group(1) if v else None)

    return PythonInfo(True, dir.name, None)   # .venv seul
