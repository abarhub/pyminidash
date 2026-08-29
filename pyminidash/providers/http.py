"""Providers HTTP : contrôle d'endpoints et extraction de tableaux depuis une API JSON."""
from __future__ import annotations

import time
from datetime import datetime
from urllib.parse import urlsplit

import httpx

from pyminidash.models import (
    Record, StatusLevel, datetime_, duration, link, number, status, text, title,
)
from pyminidash.registry import provider


def _dig(obj: object, path: str) -> object:
    if path == "$":
        return obj
    current = obj
    for segment in path.split("."):
        if isinstance(current, dict) and segment in current:
            current = current[segment]
        else:
            return None
    return current


def _check_level(code: int | None, latency_s: float) -> tuple[str, StatusLevel]:
    if code is None:
        return "DOWN", StatusLevel.ERROR
    if code >= 400:
        return f"HTTP {code}", StatusLevel.ERROR
    if latency_s >= 0.5:
        return "SLOW", StatusLevel.WARN
    return "UP", StatusLevel.OK


@provider("http_check")
def http_check(urls: list[str], timeout: float = 5.0) -> list[Record]:
    records: list[Record] = []
    for url in urls:
        code: int | None = None
        error = ""
        start = time.perf_counter()
        try:
            resp = httpx.get(url, timeout=timeout, follow_redirects=True)
            code = resp.status_code
        except httpx.RequestError as exc:
            error = str(exc)
        latency_s = time.perf_counter() - start
        label, level = _check_level(code, latency_s)
        records.append(Record(
            title("host", "Endpoint", urlsplit(url).netloc or url),
            status("state", "État", label, level=level, summary=True),
            number("code", "Code HTTP", code, summary=True),
            duration("latency", "Latence", latency_s, summary=True),
            link("url", "URL", url, url=url),
            text("error", "Erreur", error),
            datetime_("checked_at", "Vérifié à", datetime.now()),
        ))
    return records


@provider("http_json")
def http_json(url: str, rows_path: str, columns: list[str],
              timeout: float = 5.0) -> list[Record]:
    resp = httpx.get(url, timeout=timeout, follow_redirects=True)
    resp.raise_for_status()
    rows = _dig(resp.json(), rows_path)
    if not isinstance(rows, list):
        raise ValueError(
            f"rows_path '{rows_path}' ne pointe pas sur une liste (obtenu {type(rows).__name__})"
        )
    records: list[Record] = []
    for entry in rows:
        fields = [
            text(col, col.split(".")[-1], _dig(entry, col))
            for col in columns
        ]
        records.append(Record(*fields))
    return records
