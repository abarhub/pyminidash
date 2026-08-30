"""Lecture de go.mod (chemin de module, version de Go)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GoInfo:
    readable: bool
    module: str | None
    name: str | None
    go_version: str | None


def parse_gomod(dir: Path) -> GoInfo:
    try:
        lines = (dir / "go.mod").read_text(encoding="utf-8").splitlines()
    except OSError:
        return GoInfo(False, None, None, None)
    module = go_version = None
    for raw in lines:
        line = raw.strip()
        if line.startswith("module ") and module is None:
            module = line[len("module "):].strip()
        elif line.startswith("go ") and go_version is None:
            go_version = line[len("go "):].strip()
    name = module.rsplit("/", 1)[-1] if module else None
    return GoInfo(True, module, name, go_version)
