"""Helpers partagés par les providers Atlassian (Jira/Bitbucket/Bamboo)."""
from __future__ import annotations

import html
import re
import ssl
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any

import httpx

from pyminidash.errors import ProviderError
from pyminidash.models import Record, StatusLevel, status

HARD_CAP = 200


class AtlassianError(ProviderError):
    """Base des erreurs d'API Atlassian (message déjà destiné à l'utilisateur)."""


class AuthError(AtlassianError):
    pass


class ConnError(AtlassianError):
    pass


class NotFoundError(AtlassianError):
    pass


class ApiError(AtlassianError):
    pass


def _is_ssl(exc: BaseException) -> bool:
    cur: BaseException | None = exc
    seen: set[int] = set()
    while cur is not None and id(cur) not in seen:
        if isinstance(cur, ssl.SSLError):
            return True
        seen.add(id(cur))
        cur = cur.__cause__ or cur.__context__
    return False


def _api_message(resp: httpx.Response) -> str | None:
    try:
        data = resp.json()
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    msgs = data.get("errorMessages")
    if isinstance(msgs, list) and msgs:
        return str(msgs[0])
    errors = data.get("errors")
    if isinstance(errors, dict) and errors:
        return "; ".join(f"{k}: {v}" for k, v in errors.items())
    if isinstance(data.get("message"), str):
        return data["message"]
    return None


def get_json(connection, path: str, *, params: dict | None = None,
             timeout: float = 8.0) -> Any:
    try:
        with connection.client(timeout=timeout) as client:
            resp = client.get(path, params=params)
    except httpx.ConnectError as exc:
        if _is_ssl(exc):
            raise ConnError(
                f"certificat TLS rejeté pour '{connection.name}' — vérifiez verify"
            ) from None
        raise ConnError(
            f"connexion impossible à '{connection.name}' ({connection.base_url})"
        ) from None
    except httpx.TimeoutException:
        raise ConnError(
            f"délai dépassé en contactant '{connection.name}'"
        ) from None

    code = resp.status_code
    if code in (401, 403):
        raise AuthError(
            f"authentification refusée pour la connexion '{connection.name}' "
            f"— vérifiez le token"
        )
    if code == 404:
        raise NotFoundError(f"ressource introuvable ({path})")
    if code == 400:
        raise ApiError(_api_message(resp) or f"requête refusée (400) sur {path}")
    if 300 <= code < 400:
        raise ApiError(
            f"redirection inattendue ({code}) sur {path} — vérifiez base_url "
            f"pour '{connection.name}' (portail SSO ?)"
        )
    if code >= 400:
        raise ApiError(f"erreur HTTP {code} sur {path}")

    try:
        return resp.json()
    except ValueError:
        raise ApiError(f"réponse non-JSON de '{connection.name}'") from None


def count_record(label: str, count: int, *, warn_above: int | None = None,
                 error_above: int | None = None,
                 display: str | None = None) -> Record:
    level = StatusLevel.OK
    if error_above is not None and count > error_above:
        level = StatusLevel.ERROR
    elif warn_above is not None and count > warn_above:
        level = StatusLevel.WARN
    return Record(status("count", label, display or str(count), level=level,
                         summary=True))


_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(s) -> str:
    if not s:
        return ""
    return html.unescape(_TAG_RE.sub("", str(s))).strip()


def epoch_ms_to_dt(ms) -> datetime | None:
    if ms is None:
        return None
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def parse_iso(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return value


def paginate_v1(connection, path: str, *, params: dict | None = None,
                hard_cap: int = HARD_CAP, timeout: float = 8.0) -> Iterator[dict]:
    query = dict(params or {})
    start = 0
    yielded = 0
    while yielded < hard_cap:
        query["start"] = start
        query["limit"] = min(100, hard_cap - yielded)
        page = get_json(connection, path, params=query, timeout=timeout)
        if not isinstance(page, dict):
            raise ApiError(
                f"réponse inattendue (liste) de '{connection.name}' sur {path}"
            )
        values = page.get("values") or []
        for value in values:
            yield value
            yielded += 1
            if yielded >= hard_cap:
                return
        if page.get("isLastPage", True) or not values:
            return
        nxt = page.get("nextPageStart")
        if nxt is None:
            return
        start = nxt
