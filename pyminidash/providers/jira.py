"""Providers Jira Server/DC : recherche JQL, compteur, raccourci « mes issues »."""
from __future__ import annotations

from datetime import datetime

from pyminidash.models import (
    Field, FieldRole, Record, StatusLevel, datetime_, link, status, text,
)
from pyminidash.providers._atlassian import count_record, get_json
from pyminidash.registry import provider

_HARD_CAP = 200
_PAGE = 100
_DONE = {"done", "closed", "resolved", "terminé", "fermé"}
_BLOCKED = {"blocked", "impediment", "bloqué"}


def _status_level(name: str) -> StatusLevel:
    low = name.strip().lower()
    if low in _DONE:
        return StatusLevel.OK
    if low in _BLOCKED:
        return StatusLevel.ERROR
    return StatusLevel.NEUTRAL


def _parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return value


def _names(seq) -> str:
    return ", ".join(x.get("name", "") for x in (seq or []))


def _issue_field(name: str, issue: dict, base_url: str) -> Field:
    key = issue.get("key", "")
    f = issue.get("fields") or {}

    if name == "key":
        return link("key", "Clé", key, url=f"{base_url}/browse/{key}",
                    role=FieldRole.TITLE)
    if name == "summary":
        return text("summary", "Résumé", f.get("summary") or "")
    if name == "status":
        sname = ((f.get("status") or {}).get("name")) or "?"
        return status("status", "Statut", sname, level=_status_level(sname),
                      summary=True)
    if name in ("assignee", "reporter"):
        person = f.get(name) or {}
        label = "Assigné" if name == "assignee" else "Rapporteur"
        return text(name, label, person.get("displayName") or "Non assigné")
    if name == "priority":
        return text("priority", "Priorité", ((f.get("priority") or {}).get("name")) or "")
    if name in ("issuetype", "resolution"):
        label = "Type" if name == "issuetype" else "Résolution"
        return text(name, label, ((f.get(name) or {}).get("name")) or "")
    if name == "labels":
        return text("labels", "Labels", ", ".join(f.get("labels") or []))
    if name in ("components", "fixVersions"):
        label = "Composants" if name == "components" else "Versions"
        return text(name, label, _names(f.get(name)))
    if name in ("created", "updated"):
        label = "Créé" if name == "created" else "Mis à jour"
        return datetime_(name, label, _parse_dt(f.get(name)))
    if name == "parent":
        return text("parent", "Parent", ((f.get("parent") or {}).get("key")) or "")

    raw = f.get(name)
    if isinstance(raw, list):
        raw = ", ".join(str(x) for x in raw)
    elif isinstance(raw, dict):
        raw = raw.get("name") or raw.get("value") or ""
    return text(name, name, "" if raw is None else str(raw))


def _search(connection, jql: str, fields: list[str], max_results: int) -> list[Record]:
    base_url = connection.base_url
    api_fields = [n for n in fields if n != "key"]
    want = min(max_results, _HARD_CAP)

    issues: list[dict] = []
    start = 0
    while len(issues) < want:
        page = get_json(connection, "/rest/api/2/search", params={
            "jql": jql,
            "fields": ",".join(api_fields),
            "startAt": start,
            "maxResults": min(_PAGE, want - len(issues)),
        })
        batch = page.get("issues") or []
        issues.extend(batch)
        total = int(page.get("total", 0))
        start += len(batch)
        if not batch or start >= total:
            break

    issues = issues[:want]
    return [
        Record(*[_issue_field(n, iss, base_url) for n in fields])
        for iss in issues
    ]


@provider("jira_jql")
def jira_jql(connection, jql: str, fields: list[str],
            max_results: int = 50) -> list[Record]:
    return _search(connection, jql, fields, max_results)
