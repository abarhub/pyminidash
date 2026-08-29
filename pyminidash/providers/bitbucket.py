"""Providers Bitbucket Server/DC : pull requests, compteur, raccourci « à relire »."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from pyminidash.errors import ProviderError
from pyminidash.models import (
    FieldRole, Record, StatusLevel, datetime_, link, number, status, text,
)
from pyminidash.providers._atlassian import (
    AtlassianError, epoch_ms_to_dt, get_json, paginate_v1,
)
from pyminidash.registry import provider

log = logging.getLogger("pyminidash.providers.bitbucket")

_HARD_CAP = 200
_STATES = {"OPEN", "MERGED", "DECLINED", "ALL"}
_ROLES = {None, "REVIEWER", "AUTHOR"}
_DEFAULT_FIELDS = ["id", "title", "author", "reviewers", "branches", "updated"]
_STATE_LEVEL = {
    "OPEN": StatusLevel.NEUTRAL, "MERGED": StatusLevel.OK, "DECLINED": StatusLevel.ERROR,
}
_BUILD_LEVEL = {
    "SUCCESSFUL": StatusLevel.OK, "FAILED": StatusLevel.ERROR, "INPROGRESS": StatusLevel.NEUTRAL,
}


def _split_repo(s: str) -> tuple[str, str]:
    if "/" not in str(s):
        raise ProviderError(f"bitbucket : dépôt '{s}' attendu au format PROJET/slug")
    proj, slug = str(s).split("/", 1)
    return proj, slug


def resolve_repos(connection, *, repo=None, repos=None, project=None) -> list[tuple[str, str]]:
    given = [x for x in (repo, repos, project) if x is not None]
    if len(given) != 1:
        raise ProviderError(
            "bitbucket : indiquez exactement un de repo / repos / project"
        )
    if repo is not None:
        return [_split_repo(repo)]
    if repos is not None:
        return [_split_repo(r) for r in repos]
    return [
        (project, r["slug"])
        for r in paginate_v1(connection, f"/rest/api/1.0/projects/{project}/repos")
        if r.get("slug")
    ]


def _pr_field(name, pr):
    if name == "id":
        pid = pr.get("id")
        href = (((pr.get("links") or {}).get("self") or [{}])[0]).get("href") or ""
        return link("id", "PR", f"#{pid}", url=href, role=FieldRole.TITLE)
    if name == "title":
        return text("title", "Titre", pr.get("title") or "")
    if name == "author":
        u = (pr.get("author") or {}).get("user") or {}
        return text("author", "Auteur", u.get("displayName") or u.get("name") or "?")
    if name == "reviewers":
        revs = pr.get("reviewers") or []
        total = len(revs)
        approved = sum(1 for r in revs if r.get("approved"))
        if total and approved == total:
            return status("reviewers", "Revue", f"{approved}/{total} ✓",
                          level=StatusLevel.OK, summary=True)
        if any(r.get("status") == "NEEDS_WORK" for r in revs):
            return status("reviewers", "Revue", "needs work",
                          level=StatusLevel.WARN, summary=True)
        return status("reviewers", "Revue", f"{approved}/{total} ✓",
                      level=StatusLevel.NEUTRAL, summary=True)
    if name == "branches":
        frm = (pr.get("fromRef") or {}).get("displayId") or "?"
        to = (pr.get("toRef") or {}).get("displayId") or "?"
        return text("branches", "Branches", f"{frm} → {to}")
    if name == "state":
        s = pr.get("state") or "?"
        return status("state", "État", s,
                      level=_STATE_LEVEL.get(s, StatusLevel.NEUTRAL), summary=True)
    if name in ("updated", "created"):
        k = "updatedDate" if name == "updated" else "createdDate"
        label = "Mis à jour" if name == "updated" else "Créé"
        return datetime_(name, label, epoch_ms_to_dt(pr.get(k)))
    if name == "comments":
        return number("comments", "Commentaires",
                      (pr.get("properties") or {}).get("commentCount") or 0)
    if name == "tasks":
        return number("tasks", "Tâches",
                      (pr.get("properties") or {}).get("openTaskCount") or 0)
    return text(name, name, "")


def _build_field(connection, pr):
    sha = (pr.get("fromRef") or {}).get("latestCommit")
    if not sha:
        return status("build", "Build", "—", level=StatusLevel.NEUTRAL)
    try:
        data = get_json(connection, f"/rest/build-status/1.0/commits/{sha}")
    except AtlassianError:
        return status("build", "Build", "—", level=StatusLevel.NEUTRAL)
    vals = data.get("values") or []
    if not vals:
        return status("build", "Build", "—", level=StatusLevel.NEUTRAL)
    st = vals[0].get("state") or "—"
    return status("build", "Build", st,
                  level=_BUILD_LEVEL.get(st, StatusLevel.NEUTRAL), summary=True)


def _mergeable_field(connection, pr, project, slug):
    pid = pr.get("id")
    try:
        data = get_json(
            connection,
            f"/rest/api/1.0/projects/{project}/repos/{slug}/pull-requests/{pid}/merge",
        )
    except AtlassianError:
        return status("mergeable", "Fusion", "?", level=StatusLevel.NEUTRAL)
    if data.get("conflicted"):
        return status("mergeable", "Fusion", "conflit",
                      level=StatusLevel.ERROR, summary=True)
    if data.get("canMerge"):
        return status("mergeable", "Fusion", "mergeable",
                      level=StatusLevel.OK, summary=True)
    return status("mergeable", "Fusion", "bloquée", level=StatusLevel.NEUTRAL)


def _pr_record(connection, pr, fields, project, slug):
    parts = []
    for name in fields:
        if name == "build":
            parts.append(_build_field(connection, pr))
        elif name == "mergeable":
            parts.append(_mergeable_field(connection, pr, project, slug))
        else:
            parts.append(_pr_field(name, pr))
    return Record(*parts)


def _pr_query(state: str, role, connection) -> dict:
    query: dict = {}
    if state != "ALL":
        query["state"] = state
    if role is not None:
        query["role.1"] = role
        query["username.1"] = connection.user
    return query


@provider("bitbucket_pr")
def bitbucket_pr(connection, repo=None, repos=None, project=None, state="OPEN",
                 role=None, fields=None, stale_days=None,
                 max_results=50) -> list[Record]:
    state = str(state).upper()
    if state not in _STATES:
        raise ProviderError(
            f"bitbucket_pr : state '{state}' invalide (OPEN, MERGED, DECLINED, ALL)"
        )
    if role not in _ROLES:
        raise ProviderError(
            f"bitbucket_pr : role '{role}' invalide (REVIEWER, AUTHOR)"
        )
    if role is not None and not connection.user:
        raise ProviderError(
            f"connexion '{connection.name}' : renseignez user pour filtrer par rôle"
        )
    fields = fields or _DEFAULT_FIELDS
    targets = resolve_repos(connection, repo=repo, repos=repos, project=project)
    query = _pr_query(state, role, connection)

    cutoff = None
    if stale_days is not None:
        cutoff = datetime.now(tz=timezone.utc).timestamp() * 1000 - stale_days * 86_400_000

    scored: list[tuple[float, Record]] = []
    last_error: AtlassianError | None = None
    ok_repos = 0
    for proj, slug in targets:
        path = f"/rest/api/1.0/projects/{proj}/repos/{slug}/pull-requests"
        try:
            prs = list(paginate_v1(connection, path, params=query, hard_cap=_HARD_CAP))
        except AtlassianError as exc:
            last_error = exc
            log.warning("bitbucket_pr : dépôt %s/%s : %s", proj, slug, exc)
            continue
        ok_repos += 1
        for pr in prs:
            updated = pr.get("updatedDate") or 0
            if cutoff is not None and updated > cutoff:
                continue
            scored.append((updated, _pr_record(connection, pr, fields, proj, slug)))

    if ok_repos == 0 and last_error is not None:
        raise last_error

    scored.sort(key=lambda t: t[0], reverse=True)
    return [rec for _, rec in scored[: min(max_results, _HARD_CAP)]]
