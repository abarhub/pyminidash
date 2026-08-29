"""Chargement du fichier de secrets (PAT), séparé de la configuration."""
from __future__ import annotations

import logging
import os
import stat
import tomllib
from pathlib import Path

log = logging.getLogger("pyminidash.secrets")


class SecretsError(Exception):
    """Fichier de secrets absent d'un format attendu ou mal formé."""


def load_secrets(path: str | Path) -> dict[str, str]:
    p = Path(path)
    if not p.is_file():
        return {}
    try:
        data = tomllib.loads(p.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise SecretsError(f"secrets TOML invalide dans {p} : {exc}") from None

    out: dict[str, str] = {}
    for key, value in data.items():
        if not isinstance(value, str):
            raise SecretsError(
                f"secrets : la clé '{key}' n'est pas une chaîne "
                f"(obtenu {type(value).__name__})"
            )
        out[key] = value

    if os.name == "posix":
        mode = p.stat().st_mode
        if mode & 0o077:
            log.warning(
                "secrets : %s est lisible par d'autres utilisateurs (mode %o) ; "
                "chmod 600 recommandé",
                p, stat.S_IMODE(mode),
            )
    return out
