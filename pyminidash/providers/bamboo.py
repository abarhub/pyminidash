"""Providers Bamboo : dernier build d'un plan, builds d'un utilisateur, santé, en cours."""
from __future__ import annotations

import logging

from pyminidash.errors import ProviderError
from pyminidash.models import (
    FieldRole, Record, StatusLevel, datetime_, duration, link, number, status, text,
)
from pyminidash.providers._atlassian import (
    NotFoundError, count_record, get_json, parse_iso, strip_html,
)
from pyminidash.registry import provider

log = logging.getLogger("pyminidash.providers.bamboo")

_STATE_LEVEL = {
    "Successful": StatusLevel.OK,
    "Failed": StatusLevel.ERROR,
    "InProgress": StatusLevel.NEUTRAL,
    "Unknown": StatusLevel.NEUTRAL,
}
_PLAN_STATUS_FIELDS = ["plan", "state", "number", "duration", "finished"]


def _plan_result(connection, plan_key: str) -> dict | None:
    try:
        data = get_json(
            connection, f"/rest/api/latest/result/{plan_key}/latest",
            params={"expand": "results.result"},
        )
    except NotFoundError:
        return None
    if isinstance(data, dict):
        inner = (data.get("results") or {}).get("result")
        if isinstance(inner, list):
            return inner[0] if inner else None
    return data if isinstance(data, dict) else None


def _plan_key_of(result: dict, fallback: str) -> str:
    return (
        (result.get("planResultKey") or {}).get("key")
        or (result.get("plan") or {}).get("key")
        or fallback
    )


def _plan_field(name, result, base_url, plan_key):
    r = result or {}
    if name == "plan":
        prk = _plan_key_of(r, plan_key)
        label = r.get("planName") or (r.get("plan") or {}).get("shortName") or plan_key
        return link("plan", "Plan", label, url=f"{base_url}/browse/{prk}",
                    role=FieldRole.TITLE)
    if name == "state":
        if not result:
            return status("state", "État", "—", level=StatusLevel.NEUTRAL, summary=True)
        st = r.get("buildState") or "Unknown"
        return status("state", "État", st,
                      level=_STATE_LEVEL.get(st, StatusLevel.NEUTRAL), summary=True)
    if name == "number":
        return number("number", "Build", r.get("buildNumber"))
    if name == "duration":
        secs = r.get("buildDurationInSeconds")
        return duration("duration", "Durée",
                        int(secs) if secs not in (None, "") else None)
    if name == "finished":
        return datetime_("finished", "Terminé", parse_iso(r.get("buildCompletedTime")))
    if name == "trigger":
        return text("trigger", "Déclencheur", strip_html(r.get("buildReason") or ""))
    if name == "tests":
        p = r.get("successfulTestCount") or 0
        f = r.get("failedTestCount") or 0
        return text("tests", "Tests", f"{p} ✓ / {f} ✗")
    return text(name, name, "")


@provider("bamboo_plan_status")
def bamboo_plan_status(connection, plans, fields=None) -> list[Record]:
    if not plans:
        raise ProviderError("bamboo_plan_status : 'plans' ne doit pas être vide")
    fields = fields or _PLAN_STATUS_FIELDS
    out = []
    for plan_key in plans:
        result = _plan_result(connection, plan_key)
        out.append(Record(*[
            _plan_field(n, result, connection.base_url, plan_key) for n in fields
        ]))
    return out


_USER_BUILDS_FIELDS = ["plan", "state", "number", "finished", "duration"]


@provider("bamboo_user_builds")
def bamboo_user_builds(connection, user=None, max_results=25,
                       scan=100) -> list[Record]:
    who = user or connection.user
    if not who:
        raise ProviderError(
            f"connexion '{connection.name}' : renseignez user "
            f"(ou passez user=...) pour bamboo_user_builds"
        )
    data = get_json(connection, "/rest/api/latest/result", params={
        "expand": "results.result", "max-results": min(scan, 100),
    })
    results = (data.get("results") or {}).get("result") or []
    low = who.lower()
    kept = [
        r for r in results
        if low in strip_html(r.get("buildReason") or "").lower()
    ][:max_results]
    return [
        Record(*[
            _plan_field(n, r, connection.base_url, _plan_key_of(r, ""))
            for n in _USER_BUILDS_FIELDS
        ])
        for r in kept
    ]


@provider("bamboo_plan_health")
def bamboo_plan_health(connection, plans) -> list[Record]:
    if not plans:
        raise ProviderError("bamboo_plan_health : 'plans' ne doit pas être vide")
    green = red = 0
    for plan_key in plans:
        st = (_plan_result(connection, plan_key) or {}).get("buildState")
        if st == "Successful":
            green += 1
        elif st == "Failed":
            red += 1
    return [Record(
        text("title", "Santé des plans", f"{green} vert / {red} rouge"),
        number("green", "Au vert", green, summary=True),
        number("red", "Au rouge", red, summary=True),
        status("status", "Global", "KO" if red else "OK",
               level=StatusLevel.ERROR if red else StatusLevel.OK,
               role=FieldRole.BADGE, summary=True),
    )]
