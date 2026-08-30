"""Lecture de package.json (nom, version, Angular)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

_PREFIXES = "^~>=< "


@dataclass(frozen=True)
class NodeInfo:
    readable: bool
    name: str | None
    version: str | None
    angular_version: str | None
    angular_material_version: str | None


def _clean(spec: object) -> str | None:
    if not isinstance(spec, str):
        return None
    return spec.lstrip(_PREFIXES).strip() or None


def _dep(data: dict, pkg: str) -> str | None:
    for section in ("dependencies", "devDependencies"):
        block = data.get(section)
        if isinstance(block, dict) and pkg in block:
            return _clean(block[pkg])
    return None


def parse_node(dir: Path) -> NodeInfo:
    try:
        data = json.loads((dir / "package.json").read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError
    except (OSError, ValueError):
        return NodeInfo(False, None, None, None, None)
    name = data.get("name") if isinstance(data.get("name"), str) else None
    version = data.get("version") if isinstance(data.get("version"), str) else None
    return NodeInfo(
        True, name, version,
        _dep(data, "@angular/core"), _dep(data, "@angular/material"),
    )
