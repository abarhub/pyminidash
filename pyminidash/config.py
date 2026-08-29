"""Chargement et validation de la configuration TOML."""
from __future__ import annotations

import inspect
import tomllib
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import (
    BaseModel, Field as PField, ValidationError, field_validator, model_validator,
)

import pyminidash.providers  # noqa: F401 — enregistre les providers intégrés avant validation
from pyminidash.registry import get_provider, validate_params


class ConfigError(Exception):
    """Configuration absente, mal formée ou invalide. Bloque le démarrage."""


class ConnectionConfig(BaseModel):
    base_url: str
    token: str
    user: str | None = None
    verify: bool | str = True
    auth: Literal["bearer"] = "bearer"

    @field_validator("base_url")
    @classmethod
    def _check_base_url(cls, v: str) -> str:
        parsed = urlsplit(v)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError(f"base_url invalide : {v!r} (attendu http(s)://hôte)")
        return v.rstrip("/")

    @field_validator("token")
    @classmethod
    def _check_token(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("token vide")
        return v


class BlockConfig(BaseModel):
    provider: str
    params: dict[str, Any] = PField(default_factory=dict)
    title: str | None = None
    timeout: float | None = PField(default=None, gt=0)
    connection: str | None = None


class GroupConfig(BaseModel):
    id: str
    title: str
    type: Literal["table", "cards"]
    blocks: list[BlockConfig] = PField(min_length=1)


class AppConfig(BaseModel):
    title: str = "pyminidash"
    default_group: str | None = None


class Config(BaseModel):
    app: AppConfig = PField(default_factory=AppConfig)
    connections: dict[str, ConnectionConfig] = PField(default_factory=dict)
    groups: list[GroupConfig] = PField(min_length=1)

    @model_validator(mode="after")
    def _cross_checks(self) -> "Config":
        ids = [g.id for g in self.groups]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise ValueError(f"id(s) de groupe en double : {dupes}")

        if self.app.default_group is None:
            self.app.default_group = self.groups[0].id
        elif self.app.default_group not in ids:
            raise ValueError(
                f"default_group '{self.app.default_group}' ne correspond à aucun groupe"
            )

        for group in self.groups:
            for i, block in enumerate(group.blocks):
                if block.title is None:
                    block.title = block.provider
                where = f"groupe '{group.id}' bloc {i}"
                try:
                    pdef = get_provider(block.provider)
                except ValueError as exc:
                    raise ValueError(f"{where}: {exc}") from None

                params = pdef.signature.parameters
                wants = "connection" in params
                requires = (
                    wants
                    and params["connection"].default is inspect.Parameter.empty
                )
                if block.connection is not None and not wants:
                    raise ValueError(
                        f"{where} : le provider '{block.provider}' n'utilise pas de connexion"
                    )
                if requires and block.connection is None:
                    raise ValueError(
                        f"{where} : le provider '{block.provider}' exige connection = \"...\""
                    )
                if block.connection is not None and block.connection not in self.connections:
                    avail = ", ".join(sorted(self.connections)) or "(aucune)"
                    raise ValueError(
                        f"{where} : connexion inconnue '{block.connection}' ; disponibles : {avail}"
                    )
                try:
                    validate_params(
                        pdef, block.params,
                        injected=frozenset({"connection"}) if wants else frozenset(),
                    )
                except ValueError as exc:
                    raise ValueError(f"{where}: {exc}") from None
        return self


def load_config(path: str | Path) -> Config:
    p = Path(path)
    if not p.is_file():
        raise ConfigError(f"fichier de configuration introuvable : {p}")
    try:
        data = tomllib.loads(p.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"TOML invalide dans {p} : {exc}") from None
    try:
        return Config.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"configuration invalide :\n{exc}") from None
