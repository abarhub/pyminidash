"""Chargement et validation de la configuration TOML."""
from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field as PField, ValidationError, model_validator

from pyminidash.registry import get_provider, validate_params


class ConfigError(Exception):
    """Configuration absente, mal formée ou invalide. Bloque le démarrage."""


class BlockConfig(BaseModel):
    provider: str
    params: dict[str, Any] = PField(default_factory=dict)
    title: str | None = None
    timeout: float | None = None


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
                try:
                    validate_params(pdef, block.params)
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
