"""Découverte des projets sous une liste de répertoires racine."""
from __future__ import annotations

import os
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path

from pyminidash.errors import ProviderError

ALWAYS_IGNORE: frozenset[str] = frozenset({
    "target", "node_modules", "node", ".venv", ".venv2", ".env", ".git",
    "dist", "build", ".idea", ".gradle",
})

_PY_VENV_DIRS = (".venv", ".venv2", ".env")


@dataclass(frozen=True)
class ProjectDir:
    path: Path
    name: str
    types: tuple[str, ...]


def markers(d: Path) -> tuple[str, ...]:
    """Tokens de type présents dans `d`, en ordre de priorité."""
    found: list[str] = []
    if (d / "pom.xml").is_file():
        found.append("maven")
    if (d / "Cargo.toml").is_file():
        found.append("cargo")
    if (d / "go.mod").is_file():
        found.append("go")
    if (d / "package.json").is_file():
        found.append("npm")
    if (
        (d / "pyproject.toml").is_file()
        or (d / "setup.py").is_file()
        or any((d / v).is_dir() for v in _PY_VENV_DIRS)
    ):
        found.append("python")
    return tuple(found)


def _walk(root: Path, ignore: list[str], max_depth: int,
          out: dict[Path, ProjectDir]) -> None:
    def rec(d: Path, depth: int) -> None:
        types = markers(d)
        if types:
            resolved = d.resolve()
            out.setdefault(resolved, ProjectDir(resolved, d.name, types))
            return
        if depth >= max_depth:
            return
        try:
            entries = sorted(os.scandir(d), key=lambda e: e.name)
        except OSError:
            return
        for entry in entries:
            try:
                is_dir = entry.is_dir(follow_symlinks=False)
            except OSError:
                continue
            if not is_dir or entry.name in ALWAYS_IGNORE:
                continue
            if any(fnmatch(entry.name, pat) for pat in ignore):
                continue
            rec(Path(entry.path), depth + 1)

    rec(root, 0)


def find_projects(roots: list[str], ignore: list[str],
                  max_depth: int) -> list[ProjectDir]:
    missing = [r for r in roots if not Path(r).is_dir()]
    if missing:
        raise ProviderError(f"racine(s) introuvable(s) : {', '.join(missing)}")
    out: dict[Path, ProjectDir] = {}
    for r in roots:
        _walk(Path(r), ignore, max_depth, out)
    return sorted(out.values(), key=lambda p: (p.name.lower(), str(p.path)))
