# pyminidash — Plan B : providers Bitbucket + Bamboo

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter à pyminidash les providers Bitbucket (pull requests) et Bamboo (builds), sur la fondation « connexions authentifiées » livrée par le Plan A.

**Architecture:** Deux nouveaux modules de providers (`bitbucket.py`, `bamboo.py`) qui, comme `jira.py`, reçoivent un objet `Connection` injecté par le runner et appellent l'API via `_atlassian.get_json`. Trois helpers partagés s'ajoutent à `_atlassian.py` : pagination Bitbucket Server 1.0 (`paginate_v1`), nettoyage HTML (`strip_html`), et conversions de dates (`epoch_ms_to_dt`, `parse_iso`). Aucune modification du cœur (config, runner, connexion) — le Plan A a déjà tout câblé.

**Tech Stack:** Python 3.13, `uv`, `httpx`, `tomllib`. Tests : `pytest`, `pytest-asyncio`, `respx`. Aucune nouvelle dépendance.

**Spec:** `docs/superpowers/specs/2026-08-29-pyminidash-atlassian-providers-design.md` — ce plan couvre §5 (helpers restants : pagination Bitbucket, `strip_html`), §7 (Bitbucket), §8 (Bamboo), §9 (erreurs, partie Bitbucket/Bamboo), §11 (config d'exemple, complétée). §2/§3/§4/§6 sont livrés par le Plan A (déjà mergé dans `main`).

## Global Constraints

- Python `>=3.13`. `python` seul n'est PAS sur le PATH — `uv run pytest` / `uv run python`. **Si `uv run pytest` se fige sans sortie** (observé dans certains sandbox), utiliser `./.venv/Scripts/python.exe -m pytest` (même interpréteur, `.venv` déjà synchronisé). `uv sync --offline` si `uv` tente pypi et échoue (erreur de certificat).
- Plateforme de dev : Windows 11 ; tests cross-platform (`respx` uniquement, **aucun appel réseau réel**).
- Auth : les connexions et l'injection existent déjà (Plan A). Un provider **exige** une connexion ssi sa signature a un paramètre `connection` sans valeur par défaut. Tous les nouveaux providers ont `connection` en premier paramètre sans défaut.
- **Divulgation** : le contenu d'un token n'apparaît JAMAIS dans un log, un message d'exception, une réponse HTTP ou un rendu. Les messages référencent le *nom de connexion*, jamais la valeur.
- **Ne PAS importer `pyminidash.connection`** dans `bitbucket.py` / `bamboo.py` / `_atlassian.py` : `connection.py` importe `config.py` qui importe `pyminidash.providers` → cycle. Le paramètre `connection` reste **non typé** ; on n'utilise que `.name`, `.base_url`, `.user`, `.client(...)` (ce dernier via `get_json`).
- **Records homogènes** : le runner (`_check_records`) rejette un bloc dont les `Record` n'ont pas tous les mêmes `key` dans le même ordre. Toute agrégation multi-dépôts / multi-plans doit produire des records homogènes — voir la **décision sur les marqueurs d'erreur** ci-dessous.
- Erreurs d'API traduites : `get_json` lève déjà `AuthError` (401/403), `NotFoundError` (404), `ApiError` (400/3xx/autres), `ConnError` (réseau/TLS) — toutes sous-classes de `AtlassianError` ⊂ `ProviderError`, rendues en `BlockError` propre par le runner.
- `user` requis mais absent (param + `connection.user`) → le provider lève `ProviderError` avec un message clair à l'exécution.
- Langue de l'UI et des messages : français. TDD strict : test qui échoue → implémentation → test qui passe → commit. Suite complète verte avant chaque commit. Sortie de test propre (seul warning admis : le `StarletteDeprecationWarning` préexistant de `fastapi/testclient.py`).

### Décision : marqueurs d'erreur d'agrégation

La spec §7 décrit, pour un dépôt en échec dans une agrégation, « un record marqueur
d'erreur ». C'est **incompatible avec la contrainte de records homogènes** que la
spec pose elle-même (le runner rejette un bloc aux records hétérogènes). Ce plan
tranche : sur échec d'un sous-appel (un dépôt de `repos`/`project` pour Bitbucket),
le provider **logge un `WARNING`** (`log.warning("bitbucket_pr : dépôt %s : %s", ...)`)
et continue avec les autres. Si **tous** les dépôts échouent, il **re-lève** la
dernière `AtlassianError` (le bloc affiche alors l'erreur). L'intention de la spec
(« un dépôt en échec n'interrompt pas les autres ») est préservée ; seul le marqueur
visuel est abandonné.

Pour Bamboo, un plan sans build / `404` produit un record **homogène** (mêmes champs,
valeurs « — ») → pas de déviation, c'est géré nativement dans le mapping.

---

## File Structure

| Fichier | Responsabilité | Tâche |
|---|---|---|
| `pyminidash/providers/_atlassian.py` | *(modifié)* `+ strip_html`, `+ epoch_ms_to_dt`, `+ parse_iso`, `+ paginate_v1` | 1 |
| `pyminidash/providers/bitbucket.py` | *(créé)* `resolve_repos`, `_pr_field`, `_pr_record`, `_build_field`, `_mergeable_field`, `bitbucket_pr`, `bitbucket_pr_count`, `bitbucket_my_review` | 2, 3 |
| `pyminidash/providers/bamboo.py` | *(créé)* `_plan_result`, `_plan_field`, `_running_record`, `bamboo_plan_status`, `bamboo_user_builds`, `bamboo_plan_health`, `bamboo_running` | 4, 5, 6 |
| `pyminidash/providers/__init__.py` | *(modifié)* importe `bitbucket`, `bamboo` | 7 |
| `config.example.toml` | *(modifié)* décommente `[connections.bitbucket]` / `[connections.bamboo]`, ajoute 2 blocs au groupe « Mon activité » | 7 |
| `README.md` | *(modifié)* tableau des providers + 7 lignes | 7 |
| `tests/test_atlassian_helpers.py` | *(modifié)* tests des 4 helpers | 1 |
| `tests/test_providers_bitbucket.py` | *(créé)* tests Bitbucket | 2, 3, 4 |
| `tests/test_providers_bamboo.py` | *(créé)* tests Bamboo | 4, 5, 6 |
| `tests/test_integration_atlassian.py` | *(modifié)* un bloc `bitbucket_pr` bout-en-bout | 7 |

---

## Task 1: Helpers partagés `_atlassian.py`

**Files:**
- Modify: `pyminidash/providers/_atlassian.py`
- Modify: `tests/test_atlassian_helpers.py`

**Interfaces:**
- Consumes: `get_json` (existant, dans le même module), `AtlassianError` (existant).
- Produces (ajoutés à `_atlassian.py`) :
  - `strip_html(s) -> str` : retire les balises HTML, dé-échappe les entités, `strip()` ; `""` si entrée fausse.
  - `epoch_ms_to_dt(ms) -> datetime | None` : millisecondes epoch (int ou str numérique) → `datetime` **aware UTC** ; `None` si `ms` est `None`/non convertible.
  - `parse_iso(value) -> datetime | str | None` : `None`/`""` → `None` ; ISO 8601 (avec `Z`) → `datetime` ; sinon la chaîne brute (comme `jira._parse_dt`).
  - `paginate_v1(connection, path, *, params=None, hard_cap=200, timeout=15.0) -> Iterator[dict]` : itère les `values` d'une API Bitbucket Server 1.0. Pose `start`/`limit` (limit = `min(100, restant)`), s'arrête sur `isLastPage` vrai, `values` vide, ou `nextPageStart` absent, ou `hard_cap` atteint. Propage les exceptions de `get_json`.

- [ ] **Step 1: Écrire les tests qui échouent** — ajouter à la fin de `tests/test_atlassian_helpers.py`

```python
from datetime import datetime, timezone

from pyminidash.providers._atlassian import (
    epoch_ms_to_dt, paginate_v1, parse_iso, strip_html,
)


def test_strip_html():
    assert strip_html('Manual run by <a href="x">Jean Dupont</a>') == "Manual run by Jean Dupont"
    assert strip_html("d&eacute;clench&eacute;") == "déclenché"
    assert strip_html("") == ""
    assert strip_html(None) == ""


def test_epoch_ms_to_dt():
    dt = epoch_ms_to_dt(1_724_500_000_000)
    assert dt is not None and dt.tzinfo is timezone.utc and dt.year == 2024
    assert epoch_ms_to_dt("1724500000000").year == 2024
    assert epoch_ms_to_dt(None) is None
    assert epoch_ms_to_dt("nope") is None


def test_parse_iso():
    assert parse_iso("") is None
    assert parse_iso("2026-08-20T14:30:00Z").hour == 14
    assert parse_iso("pas une date") == "pas une date"


@respx.mock
def test_paginate_v1_walks_pages():
    route = respx.get("https://jira.example.com/x")
    route.side_effect = [
        httpx.Response(200, json={"values": [{"id": 1}, {"id": 2}], "isLastPage": False, "nextPageStart": 2}),
        httpx.Response(200, json={"values": [{"id": 3}], "isLastPage": True}),
    ]
    got = list(paginate_v1(CONN, "/x"))
    assert [v["id"] for v in got] == [1, 2, 3]
    assert route.call_count == 2


@respx.mock
def test_paginate_v1_respects_hard_cap():
    respx.get("https://jira.example.com/x").mock(return_value=httpx.Response(
        200, json={"values": [{"id": i} for i in range(100)], "isLastPage": False, "nextPageStart": 100}
    ))
    got = list(paginate_v1(CONN, "/x", hard_cap=5))
    assert len(got) == 5
```

*(`CONN`, `respx`, `httpx` sont déjà importés en tête du fichier depuis le Plan A.)*

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `uv run pytest tests/test_atlassian_helpers.py -k "strip_html or epoch or parse_iso or paginate" -v`
Expected: FAIL — `ImportError: cannot import name 'strip_html'`

- [ ] **Step 3: Ajouter à `pyminidash/providers/_atlassian.py`**

En tête, compléter les imports :
```python
import html
import re
from collections.abc import Iterator
from datetime import datetime, timezone
```

À la fin du fichier :
```python
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
                hard_cap: int = 200, timeout: float = 15.0) -> Iterator[dict]:
    query = dict(params or {})
    start = 0
    yielded = 0
    while yielded < hard_cap:
        query["start"] = start
        query["limit"] = min(100, hard_cap - yielded)
        page = get_json(connection, path, params=query, timeout=timeout)
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
```

- [ ] **Step 4: Lancer, vérifier le succès**

Run: `uv run pytest tests/test_atlassian_helpers.py -v`
Expected: PASS (tous, anciens + 5 nouveaux). Si `test_strip_html` diverge sur la casse/accents des entités, ajuster l'attendu à la sortie réelle de `html.unescape` (l'algorithme fait foi).

- [ ] **Step 5: Suite complète + commit**

```bash
uv run pytest -q
git add -A
git commit -m "Ajoute strip_html, epoch_ms_to_dt, parse_iso, paginate_v1 aux helpers Atlassian"
```

---

## Task 2: `bitbucket.py` — `bitbucket_pr` (cœur)

**Files:**
- Create: `pyminidash/providers/bitbucket.py`
- Create: `tests/test_providers_bitbucket.py`

**Interfaces:**
- Consumes: `_atlassian` (`get_json`, `paginate_v1`, `epoch_ms_to_dt`, `count_record`, `AtlassianError`), `pyminidash.errors.ProviderError`, `pyminidash.models` (helpers + `FieldRole`, `StatusLevel`), `pyminidash.registry.provider`. **PAS** `pyminidash.connection`.
- Produces :
  - `_split_repo(s) -> tuple[str, str]` : `"ABC/mon-repo"` → `("ABC", "mon-repo")` ; sans `/` → `ProviderError`.
  - `resolve_repos(connection, *, repo=None, repos=None, project=None) -> list[tuple[str, str]]` : exactement une des trois formes (sinon `ProviderError`) ; `project` → `paginate_v1` sur `/rest/api/1.0/projects/{project}/repos`, renvoie `[(project, r["slug"]), ...]`.
  - `_pr_field(name, pr) -> Field` : mapping du §7 pour `id` (`link` + `role=TITLE`, libellé `#<id>`, url = `links.self[0].href`), `title`, `author` (`author.user.displayName`), `reviewers` (`status` : tous approuvés → `OK` « n/n ✓ » ; ≥1 `NEEDS_WORK` → `WARN` « needs work » ; sinon `NEUTRAL` « k/n ✓ »), `branches` (`fromRef.displayId → toRef.displayId`), `state` (`status` : OPEN→NEUTRAL, MERGED→OK, DECLINED→ERROR), `updated`/`created` (`datetime_` via `epoch_ms_to_dt`), `comments`/`tasks` (`number` depuis `properties`). Champ inconnu → `text` vide.
  - `_build_field(connection, pr) -> Field` : `GET /rest/build-status/1.0/commits/{fromRef.latestCommit}` → `status` (`SUCCESSFUL`→OK, `FAILED`→ERROR, `INPROGRESS`→NEUTRAL, absent/erreur → « — » NEUTRAL).
  - `_mergeable_field(connection, pr, project, slug) -> Field` : `GET /rest/api/1.0/projects/{project}/repos/{slug}/pull-requests/{id}/merge` → `status` (`conflicted`→ERROR « conflit », `canMerge`→OK « mergeable », sinon NEUTRAL « bloquée » ; erreur → « ? » NEUTRAL).
  - `_pr_record(connection, pr, fields, project, slug) -> Record` : un `Field` par nom de `fields`, `build`/`mergeable` délégués aux helpers ci-dessus, le reste à `_pr_field`.
  - `@provider("bitbucket_pr") def bitbucket_pr(connection, repo=None, repos=None, project=None, state="OPEN", role=None, fields=None, stale_days=None, max_results=50) -> list[Record]`.
    - `state` normalisé `.upper()` ; ∉ `{OPEN, MERGED, DECLINED, ALL}` → `ProviderError`. `state == "ALL"` → pas de param `state`.
    - `role` ∈ `{None, "REVIEWER", "AUTHOR"}` ; non-`None` → `ProviderError` si `not connection.user` ; ajoute `role.1` + `username.1 = connection.user`.
    - `fields` défaut `["id", "title", "author", "reviewers", "branches", "updated"]`.
    - agrège sur `resolve_repos(...)` via `paginate_v1` sur `/rest/api/1.0/projects/{proj}/repos/{slug}/pull-requests` ; **échec d'un dépôt → `log.warning` + continue** ; **tous en échec → re-lève**.
    - `stale_days` : filtre client, garde les PR dont `updatedDate` (ms) est **plus vieux** que `maintenant - stale_days`.
    - tri par `updatedDate` desc, tronqué à `min(max_results, 200)`.
  - `log = logging.getLogger("pyminidash.providers.bitbucket")`.

- [ ] **Step 1: Écrire le test qui échoue** — `tests/test_providers_bitbucket.py`

```python
import logging

import httpx
import pytest
import respx

from pyminidash.connection import Connection
from pyminidash.errors import ProviderError
from pyminidash.models import FieldRole, FieldType, StatusLevel
from pyminidash.providers.bitbucket import (
    _split_repo, bitbucket_pr, resolve_repos,
)

CONN = Connection(name="bb", base_url="https://bb.example.com", token="PAT", user="jdupont")
BASE = "https://bb.example.com/rest/api/1.0/projects/ABC/repos/r1/pull-requests"


def _pr(pid=1, updated=1_724_500_000_000, reviewers=None, state="OPEN"):
    return {
        "id": pid,
        "title": f"PR {pid}",
        "state": state,
        "author": {"user": {"displayName": "Léa"}},
        "reviewers": reviewers if reviewers is not None else [{"approved": True}],
        "fromRef": {"displayId": "feature/x", "latestCommit": "abc123"},
        "toRef": {"displayId": "main"},
        "updatedDate": updated,
        "properties": {"commentCount": 3, "openTaskCount": 1},
        "links": {"self": [{"href": f"https://bb.example.com/pr/{pid}"}]},
    }


def _page(values, last=True, nxt=None):
    body = {"values": values, "isLastPage": last, "size": len(values)}
    if nxt is not None:
        body["nextPageStart"] = nxt
    return httpx.Response(200, json=body)


def test_split_repo():
    assert _split_repo("ABC/mon-repo") == ("ABC", "mon-repo")
    with pytest.raises(ProviderError, match="PROJET/slug"):
        _split_repo("mon-repo")


def test_resolve_repos_exactly_one():
    with pytest.raises(ProviderError, match="exactement un"):
        resolve_repos(CONN)
    with pytest.raises(ProviderError, match="exactement un"):
        resolve_repos(CONN, repo="ABC/r1", project="ABC")
    assert resolve_repos(CONN, repo="ABC/r1") == [("ABC", "r1")]
    assert resolve_repos(CONN, repos=["ABC/r1", "ABC/r2"]) == [("ABC", "r1"), ("ABC", "r2")]


@respx.mock
def test_resolve_repos_project_paginates():
    respx.get("https://bb.example.com/rest/api/1.0/projects/ABC/repos").mock(
        return_value=httpx.Response(200, json={"values": [{"slug": "r1"}, {"slug": "r2"}], "isLastPage": True})
    )
    assert resolve_repos(CONN, project="ABC") == [("ABC", "r1"), ("ABC", "r2")]


@respx.mock
def test_bitbucket_pr_maps_fields_in_order():
    respx.get(BASE).mock(return_value=_page([_pr(1)]))
    records = bitbucket_pr(CONN, repo="ABC/r1", fields=["id", "title", "author", "reviewers", "branches", "updated"])
    assert len(records) == 1
    f = records[0].fields
    assert [x.key for x in f] == ["id", "title", "author", "reviewers", "branches", "updated"]
    assert f[0].type is FieldType.LINK and f[0].role is FieldRole.TITLE and f[0].value == "#1"
    assert f[0].url == "https://bb.example.com/pr/1"
    assert f[2].value == "Léa"
    assert f[3].type is FieldType.STATUS and f[3].level is StatusLevel.OK  # 1/1 approuvé
    assert f[4].value == "feature/x → main"
    assert f[5].type is FieldType.DATETIME


@respx.mock
def test_bitbucket_pr_reviewers_needs_work():
    prs = [_pr(1, reviewers=[{"approved": False, "status": "NEEDS_WORK"}, {"approved": True}])]
    respx.get(BASE).mock(return_value=_page(prs))
    rec = bitbucket_pr(CONN, repo="ABC/r1", fields=["reviewers"])[0]
    assert rec.fields[0].level is StatusLevel.WARN


@respx.mock
def test_bitbucket_pr_state_filter_and_role_requires_user():
    respx.get(BASE).mock(return_value=_page([_pr(1)]))
    bitbucket_pr(CONN, repo="ABC/r1", state="merged", fields=["id"])  # normalisé, ne lève pas
    no_user = Connection(name="bb", base_url="https://bb.example.com", token="X")
    with pytest.raises(ProviderError, match="user"):
        bitbucket_pr(no_user, repo="ABC/r1", role="REVIEWER", fields=["id"])


@respx.mock
def test_bitbucket_pr_bad_state():
    with pytest.raises(ProviderError, match="state"):
        bitbucket_pr(CONN, repo="ABC/r1", state="WEIRD", fields=["id"])


@respx.mock
def test_bitbucket_pr_aggregates_and_sorts_desc():
    respx.get("https://bb.example.com/rest/api/1.0/projects/ABC/repos/r1/pull-requests").mock(
        return_value=_page([_pr(1, updated=100)]))
    respx.get("https://bb.example.com/rest/api/1.0/projects/ABC/repos/r2/pull-requests").mock(
        return_value=_page([_pr(2, updated=200)]))
    records = bitbucket_pr(CONN, repos=["ABC/r1", "ABC/r2"], fields=["id"])
    assert [r.fields[0].value for r in records] == ["#2", "#1"]  # tri updated desc


@respx.mock
def test_bitbucket_pr_one_repo_fails_others_pass(caplog):
    respx.get("https://bb.example.com/rest/api/1.0/projects/ABC/repos/r1/pull-requests").mock(
        return_value=_page([_pr(1)]))
    respx.get("https://bb.example.com/rest/api/1.0/projects/ABC/repos/r2/pull-requests").mock(
        return_value=httpx.Response(404))
    with caplog.at_level(logging.WARNING, logger="pyminidash.providers.bitbucket"):
        records = bitbucket_pr(CONN, repos=["ABC/r1", "ABC/r2"], fields=["id"])
    assert [r.fields[0].value for r in records] == ["#1"]
    assert any("r2" in r.message for r in caplog.records)


@respx.mock
def test_bitbucket_pr_all_repos_fail_raises():
    respx.get("https://bb.example.com/rest/api/1.0/projects/ABC/repos/r1/pull-requests").mock(
        return_value=httpx.Response(404))
    with pytest.raises(ProviderError):
        bitbucket_pr(CONN, repos=["ABC/r1"], fields=["id"])


@respx.mock
def test_bitbucket_pr_stale_days_filter():
    now_ms = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).timestamp() * 1000
    fresh = _pr(1, updated=int(now_ms))
    old = _pr(2, updated=int(now_ms - 10 * 86_400_000))
    respx.get(BASE).mock(return_value=_page([fresh, old]))
    records = bitbucket_pr(CONN, repo="ABC/r1", fields=["id"], stale_days=7)
    assert [r.fields[0].value for r in records] == ["#2"]
```

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `uv run pytest tests/test_providers_bitbucket.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pyminidash.providers.bitbucket'`

- [ ] **Step 3: Écrire `pyminidash/providers/bitbucket.py`**

```python
"""Providers Bitbucket Server/DC : pull requests, compteur, raccourci « à relire »."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from pyminidash.errors import ProviderError
from pyminidash.models import (
    FieldRole, Record, StatusLevel, datetime_, link, number, status, text, title,
)
from pyminidash.providers._atlassian import (
    AtlassianError, count_record, epoch_ms_to_dt, get_json, paginate_v1,
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
```

- [ ] **Step 4: Lancer, vérifier le succès**

Run: `uv run pytest tests/test_providers_bitbucket.py -v`
Expected: PASS (12 tests). `providers/__init__.py` n'est PAS encore modifié → `bitbucket_pr` n'est pas enregistré globalement, mais le test l'importe en direct. C'est voulu (câblage en Task 7).

- [ ] **Step 5: Suite complète + commit**

```bash
uv run pytest -q
git add -A
git commit -m "Ajoute le provider bitbucket_pr (résolution de portée, agrégation, mapping)"
```

---

## Task 3: `bitbucket.py` — colonnes `build` / `mergeable`

**Files:**
- Modify: `tests/test_providers_bitbucket.py`

**Interfaces:**
- Consumes: `_build_field`, `_mergeable_field`, `bitbucket_pr` (Task 2). Rien de nouveau à écrire côté code — Task 2 a déjà implémenté `_build_field` / `_mergeable_field` / leur intégration dans `_pr_record`. **Cette tâche ne fait qu'ajouter la couverture de test** de ces chemins optionnels (1 appel API par PR).
- Produces: rien (tests uniquement).

- [ ] **Step 1: Ajouter les tests qui échouent** — à la fin de `tests/test_providers_bitbucket.py`

```python
@respx.mock
def test_bitbucket_pr_build_column():
    respx.get(BASE).mock(return_value=_page([_pr(1)]))
    respx.get("https://bb.example.com/rest/build-status/1.0/commits/abc123").mock(
        return_value=httpx.Response(200, json={"values": [{"state": "FAILED"}]})
    )
    rec = bitbucket_pr(CONN, repo="ABC/r1", fields=["id", "build"])[0]
    assert rec.fields[1].key == "build"
    assert rec.fields[1].value == "FAILED"
    assert rec.fields[1].level is StatusLevel.ERROR


@respx.mock
def test_bitbucket_pr_build_column_missing_is_dash():
    pr = _pr(1)
    pr["fromRef"].pop("latestCommit")
    respx.get(BASE).mock(return_value=_page([pr]))
    rec = bitbucket_pr(CONN, repo="ABC/r1", fields=["build"])[0]
    assert rec.fields[0].value == "—"
    assert rec.fields[0].level is StatusLevel.NEUTRAL


@respx.mock
def test_bitbucket_pr_mergeable_column():
    respx.get(BASE).mock(return_value=_page([_pr(1)]))
    respx.get("https://bb.example.com/rest/api/1.0/projects/ABC/repos/r1/pull-requests/1/merge").mock(
        return_value=httpx.Response(200, json={"canMerge": False, "conflicted": True})
    )
    rec = bitbucket_pr(CONN, repo="ABC/r1", fields=["id", "mergeable"])[0]
    assert rec.fields[1].key == "mergeable"
    assert rec.fields[1].value == "conflit"
    assert rec.fields[1].level is StatusLevel.ERROR


@respx.mock
def test_bitbucket_pr_mergeable_api_error_is_question_mark():
    respx.get(BASE).mock(return_value=_page([_pr(1)]))
    respx.get("https://bb.example.com/rest/api/1.0/projects/ABC/repos/r1/pull-requests/1/merge").mock(
        return_value=httpx.Response(500)
    )
    rec = bitbucket_pr(CONN, repo="ABC/r1", fields=["mergeable"])[0]
    assert rec.fields[0].value == "?"
```

- [ ] **Step 2: Lancer, vérifier**

Run: `uv run pytest tests/test_providers_bitbucket.py -k "build or mergeable" -v`
Expected: PASS immédiatement (le code existe déjà depuis Task 2). Si un test échoue, c'est un vrai défaut dans `_build_field` / `_mergeable_field` — corriger dans `bitbucket.py`.

- [ ] **Step 3: Suite complète + commit**

```bash
uv run pytest -q
git add -A
git commit -m "Couvre les colonnes build et mergeable de bitbucket_pr"
```

---

## Task 4: `bitbucket.py` — `bitbucket_pr_count` + `bitbucket_my_review` ; `bamboo.py` — `bamboo_plan_status`

**Files:**
- Modify: `pyminidash/providers/bitbucket.py`
- Create: `pyminidash/providers/bamboo.py`
- Modify: `tests/test_providers_bitbucket.py`
- Create: `tests/test_providers_bamboo.py`

**Interfaces:**
- Consumes: Task 2 (`resolve_repos`, `_pr_query`, `_pr_record`, `_DEFAULT_FIELDS`), `_atlassian` (`get_json`, `count_record`, `paginate_v1`, `NotFoundError`, `parse_iso`, `strip_html`), `pyminidash.models` helpers.
- Produces :
  - `bitbucket.py` :
    - `@provider("bitbucket_pr_count") def bitbucket_pr_count(connection, repo=None, repos=None, project=None, state="OPEN", role=None, warn_above=None, error_above=None) -> list[Record]` : somme des PR correspondantes sur les dépôts résolus (compte les éléments via `paginate_v1`) ; renvoie `[count_record("Total", n, warn_above=..., error_above=...)]`. Un dépôt en échec → `log.warning` + continue ; tous en échec → re-lève.
    - `_MY_REVIEW_FIELDS = ["id", "title", "author", "reviewers", "updated"]`.
    - `@provider("bitbucket_my_review") def bitbucket_my_review(connection, repo=None, repos=None, project=None, fields=None, max_results=50) -> list[Record]` : délègue à `bitbucket_pr(connection, repo=repo, repos=repos, project=project, state="OPEN", role="REVIEWER", fields=fields or _MY_REVIEW_FIELDS, max_results=max_results)`.
  - `bamboo.py` :
    - `log = logging.getLogger("pyminidash.providers.bamboo")`.
    - `_STATE_LEVEL = {"Successful": OK, "Failed": ERROR, "InProgress": NEUTRAL, "Unknown": NEUTRAL}`.
    - `_plan_result(connection, plan_key) -> dict | None` : `GET /rest/api/latest/result/{plan_key}/latest?expand=results.result` ; `NotFoundError` → `None` ; si la réponse a `results.result` (liste) → `[0]` ou `None` ; sinon la réponse elle-même.
    - `_plan_field(name, result, base_url, plan_key) -> Field` : mapping du §8 (`plan` → `link` + `role=TITLE`, libellé `planName`/`plan.shortName`/`plan_key`, url `{base_url}/browse/{planResultKey.key or plan_key}` ; `state` → `status` (« — » NEUTRAL si `result` est `None`) ; `number` → `number` `buildNumber` ; `duration` → `duration` `buildDurationInSeconds` ; `finished` → `datetime_` via `parse_iso(buildCompletedTime)` ; `trigger` → `text` `strip_html(buildReason)` ; `tests` → `text` `f"{successfulTestCount or 0} ✓ / {failedTestCount or 0} ✗"`). Inconnu → `text` vide.
    - `_PLAN_STATUS_FIELDS = ["plan", "state", "number", "duration", "finished"]`.
    - `@provider("bamboo_plan_status") def bamboo_plan_status(connection, plans, fields=None) -> list[Record]` : `plans` vide → `ProviderError` ; un record par plan (`_plan_result` puis `_plan_field` par nom, `result` éventuellement `None`).

- [ ] **Step 1: Écrire les tests qui échouent**

Ajouter à `tests/test_providers_bitbucket.py` :
```python
from pyminidash.providers.bitbucket import bitbucket_my_review, bitbucket_pr_count


@respx.mock
def test_bitbucket_pr_count_sums_repos():
    respx.get("https://bb.example.com/rest/api/1.0/projects/ABC/repos/r1/pull-requests").mock(
        return_value=_page([_pr(1), _pr(2)]))
    respx.get("https://bb.example.com/rest/api/1.0/projects/ABC/repos/r2/pull-requests").mock(
        return_value=_page([_pr(3)]))
    rec = bitbucket_pr_count(CONN, repos=["ABC/r1", "ABC/r2"], warn_above=2, error_above=5)[0]
    assert rec.fields[0].value == "3"
    assert rec.fields[0].level is StatusLevel.WARN


@respx.mock
def test_bitbucket_my_review_uses_reviewer_role():
    route = respx.get(BASE).mock(return_value=_page([_pr(1)]))
    records = bitbucket_my_review(CONN, repo="ABC/r1")
    assert [x.key for x in records[0].fields] == ["id", "title", "author", "reviewers", "updated"]
    url = str(route.calls.last.request.url)
    assert "role.1=REVIEWER" in url and "username.1=jdupont" in url
```

`tests/test_providers_bamboo.py` :
```python
import httpx
import pytest
import respx

from pyminidash.connection import Connection
from pyminidash.errors import ProviderError
from pyminidash.models import FieldRole, FieldType, StatusLevel
from pyminidash.providers.bamboo import bamboo_plan_status

CONN = Connection(name="bam", base_url="https://bam.example.com", token="PAT", user="jdupont")


def _result(key="PROJ-PLAN-42", state="Successful", num=42):
    return {
        "planResultKey": {"key": key},
        "planName": "Mon Plan",
        "buildState": state,
        "buildNumber": num,
        "buildDurationInSeconds": 125,
        "buildCompletedTime": "2026-08-20T14:30:00Z",
        "buildReason": 'Manual run by <a href="x">Jean</a>',
        "successfulTestCount": 142,
        "failedTestCount": 3,
    }


def _latest(result):
    return httpx.Response(200, json=result)


def test_bamboo_plan_status_empty_plans_raises():
    with pytest.raises(ProviderError, match="plans"):
        bamboo_plan_status(CONN, plans=[])


@respx.mock
def test_bamboo_plan_status_maps_fields():
    respx.get("https://bam.example.com/rest/api/latest/result/PROJ-PLAN/latest").mock(
        return_value=_latest(_result()))
    rec = bamboo_plan_status(CONN, plans=["PROJ-PLAN"])[0]
    f = rec.fields
    assert [x.key for x in f] == ["plan", "state", "number", "duration", "finished"]
    assert f[0].type is FieldType.LINK and f[0].role is FieldRole.TITLE
    assert f[0].url == "https://bam.example.com/browse/PROJ-PLAN-42"
    assert f[1].type is FieldType.STATUS and f[1].level is StatusLevel.OK
    assert f[2].value == 42
    assert f[3].type is FieldType.DURATION
    assert f[4].type is FieldType.DATETIME


@respx.mock
def test_bamboo_plan_status_never_built_is_dash():
    respx.get("https://bam.example.com/rest/api/latest/result/PROJ-NOPE/latest").mock(
        return_value=httpx.Response(404))
    rec = bamboo_plan_status(CONN, plans=["PROJ-NOPE"])[0]
    assert rec.fields[0].value == "PROJ-NOPE"   # libellé = clé du plan
    assert rec.fields[1].value == "—" and rec.fields[1].level is StatusLevel.NEUTRAL


@respx.mock
def test_bamboo_plan_status_wrapped_results():
    respx.get("https://bam.example.com/rest/api/latest/result/PROJ-PLAN/latest").mock(
        return_value=httpx.Response(200, json={"results": {"result": [_result(state="Failed")]}}))
    rec = bamboo_plan_status(CONN, plans=["PROJ-PLAN"])[0]
    assert rec.fields[1].level is StatusLevel.ERROR


@respx.mock
def test_bamboo_plan_status_optional_fields():
    respx.get("https://bam.example.com/rest/api/latest/result/PROJ-PLAN/latest").mock(
        return_value=_latest(_result()))
    rec = bamboo_plan_status(CONN, plans=["PROJ-PLAN"], fields=["plan", "trigger", "tests"])[0]
    assert rec.fields[1].value == "Manual run by Jean"
    assert rec.fields[2].value == "142 ✓ / 3 ✗"
```

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `uv run pytest tests/test_providers_bitbucket.py tests/test_providers_bamboo.py -v`
Expected: FAIL — `ImportError: cannot import name 'bitbucket_pr_count'` / `No module named 'pyminidash.providers.bamboo'`

- [ ] **Step 3: Ajouter à `pyminidash/providers/bitbucket.py`**

```python
_MY_REVIEW_FIELDS = ["id", "title", "author", "reviewers", "updated"]


@provider("bitbucket_pr_count")
def bitbucket_pr_count(connection, repo=None, repos=None, project=None,
                       state="OPEN", role=None, warn_above=None,
                       error_above=None) -> list[Record]:
    state = str(state).upper()
    if state not in _STATES:
        raise ProviderError(
            f"bitbucket_pr_count : state '{state}' invalide (OPEN, MERGED, DECLINED, ALL)"
        )
    if role not in _ROLES:
        raise ProviderError(f"bitbucket_pr_count : role '{role}' invalide")
    if role is not None and not connection.user:
        raise ProviderError(
            f"connexion '{connection.name}' : renseignez user pour filtrer par rôle"
        )
    targets = resolve_repos(connection, repo=repo, repos=repos, project=project)
    query = _pr_query(state, role, connection)

    total = 0
    last_error: AtlassianError | None = None
    ok_repos = 0
    for proj, slug in targets:
        path = f"/rest/api/1.0/projects/{proj}/repos/{slug}/pull-requests"
        try:
            total += sum(
                1 for _ in paginate_v1(connection, path, params=query, hard_cap=_HARD_CAP)
            )
        except AtlassianError as exc:
            last_error = exc
            log.warning("bitbucket_pr_count : dépôt %s/%s : %s", proj, slug, exc)
            continue
        ok_repos += 1

    if ok_repos == 0 and last_error is not None:
        raise last_error
    return [count_record("Total", total, warn_above=warn_above, error_above=error_above)]


@provider("bitbucket_my_review")
def bitbucket_my_review(connection, repo=None, repos=None, project=None,
                        fields=None, max_results=50) -> list[Record]:
    return bitbucket_pr(
        connection, repo=repo, repos=repos, project=project,
        state="OPEN", role="REVIEWER",
        fields=fields or _MY_REVIEW_FIELDS, max_results=max_results,
    )
```

- [ ] **Step 4: Écrire `pyminidash/providers/bamboo.py`**

```python
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
```

- [ ] **Step 5: Lancer, vérifier le succès**

Run: `uv run pytest tests/test_providers_bitbucket.py tests/test_providers_bamboo.py -v`
Expected: PASS (Bitbucket : 12 + 4 + 2 ; Bamboo : 6).

- [ ] **Step 6: Suite complète + commit**

```bash
uv run pytest -q
git add -A
git commit -m "Ajoute bitbucket_pr_count, bitbucket_my_review et bamboo_plan_status"
```

---

## Task 5: `bamboo.py` — `bamboo_user_builds` + `bamboo_plan_health`

**Files:**
- Modify: `pyminidash/providers/bamboo.py`
- Modify: `tests/test_providers_bamboo.py`

**Interfaces:**
- Consumes: `_plan_result`, `_plan_field`, `_STATE_LEVEL` (Task 4), `_atlassian` (`get_json`, `count_record`, `strip_html`).
- Produces :
  - `_USER_BUILDS_FIELDS = ["plan", "state", "number", "finished", "duration"]`.
  - `@provider("bamboo_user_builds") def bamboo_user_builds(connection, user=None, max_results=25, scan=100) -> list[Record]` :
    - `who = user or connection.user` ; `None` → `ProviderError` (« renseignez user … »).
    - `GET /rest/api/latest/result?expand=results.result&max-results={min(scan, 100)}`.
    - garde les résultats dont `strip_html(buildReason)` contient `who` (insensible à la casse), tronqués à `max_results`.
    - un record par résultat via `_plan_field` sur `_USER_BUILDS_FIELDS` (plan_key = `_plan_key_of(result, "")`).
  - `@provider("bamboo_plan_health") def bamboo_plan_health(connection, plans) -> list[Record]` :
    - `plans` vide → `ProviderError`.
    - `_plan_result` par plan ; compte `buildState == "Successful"` (green) et `== "Failed"` (red).
    - renvoie **un** record : `text("title", "Santé des plans", f"{green} vert / {red} rouge")`, `number("green", "Au vert", green, summary=True)`, `number("red", "Au rouge", red, summary=True)`, `status("status", "Global", "KO" if red else "OK", level=ERROR if red else OK, role=FieldRole.BADGE, summary=True)`.

- [ ] **Step 1: Ajouter les tests qui échouent** — `tests/test_providers_bamboo.py`

```python
from pyminidash.providers.bamboo import bamboo_plan_health, bamboo_user_builds


def _results_page(results):
    return httpx.Response(200, json={"results": {"result": results}})


@respx.mock
def test_bamboo_user_builds_filters_by_reason():
    mine = _result(key="P-A-1", num=1)
    mine["buildReason"] = 'Manual run by <a>jdupont</a>'
    other = _result(key="P-B-2", num=2)
    other["buildReason"] = "Changes by someone else"
    respx.get("https://bam.example.com/rest/api/latest/result").mock(
        return_value=_results_page([mine, other]))
    records = bamboo_user_builds(CONN)   # user par défaut = connection.user = "jdupont"
    assert len(records) == 1
    assert [x.key for x in records[0].fields] == ["plan", "state", "number", "finished", "duration"]
    assert records[0].fields[2].value == 1


def test_bamboo_user_builds_no_user_raises():
    no_user = Connection(name="bam", base_url="https://bam.example.com", token="X")
    with pytest.raises(ProviderError, match="user"):
        bamboo_user_builds(no_user)


@respx.mock
def test_bamboo_user_builds_explicit_user_and_limit():
    results = []
    for i in range(5):
        r = _result(key=f"P-X-{i}", num=i)
        r["buildReason"] = "run by alice"
        results.append(r)
    respx.get("https://bam.example.com/rest/api/latest/result").mock(
        return_value=_results_page(results))
    records = bamboo_user_builds(CONN, user="alice", max_results=3)
    assert len(records) == 3


@respx.mock
def test_bamboo_plan_health_counts():
    respx.get("https://bam.example.com/rest/api/latest/result/P-A/latest").mock(
        return_value=_latest(_result(state="Successful")))
    respx.get("https://bam.example.com/rest/api/latest/result/P-B/latest").mock(
        return_value=_latest(_result(state="Failed")))
    respx.get("https://bam.example.com/rest/api/latest/result/P-C/latest").mock(
        return_value=httpx.Response(404))
    rec = bamboo_plan_health(CONN, plans=["P-A", "P-B", "P-C"])[0]
    assert rec.fields[1].value == 1   # green
    assert rec.fields[2].value == 1   # red
    assert rec.fields[3].level is StatusLevel.ERROR


def test_bamboo_plan_health_empty_raises():
    with pytest.raises(ProviderError, match="plans"):
        bamboo_plan_health(CONN, plans=[])
```

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `uv run pytest tests/test_providers_bamboo.py -k "user_builds or health" -v`
Expected: FAIL — `ImportError: cannot import name 'bamboo_user_builds'`

- [ ] **Step 3: Ajouter à `pyminidash/providers/bamboo.py`**

```python
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
```

- [ ] **Step 4: Lancer, vérifier le succès**

Run: `uv run pytest tests/test_providers_bamboo.py -v`
Expected: PASS (6 + 5 tests)

- [ ] **Step 5: Suite complète + commit**

```bash
uv run pytest -q
git add -A
git commit -m "Ajoute bamboo_user_builds et bamboo_plan_health"
```

---

## Task 6: `bamboo.py` — `bamboo_running`

**Files:**
- Modify: `pyminidash/providers/bamboo.py`
- Modify: `tests/test_providers_bamboo.py`

**Interfaces:**
- Consumes: `_plan_result`, `_plan_key_of` (Task 4), `_atlassian` (`get_json`, `parse_iso`).
- Produces :
  - `_running_record(base_url, source, state_label) -> Record` : `source` est soit un résultat Bamboo, soit un `queuedBuild`. Champs (fixes) : `plan` (`link` + `role=TITLE`, libellé `planName`/`plan.shortName`/clé), `state` (`status` NEUTRAL = `state_label`), `number` (`number` `buildNumber`), `started` (`datetime_` via `parse_iso(buildStartedTime)`), `progress` (`text` = `progress.percentageCompletedPretty` ou `""`).
  - `@provider("bamboo_running") def bamboo_running(connection, plans=None, project=None) -> list[Record]` :
    - exactement un de `plans` / `project` (sinon `ProviderError`) ; `plans` fourni mais vide → `ProviderError`.
    - **en file** : `GET /rest/api/latest/queue?expand=queuedBuilds` → `queuedBuilds.queuedBuild[]` → `_running_record(..., "En file")`.
    - **en cours** : liste de clés = `plans`, ou (si `project`) `GET /rest/api/latest/project/{project}?expand=plans` → `plans.plan[].key` ; pour chaque clé, `_plan_result` et retenir `lifeCycleState == "InProgress"` → `_running_record(..., "En cours")`.

- [ ] **Step 1: Ajouter les tests qui échouent** — `tests/test_providers_bamboo.py`

```python
from pyminidash.providers.bamboo import bamboo_running


@respx.mock
def test_bamboo_running_queue_and_in_progress():
    respx.get("https://bam.example.com/rest/api/latest/queue").mock(
        return_value=httpx.Response(200, json={"queuedBuilds": {"queuedBuild": [
            {"planName": "Plan Q", "planResultKey": {"key": "P-Q-9"}, "buildNumber": 9}
        ]}}))
    running = _result(key="P-A-5", num=5)
    running["lifeCycleState"] = "InProgress"
    running["buildState"] = "Unknown"
    running["progress"] = {"percentageCompletedPretty": "62%"}
    respx.get("https://bam.example.com/rest/api/latest/result/P-A/latest").mock(
        return_value=_latest(running))
    records = bamboo_running(CONN, plans=["P-A"])
    labels = {r.fields[1].value for r in records}
    assert labels == {"En file", "En cours"}
    prog = [r.fields[4].value for r in records if r.fields[1].value == "En cours"][0]
    assert prog == "62%"


@respx.mock
def test_bamboo_running_skips_finished_plans():
    done = _result(key="P-A-5")
    done["lifeCycleState"] = "Finished"
    respx.get("https://bam.example.com/rest/api/latest/queue").mock(
        return_value=httpx.Response(200, json={"queuedBuilds": {"queuedBuild": []}}))
    respx.get("https://bam.example.com/rest/api/latest/result/P-A/latest").mock(
        return_value=_latest(done))
    assert bamboo_running(CONN, plans=["P-A"]) == []


def test_bamboo_running_needs_exactly_one_target():
    with pytest.raises(ProviderError, match="exactement un"):
        bamboo_running(CONN)
    with pytest.raises(ProviderError, match="exactement un"):
        bamboo_running(CONN, plans=["P-A"], project="P")


@respx.mock
def test_bamboo_running_project_expands_plans():
    respx.get("https://bam.example.com/rest/api/latest/queue").mock(
        return_value=httpx.Response(200, json={"queuedBuilds": {"queuedBuild": []}}))
    respx.get("https://bam.example.com/rest/api/latest/project/PROJ").mock(
        return_value=httpx.Response(200, json={"plans": {"plan": [{"key": "PROJ-A"}, {"key": "PROJ-B"}]}}))
    ip = _result(key="PROJ-A-1")
    ip["lifeCycleState"] = "InProgress"
    respx.get("https://bam.example.com/rest/api/latest/result/PROJ-A/latest").mock(
        return_value=_latest(ip))
    respx.get("https://bam.example.com/rest/api/latest/result/PROJ-B/latest").mock(
        return_value=httpx.Response(404))
    records = bamboo_running(CONN, project="PROJ")
    assert len(records) == 1 and records[0].fields[0].value == "Mon Plan"
```

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `uv run pytest tests/test_providers_bamboo.py -k running -v`
Expected: FAIL — `ImportError: cannot import name 'bamboo_running'`

- [ ] **Step 3: Ajouter à `pyminidash/providers/bamboo.py`**

```python
def _running_record(base_url, source, state_label):
    s = source or {}
    prk = _plan_key_of(s, s.get("planKey") or "")
    label = s.get("planName") or (s.get("plan") or {}).get("shortName") or prk or "?"
    prog = (s.get("progress") or {}).get("percentageCompletedPretty") or ""
    return Record(
        link("plan", "Plan", label, url=f"{base_url}/browse/{prk}",
             role=FieldRole.TITLE),
        status("state", "État", state_label, level=StatusLevel.NEUTRAL, summary=True),
        number("number", "Build", s.get("buildNumber")),
        datetime_("started", "Démarré", parse_iso(s.get("buildStartedTime"))),
        text("progress", "Avancement", prog),
    )


@provider("bamboo_running")
def bamboo_running(connection, plans=None, project=None) -> list[Record]:
    given = [x for x in (plans, project) if x is not None]
    if len(given) != 1:
        raise ProviderError(
            "bamboo_running : indiquez exactement un de plans / project"
        )
    if plans is not None and not plans:
        raise ProviderError("bamboo_running : 'plans' ne doit pas être vide")

    out: list[Record] = []
    queue = get_json(connection, "/rest/api/latest/queue",
                     params={"expand": "queuedBuilds"})
    for qb in (queue.get("queuedBuilds") or {}).get("queuedBuild") or []:
        out.append(_running_record(connection.base_url, qb, "En file"))

    keys = plans
    if project is not None:
        proj = get_json(connection, f"/rest/api/latest/project/{project}",
                        params={"expand": "plans"})
        keys = [
            p.get("key")
            for p in (proj.get("plans") or {}).get("plan") or []
            if p.get("key")
        ]
    for plan_key in keys or []:
        result = _plan_result(connection, plan_key)
        if result and result.get("lifeCycleState") == "InProgress":
            out.append(_running_record(connection.base_url, result, "En cours"))
    return out
```

- [ ] **Step 4: Lancer, vérifier le succès**

Run: `uv run pytest tests/test_providers_bamboo.py -v`
Expected: PASS (tous)

- [ ] **Step 5: Suite complète + commit**

```bash
uv run pytest -q
git add -A
git commit -m "Ajoute bamboo_running (builds en cours et en file)"
```

---

## Task 7: Câblage — enregistrement, config d'exemple, doc, intégration

**Files:**
- Modify: `pyminidash/providers/__init__.py`
- Modify: `config.example.toml`, `README.md`
- Modify: `tests/test_integration_atlassian.py`
- Modify: `tests/test_example_config.py` (si besoin)

**Interfaces:**
- Consumes: tous les providers Bitbucket/Bamboo (Tasks 2-6).
- Produces : `bitbucket` et `bamboo` importés dans `providers/__init__.py` → les 7 providers sont enregistrés ; `config.example.toml` a des connexions et blocs Bitbucket/Bamboo valides ; README à jour ; un test d'intégration `bitbucket_pr` bout-en-bout.

- [ ] **Step 1: Écrire le test qui échoue** — ajouter à `tests/test_integration_atlassian.py`

```python
import respx as _respx


@_respx.mock
def test_bitbucket_block_renders_table_fragment():
    from pyminidash.config import Config
    from pyminidash.connection import build_connections
    from pyminidash.web.app import create_app

    config = Config.model_validate({
        "connections": {"bb": {"base_url": "https://bb.example.com", "token": "bb", "user": "jdupont"}},
        "groups": [{
            "id": "bb", "title": "Bitbucket", "type": "table",
            "blocks": [{
                "provider": "bitbucket_pr", "connection": "bb", "title": "PR ouvertes",
                "params": {"repo": "ABC/r1", "fields": ["id", "title", "author"]},
            }],
        }],
    })
    connections = build_connections(config, {"bb": "PAT"})
    client = TestClient(create_app(config, connections))

    _respx.get("https://bb.example.com/rest/api/1.0/projects/ABC/repos/r1/pull-requests").mock(
        return_value=httpx.Response(200, json={"values": [{
            "id": 7, "title": "Corrige le cache", "state": "OPEN",
            "author": {"user": {"displayName": "Sam"}},
            "reviewers": [], "fromRef": {"displayId": "fix"}, "toRef": {"displayId": "main"},
            "updatedDate": 1_724_500_000_000,
            "links": {"self": [{"href": "https://bb.example.com/pr/7"}]},
        }], "isLastPage": True}))

    html = client.get("/groups/bb/blocks/0").text
    assert "<th>PR</th>" in html
    assert "#7" in html and "Corrige le cache" in html and "Sam" in html
    assert "https://bb.example.com/pr/7" in html
```

*(`TestClient`, `httpx` sont déjà importés en tête du fichier depuis le Plan A.)*

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `uv run pytest tests/test_integration_atlassian.py -k bitbucket -v`
Expected: FAIL — `bitbucket_pr` non enregistré → `ConfigError` (« provider inconnu ») au `Config.model_validate`.

- [ ] **Step 3: Modifier `pyminidash/providers/__init__.py`**

```python
"""Import des modules de providers intégrés → enregistrement au chargement."""
from pyminidash.providers import bamboo, bitbucket, http, jira, system  # noqa: F401
```

- [ ] **Step 4: Lancer, vérifier le succès**

Run: `uv run pytest tests/test_integration_atlassian.py -v`
Expected: PASS (le test Jira existant + le nouveau Bitbucket)

- [ ] **Step 5: Modifier `config.example.toml`**

Décommenter les deux sections de connexion (retirer les `#` de tête) :
```toml
[connections.bitbucket]
base_url = "https://bitbucket.interne.example.com"
token    = "bitbucket"
user     = "jdupont"

[connections.bamboo]
base_url = "https://bamboo.interne.example.com"
token    = "bamboo"
user     = "jdupont"
```

Dans le groupe `[[groups]]` d'id `mon-activite`, ajouter deux blocs après le bloc `jira_my_issues` :
```toml
  [[groups.blocks]]
  title      = "PR à relire"
  provider   = "bitbucket_my_review"
  connection = "bitbucket"
  params     = { project = "ABC" }

  [[groups.blocks]]
  title      = "Mes derniers builds"
  provider   = "bamboo_user_builds"
  connection = "bamboo"
```

- [ ] **Step 6: Vérifier `tests/test_example_config.py`**

Run: `uv run pytest tests/test_example_config.py -v`
Expected: PASS. `load_config` valide que `bitbucket_my_review` / `bamboo_user_builds` existent (ils sont enregistrés via `providers/__init__.py`) et que leurs connexions sont déclarées. `load_config` ne touche pas aux secrets → pas besoin de `secrets.toml`. Si un `assert` sur le nombre de groupes casse, l'ajuster (le nombre est inchangé, seuls des blocs sont ajoutés).

- [ ] **Step 7: Modifier `README.md`**

Dans le tableau des providers, ajouter :
```markdown
| `bitbucket_pr` | Pull requests d'un dépôt / d'une liste / d'un projet | `repo` \| `repos` \| `project`, `state`, `role`, `fields`, `stale_days`, `max_results` |
| `bitbucket_pr_count` | Compteur de PR (avec seuils) | idem portée + `state`, `role`, `warn_above`, `error_above` |
| `bitbucket_my_review` | PR ouvertes où je suis reviewer (exige `user`) | portée + `fields`, `max_results` |
| `bamboo_plan_status` | Dernier build de chaque plan | `plans`, `fields` |
| `bamboo_user_builds` | Builds récents déclenchés par un utilisateur | `user` (défaut = `connection.user`), `max_results`, `scan` |
| `bamboo_plan_health` | Compteur vert / rouge sur une liste de plans | `plans` |
| `bamboo_running` | Builds en cours et en file | `plans` \| `project` |
```

Ajouter une phrase dans la section « Connexions et secrets » : les colonnes optionnelles `build` / `mergeable` de `bitbucket_pr` déclenchent un appel d'API supplémentaire par PR.

- [ ] **Step 8: Suite complète + smoke**

Run: `uv run pytest -q`
Expected: tout vert.

Smoke (sans réseau — juste vérifier que la config d'exemple se valide sans `secrets.toml`) :
```bash
uv run pyminidash --config config.example.toml --port 8791
```
Attendu : `Erreur de configuration : connexion 'jira' : la clé de token déclarée est absente de secrets.toml ...` sur stderr, code 2 (pas de `secrets.toml`). *(Le message peut nommer `jira`, `bitbucket` ou `bamboo` — l'ordre d'itération du dict.)*

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "Enregistre les providers Bitbucket/Bamboo, complète config d'exemple et doc"
```

---

## Self-Review

**Spec coverage :**

| Spec | Tâche |
|---|---|
| §5 `paginate` (style Bitbucket 1.0) | 1 (`paginate_v1`) |
| §5 `strip_html` | 1 |
| §5 `resolve_repos` | 2 *(placé dans `bitbucket.py`, pas `_atlassian.py` — voir ruling)* |
| §5 `count_record` (Bitbucket) | 2, 4 (réutilisé, déjà livré Plan A) |
| §7 `bitbucket_pr` (portée dépôt/liste/projet, `state`, `role`, `stale_days`, tri, cap) | 2 |
| §7 mapping des champs PR (`id`/`title`/`author`/`reviewers`/`branches`/`state`/`updated`/`comments`/`tasks`) | 2 |
| §7 colonnes optionnelles `build` / `mergeable` (1 appel/PR) | 2 (code) + 3 (couverture) |
| §7 `bitbucket_pr_count` | 4 |
| §7 `bitbucket_my_review` (raccourci `role=REVIEWER`, exige `user`) | 4 |
| §7 erreurs : `404` nommé, agrégation partielle, `401`/réseau/TLS | 2 (via `get_json` + ruling marqueurs) |
| §8 `bamboo_plan_status` (mapping, `404` → « — ») | 4 |
| §8 `bamboo_user_builds` (`user` défaut connexion, filtrage client sur `buildReason`) | 5 |
| §8 `bamboo_plan_health` (compteur vert/rouge + badge) | 5 |
| §8 `bamboo_running` (`queue` + `InProgress`, `plans` ou `project`) | 6 |
| §8 erreurs Bamboo (`401`/réseau/TLS via `get_json` ; `404` plan → « — ») | 4, 5, 6 |
| §9 `user` requis absent → message clair | 2 (`bitbucket_pr` role), 5 (`bamboo_user_builds`) |
| §9 records homogènes vs marqueur d'erreur | ruling (log + continue / re-lève) |
| §11 `config.example.toml` connexions + blocs Bitbucket/Bamboo | 7 |
| §10 `providers/__init__.py` importe `bitbucket`, `bamboo` | 7 |
| §12 tests par couche, `respx`, intégration | chaque tâche + 7 |

Aucun trou dans le périmètre du Plan B. (`field_record` de §5 : non nécessaire — chaque module a son mapping `_*_field`, cohérent avec `jira._issue_field` livré au Plan A.)

**Placeholder scan :** aucun `TODO`/`TBD` ; chaque étape de code porte un bloc complet. Task 3 est une tâche de **couverture** (le code vient de Task 2) — explicite, pas un placeholder.

**Type consistency :**
- `paginate_v1(connection, path, *, params=None, hard_cap=200, timeout=15.0)` : identique Task 1 (déf) et Tasks 2/4 (appel).
- `resolve_repos(connection, *, repo=None, repos=None, project=None) -> list[tuple[str,str]]` : Task 2 (déf), Task 4 (appel `bitbucket_pr_count`).
- `_pr_query(state, role, connection)` : Task 2 (déf), Task 4 (appel).
- `_plan_result(connection, plan_key) -> dict | None`, `_plan_field(name, result, base_url, plan_key)`, `_plan_key_of(result, fallback)` : Task 4 (déf), Tasks 5/6 (appel).
- `count_record(label, count, *, warn_above, error_above)` : signature du Plan A, respectée Tasks 2/4.
- `epoch_ms_to_dt` / `parse_iso` / `strip_html` : Task 1 (déf), Tasks 2/4/5/6 (appel).
- `bitbucket_pr(connection, repo, repos, project, state, role, fields, stale_days, max_results)` : Task 2 (déf), Task 4 (`bitbucket_my_review` délègue avec les bons kwargs).
- `_running_record(base_url, source, state_label)` : Task 6 (déf + appels internes).
- Tous les providers : `connection` en 1er param sans défaut → « exige une connexion » (validation Plan A).

**Rulings pris dans ce plan :**
- **Marqueurs d'erreur d'agrégation abandonnés** au profit d'un `log.warning` + continuation (re-lève si tout échoue). Raison : incompatibles avec la contrainte de records homogènes que la spec pose elle-même. Coût si erroné : re-travail sur `bitbucket_pr` pour un rendu de marqueur homogène.
- **`resolve_repos` dans `bitbucket.py`** et non `_atlassian.py` (§5 le listait dans `_atlassian.py`). Raison : c'est du 100 % API Bitbucket 1.0, aucun autre module ne l'utilise. Coût si erroné : un déplacement de fonction.
- **`bamboo_plan_health` record** : ordre `title, green, red, status` (la spec liste les 4 sans ordre). Cohérent avec les autres compteurs. Coût si erroné : réordonner 4 champs.
- **`_plan_result` accepte les deux formes de réponse** (`/latest` direct ou `{results:{result:[...]}}`) selon la version de Bamboo. Coût si erroné : un `if` en trop.
