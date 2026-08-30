"""Lecture de Cargo.toml (package ou workspace)."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CargoInfo:
    readable: bool
    name: str | None
    version: str | None
    edition: str | None
    rust_version: str | None
    members: tuple[str, ...]


def _str_or_none(value: object) -> str | None:
    # `version.workspace = true` & co. donnent un dict ; on ne garde que les str.
    return value if isinstance(value, str) else None


def parse_cargo(dir: Path) -> CargoInfo:
    try:
        data = tomllib.loads((dir / "Cargo.toml").read_text(
            encoding="utf-8", errors="replace"))
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError):
        return CargoInfo(False, None, None, None, None, ())
    pkg = data.get("package", {})
    if isinstance(pkg, dict) and pkg:
        return CargoInfo(
            True, _str_or_none(pkg.get("name")), _str_or_none(pkg.get("version")),
            _str_or_none(pkg.get("edition")), _str_or_none(pkg.get("rust-version")), (),
        )
    ws = data.get("workspace", {})
    members = ws.get("members", []) if isinstance(ws, dict) else []
    members = tuple(m for m in members if isinstance(m, str))
    return CargoInfo(True, dir.name, None, None, None, members)
