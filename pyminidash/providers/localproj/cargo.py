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


def parse_cargo(dir: Path) -> CargoInfo:
    try:
        data = tomllib.loads((dir / "Cargo.toml").read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return CargoInfo(False, None, None, None, None, ())
    pkg = data.get("package", {})
    if isinstance(pkg, dict) and pkg:
        return CargoInfo(
            True, pkg.get("name"), pkg.get("version"),
            pkg.get("edition"), pkg.get("rust-version"), (),
        )
    ws = data.get("workspace", {})
    members = ws.get("members", []) if isinstance(ws, dict) else []
    members = tuple(m for m in members if isinstance(m, str))
    return CargoInfo(True, dir.name, None, None, None, members)
