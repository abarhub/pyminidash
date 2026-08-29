"""Formatage d'une valeur de Field en texte affichable.

status et link ne sont mis en forme (pastille / ancre) que par les templates ;
ici on ne renvoie que leur texte brut."""
from __future__ import annotations

from datetime import datetime

from pyminidash.models import Field, FieldType

_BYTE_UNITS = ("B", "KB", "MB", "GB", "TB", "PB")


def _humanize_bytes(n: float) -> str:
    value = float(n)
    for unit in _BYTE_UNITS:
        if abs(value) < 1024 or unit == _BYTE_UNITS[-1]:
            if unit == "B":
                return f"{value:.0f} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} {_BYTE_UNITS[-1]}"  # inatteignable, garde-fou


def _humanize_duration(seconds: float) -> str:
    s = float(seconds)
    if s < 1:
        return f"{s * 1000:.0f} ms"
    if s < 60:
        return f"{s:.0f} s"
    total = int(s)
    minutes, sec = divmod(total, 60)
    if minutes < 60:
        return f"{minutes} min {sec} s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes} min"


def format_value(field: Field) -> str:
    value = field.value
    if value is None:
        return ""
    t = field.type
    if t in (FieldType.TEXT, FieldType.STATUS, FieldType.LINK):
        return str(value)
    if t is FieldType.NUMBER:
        return f"{value:g}" if isinstance(value, (int, float)) else str(value)
    if t is FieldType.BYTES:
        return _humanize_bytes(value)
    if t is FieldType.PERCENT:
        return f"{float(value):g} %"
    if t is FieldType.DATETIME:
        return value.strftime("%Y-%m-%d %H:%M:%S") if isinstance(value, datetime) else str(value)
    if t is FieldType.DURATION:
        return _humanize_duration(value)
    return str(value)
