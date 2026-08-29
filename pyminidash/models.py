"""Modèle de données : un provider renvoie une list[Record], chaque Record est
une suite ordonnée de Field. Un Record se rend en ligne de tableau OU en card."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class FieldType(str, Enum):
    TEXT = "text"
    NUMBER = "number"
    BYTES = "bytes"
    PERCENT = "percent"
    STATUS = "status"
    LINK = "link"
    DATETIME = "datetime"
    DURATION = "duration"


class StatusLevel(str, Enum):
    OK = "ok"
    WARN = "warn"
    ERROR = "error"
    NEUTRAL = "neutral"


class FieldRole(str, Enum):
    NORMAL = "normal"
    TITLE = "title"
    BADGE = "badge"


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    value: Any
    type: FieldType = FieldType.TEXT
    role: FieldRole = FieldRole.NORMAL
    summary: bool = False
    level: StatusLevel | None = None
    url: str | None = None


class Record:
    __slots__ = ("fields",)

    def __init__(self, *fields: Field) -> None:
        self.fields: tuple[Field, ...] = tuple(fields)

    def keys(self) -> tuple[str, ...]:
        return tuple(f.key for f in self.fields)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Record) and self.fields == other.fields

    def __repr__(self) -> str:
        return f"Record({', '.join(repr(f) for f in self.fields)})"


def _field(key, label, value, ftype, *, summary=False, role=FieldRole.NORMAL,
           level=None, url=None) -> Field:
    return Field(key=key, label=label, value=value, type=ftype, role=role,
                 summary=summary, level=level, url=url)


def text(key, label, value, *, summary=False, role=FieldRole.NORMAL) -> Field:
    return _field(key, label, value, FieldType.TEXT, summary=summary, role=role)


def number(key, label, value, *, summary=False, role=FieldRole.NORMAL) -> Field:
    return _field(key, label, value, FieldType.NUMBER, summary=summary, role=role)


def bytes_(key, label, value, *, summary=False, role=FieldRole.NORMAL) -> Field:
    return _field(key, label, value, FieldType.BYTES, summary=summary, role=role)


def percent(key, label, value, *, summary=False, role=FieldRole.NORMAL) -> Field:
    return _field(key, label, value, FieldType.PERCENT, summary=summary, role=role)


def datetime_(key, label, value, *, summary=False, role=FieldRole.NORMAL) -> Field:
    return _field(key, label, value, FieldType.DATETIME, summary=summary, role=role)


def duration(key, label, value, *, summary=False, role=FieldRole.NORMAL) -> Field:
    return _field(key, label, value, FieldType.DURATION, summary=summary, role=role)


def status(key, label, value, *, level: StatusLevel, summary=False,
           role=FieldRole.BADGE) -> Field:
    return _field(key, label, value, FieldType.STATUS, summary=summary, role=role,
                  level=level)


def link(key, label, value, url, *, summary=False, role=FieldRole.NORMAL) -> Field:
    return _field(key, label, value, FieldType.LINK, summary=summary, role=role,
                  url=url)


def title(key, label, value) -> Field:
    return _field(key, label, value, FieldType.TEXT, role=FieldRole.TITLE)
