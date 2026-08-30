# Provider `local_projects` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter un provider `local_projects` qui scanne des répertoires du disque, y découvre les projets (Maven, npm/Angular, Cargo, Go, Python) et produit une `list[Record]` homogène avec identité/version, stack technique et état Git.

**Architecture:** Un sous-package `pyminidash/providers/localproj/` : `discovery` (scan filesystem), `gitinfo` (subprocess `git`), un parser par écosystème (`maven`, `node`, `cargo`, `gomod`, `python`), `record` (assemblage des 16 champs + application du paramètre `show`), `__init__` (orchestration, `@provider`, parallélisation Git). Deux petites extensions transverses : un hook de validation config par provider dans `registry`/`config`, et le masquage des champs repliés vides dans `web/render`.

**Tech Stack:** Python 3.11, stdlib uniquement (`xml.etree.ElementTree`, `json`, `tomllib`, `subprocess`, `concurrent.futures`, `fnmatch`, `pathlib`), Pydantic v2 (config existante), pytest.

**Spec:** `docs/superpowers/specs/2026-08-30-pyminidash-local-projects-design.md`

## Global Constraints

- **Aucune nouvelle dépendance.** Stdlib d'abord ; pas de lib Git embarquée (on invoque le binaire `git`).
- Tout module Python commence par `from __future__ import annotations`.
- Cible Python **3.11** (`tomllib` disponible).
- Commentaires, libellés de `Field` et messages d'erreur **en français**.
- Les records d'un bloc doivent être **homogènes** (mêmes `.keys()`), garanti ici par un constructeur unique `to_record`.
- `local_projects` est **`connection`-less** (pas de paramètre `connection`, comme `disk_usage`).
- Un provider faisant de l'I/O bloquante borne lui-même ses appels : chaque invocation `git` porte `timeout=5`.
- Tests exécutés via `./.venv/Scripts/python.exe -m pytest` (le sandbox peut figer `uv run pytest`).
- Style de commit du repo : message en français, à l'impératif/présent (« Ajoute… », « Corrige… »), terminé par la ligne `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.
- Convention providers : fonction décorée `@provider("nom")` dans `pyminidash/providers/`, importée depuis `pyminidash/providers/__init__.py`.

---

## File Structure

**Créés :**

| Fichier | Responsabilité |
|---|---|
| `pyminidash/providers/localproj/__init__.py` | `@provider("local_projects", validate=_validate_cfg)` ; orchestration ; `_parse_all` ; `ThreadPoolExecutor` pour Git. |
| `pyminidash/providers/localproj/discovery.py` | `ProjectDir`, `find_projects`, `ALWAYS_IGNORE`. |
| `pyminidash/providers/localproj/gitinfo.py` | `GitInfo`, `git_info`, `git_on_path`. |
| `pyminidash/providers/localproj/maven.py` | `MavenInfo`, `parse_maven` (pom + `${}` + parent sur disque + frontend-maven-plugin + sous-scan Angular via `node.parse_node`). |
| `pyminidash/providers/localproj/node.py` | `NodeInfo`, `parse_node`. |
| `pyminidash/providers/localproj/cargo.py` | `CargoInfo`, `parse_cargo`. |
| `pyminidash/providers/localproj/gomod.py` | `GoInfo`, `parse_gomod`. |
| `pyminidash/providers/localproj/python.py` | `PythonInfo`, `parse_python`. |
| `pyminidash/providers/localproj/record.py` | `ParsedProject`, `KNOWN_FIELDS`, `to_record`, `relative_date`. |
| `tests/test_providers_localproj_discovery.py` | Tests de `discovery`. |
| `tests/test_providers_localproj_gitinfo.py` | Tests de `gitinfo` (vrais dépôts en `tmp_path`). |
| `tests/test_providers_localproj_parsers.py` | Tests de `node`/`cargo`/`gomod`/`python`. |
| `tests/test_providers_localproj_maven.py` | Tests de `maven`. |
| `tests/test_providers_localproj_record.py` | Tests de `record`. |
| `tests/test_providers_localproj.py` | Tests d'intégration du provider + validation config. |

**Modifiés :**

| Fichier | Changement |
|---|---|
| `pyminidash/registry.py` | Champ `validate` sur `ProviderDef` ; param `validate` du décorateur. |
| `pyminidash/config.py` | Appel de `pdef.validate(block.params)` dans `_cross_checks`. |
| `pyminidash/web/render.py` | `to_cards` ignore les champs repliés vides. |
| `pyminidash/providers/__init__.py` | Importer `localproj`. |
| `config.example.toml` | Bloc d'exemple `local_projects` (avec `timeout = 60`). |
| `README.md` | Ligne dans le tableau des providers. |
| `docs/ETAT.md` | Provider livré, dette « projet local » close. |
| `tests/test_registry.py` | Test du hook `validate`. |
| `tests/test_render.py` | Test du masquage des champs repliés vides. |

---

## Task 1 : Hook de validation config par provider

**Files:**
- Modify: `pyminidash/registry.py`
- Modify: `pyminidash/config.py` (dans `_cross_checks`, après le bloc `validate_params`)
- Test: `tests/test_registry.py`, `tests/test_config.py`

**Interfaces:**
- Consumes: rien.
- Produces :
  - `ProviderDef` gagne un champ `validate: Callable[[dict], None] | None = None`.
  - `provider(name: str, *, validate: Callable[[dict], None] | None = None)` — le décorateur accepte un validateur optionnel. Un validateur reçoit `block.params` (dict) et lève `ValueError` si invalide.
  - `config._cross_checks` appelle `pdef.validate(block.params)` s'il est défini et transforme `ValueError` en `ConfigError` préfixée par la localisation du bloc (`f"{where}: {exc}"`).

- [ ] **Step 1 : Écrire le test du décorateur (registry)**

Dans `tests/test_registry.py`, ajouter :

```python
def test_provider_accepts_optional_validate_hook():
    def _v(params):
        if params.get("bad"):
            raise ValueError("param bad interdit")

    @provider("withval", validate=_v)
    def withval(x: int = 1):
        return []

    pdef = get_provider("withval")
    assert pdef.validate is _v
    pdef.validate({"bad": False})           # ne lève pas
    with pytest.raises(ValueError, match="bad interdit"):
        pdef.validate({"bad": True})


def test_provider_validate_defaults_to_none():
    @provider("noval")
    def noval():
        return []

    assert get_provider("noval").validate is None
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_registry.py -q`
Expected : FAIL (`TypeError: provider() got an unexpected keyword argument 'validate'` / `AttributeError: ... 'validate'`).

- [ ] **Step 3 : Implémenter dans `registry.py`**

```python
@dataclass(frozen=True)
class ProviderDef:
    name: str
    func: Callable[..., list]
    signature: inspect.Signature
    validate: Callable[[dict], None] | None = None


def provider(
    name: str, *, validate: Callable[[dict], None] | None = None
) -> Callable[[Callable[..., list]], Callable[..., list]]:
    def decorator(func: Callable[..., list]) -> Callable[..., list]:
        if name in REGISTRY:
            raise ValueError(f"provider '{name}' déjà enregistré")
        REGISTRY[name] = ProviderDef(
            name=name, func=func, signature=inspect.signature(func),
            validate=validate,
        )
        return func

    return decorator
```

- [ ] **Step 4 : Lancer, vérifier le succès (registry)**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_registry.py -q`
Expected : PASS.

- [ ] **Step 5 : Écrire le test config**

Dans `tests/test_config.py`, ajouter (le fichier a déjà `_write`, `pytest`, `ConfigError`, `load_config`) :

```python
def test_provider_validate_hook_raises_configerror(tmp_path, monkeypatch):
    from pyminidash.registry import REGISTRY, provider

    def _v(params):
        if "show" in params:
            raise ValueError("show interdit ici")

    @provider("needs_val", validate=_v)
    def needs_val(x: int = 1):
        return []

    p = _write(tmp_path, """
        [[groups]]
        id = "g"
        title = "G"
        type = "table"
          [[groups.blocks]]
          provider = "needs_val"
          params = { show = ["a"] }
    """)
    with pytest.raises(ConfigError, match="show interdit ici"):
        load_config(p)
```

(Le nettoyage du registre est assuré par la fixture autouse `_registry_snapshot` de `conftest.py`.)

- [ ] **Step 6 : Lancer, vérifier l'échec**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_config.py::test_provider_validate_hook_raises_configerror -q`
Expected : FAIL (`DID NOT RAISE` ou pas de match).

- [ ] **Step 7 : Implémenter dans `config.py`**

Dans `_cross_checks`, juste après le bloc `try: validate_params(...) except ValueError ...` et avant la fin de la boucle `for i, block` :

```python
                if pdef.validate is not None:
                    try:
                        pdef.validate(block.params)
                    except ValueError as exc:
                        raise ValueError(f"{where}: {exc}") from None
```

- [ ] **Step 8 : Lancer toute la suite**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_registry.py tests/test_config.py -q`
Expected : PASS (providers existants inchangés — aucun n'a de `validate`).

- [ ] **Step 9 : Commit**

```bash
git add pyminidash/registry.py pyminidash/config.py tests/test_registry.py tests/test_config.py
git commit -m "$(printf 'Ajoute un hook de validation config par provider\n\nProviderDef.validate optionnel, appelE dans _cross_checks : un provider\npeut valider ses params au demarrage et lever ConfigError localisee.\n\nCo-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>')"
```

---

## Task 2 : Masquage des champs repliés vides dans `to_cards`

**Files:**
- Modify: `pyminidash/web/render.py`
- Test: `tests/test_render.py`

**Interfaces:**
- Consumes: rien.
- Produces : `to_cards` inchangé côté signature ; comportement : un `Field` **non-résumé, non-titre, non-badge** dont `format_value(f) == ""` **et** `f.url is None` **et** `f.type is not FieldType.STATUS` n'apparaît plus dans `CardView.hidden_fields`. `to_table` inchangé.

- [ ] **Step 1 : Écrire le test**

Dans `tests/test_render.py`, ajouter :

```python
from pyminidash.web.render import to_cards  # déjà importé en haut du fichier


def test_to_cards_drops_empty_hidden_fields():
    from pyminidash.models import Record, text, title
    recs = [Record(
        title("name", "Nom", "p1"),
        text("v", "Version", "1.0", summary=True),
        text("empty", "Vide", ""),
        text("full", "Plein", "xxx"),
    )]
    card = to_cards(recs)[0]
    assert [f.key for f in card.hidden_fields] == ["full"]


def test_to_cards_keeps_empty_summary_fields():
    from pyminidash.models import Record, text, title
    recs = [Record(
        title("name", "Nom", "p1"),
        text("v", "Version", "", summary=True),
    )]
    card = to_cards(recs)[0]
    assert [f.key for f in card.summary_fields] == ["v"]
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_render.py::test_to_cards_drops_empty_hidden_fields -q`
Expected : FAIL (`['empty', 'full'] == ['full']`).

- [ ] **Step 3 : Implémenter**

Dans `pyminidash/web/render.py` : ajouter `FieldType` à l'import depuis `pyminidash.models`, puis dans la boucle de `to_cards`, remplacer la branche finale :

```python
            elif f.summary:
                summary.append(f)
            elif (
                format_value(f) == ""
                and f.url is None
                and f.type is not FieldType.STATUS
            ):
                continue
            else:
                hidden.append(f)
```

- [ ] **Step 4 : Lancer, vérifier le succès**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_render.py -q`
Expected : PASS.

- [ ] **Step 5 : Commit**

```bash
git add pyminidash/web/render.py tests/test_render.py
git commit -m "$(printf 'Masque les champs replies vides dans les cards\n\nto_cards ne place plus dans hidden_fields un champ texte vide sans url ni\nstatut. to_table inchange.\n\nCo-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>')"
```

---

## Task 3 : `discovery.py` — scan et découverte des projets

**Files:**
- Create: `pyminidash/providers/localproj/__init__.py` (vide pour l'instant : `"""Provider d'inspection de projets locaux."""` — le vrai contenu vient en Task 8)
- Create: `pyminidash/providers/localproj/discovery.py`
- Test: `tests/test_providers_localproj_discovery.py`

**Interfaces:**
- Consumes: `pyminidash.errors.ProviderError`.
- Produces :
  - `ALWAYS_IGNORE: frozenset[str]` = `{"target","node_modules","node",".venv",".venv2",".env",".git","dist","build",".idea",".gradle"}`.
  - `@dataclass(frozen=True) class ProjectDir: path: Path ; name: str ; types: tuple[str, ...]` — `types` est un sous-ensemble ordonné de `("maven","cargo","go","npm","python")`.
  - `find_projects(roots: list[str], ignore: list[str], max_depth: int) -> list[ProjectDir]` — trié par `(name.lower(), str(path))`, dédupliqué sur `path` résolu ; lève `ProviderError` si un `root` n'est pas un répertoire.
  - `markers(d: Path) -> tuple[str, ...]` (helper réutilisé par `maven.py`).

- [ ] **Step 1 : Écrire les tests**

`tests/test_providers_localproj_discovery.py` :

```python
from pathlib import Path

import pytest

from pyminidash.errors import ProviderError
from pyminidash.providers.localproj.discovery import find_projects, markers


def _touch(p: Path):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x", encoding="utf-8")


def test_markers_priority_order(tmp_path):
    _touch(tmp_path / "pom.xml")
    _touch(tmp_path / "package.json")
    assert markers(tmp_path) == ("maven", "npm")


def test_markers_python_via_venv_dir(tmp_path):
    (tmp_path / ".venv2").mkdir()
    assert markers(tmp_path) == ("python",)


def test_finds_nested_project_and_stops_descending(tmp_path):
    _touch(tmp_path / "a" / "pom.xml")
    _touch(tmp_path / "a" / "sub" / "pom.xml")     # ne doit PAS produire un 2e record
    found = find_projects([str(tmp_path)], [], max_depth=5)
    assert [p.path for p in found] == [tmp_path / "a"]


def test_hardcoded_ignores_are_skipped(tmp_path):
    _touch(tmp_path / "node_modules" / "pkg" / "package.json")
    _touch(tmp_path / "real" / "package.json")
    found = find_projects([str(tmp_path)], [], max_depth=5)
    assert [p.name for p in found] == ["real"]


def test_ignore_glob_on_dir_name(tmp_path):
    _touch(tmp_path / "archive-2019" / "pom.xml")
    _touch(tmp_path / "keep" / "pom.xml")
    found = find_projects([str(tmp_path)], ["archive-*"], max_depth=5)
    assert [p.name for p in found] == ["keep"]


def test_max_depth_cutoff(tmp_path):
    _touch(tmp_path / "x" / "y" / "z" / "pom.xml")
    assert find_projects([str(tmp_path)], [], max_depth=2) == []
    assert len(find_projects([str(tmp_path)], [], max_depth=3)) == 1


def test_overlapping_roots_dedup(tmp_path):
    _touch(tmp_path / "proj" / "go.mod")
    found = find_projects([str(tmp_path), str(tmp_path / "proj")], [], max_depth=5)
    assert len(found) == 1


def test_missing_root_raises_providererror(tmp_path):
    with pytest.raises(ProviderError, match="introuvable"):
        find_projects([str(tmp_path / "nope")], [], max_depth=3)


def test_results_sorted_by_name(tmp_path):
    _touch(tmp_path / "zeta" / "go.mod")
    _touch(tmp_path / "alpha" / "go.mod")
    found = find_projects([str(tmp_path)], [], max_depth=5)
    assert [p.name for p in found] == ["alpha", "zeta"]
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_providers_localproj_discovery.py -q`
Expected : FAIL (`ModuleNotFoundError: pyminidash.providers.localproj.discovery`).

- [ ] **Step 3 : Créer le package**

`pyminidash/providers/localproj/__init__.py` :

```python
"""Provider d'inspection de projets locaux (découverte + Git + parsers)."""
from __future__ import annotations
```

- [ ] **Step 4 : Implémenter `discovery.py`**

```python
"""Découverte des projets sous une liste de répertoires racine."""
from __future__ import annotations

import os
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path

from pyminidash.errors import ProviderError

ALWAYS_IGNORE: frozenset[str] = frozenset({
    "target", "node_modules", "node", ".venv", ".venv2", ".env", ".git",
    "dist", "build", ".idea", ".gradle",
})

_PY_VENV_DIRS = (".venv", ".venv2", ".env")


@dataclass(frozen=True)
class ProjectDir:
    path: Path
    name: str
    types: tuple[str, ...]


def markers(d: Path) -> tuple[str, ...]:
    """Tokens de type présents dans `d`, en ordre de priorité."""
    found: list[str] = []
    if (d / "pom.xml").is_file():
        found.append("maven")
    if (d / "Cargo.toml").is_file():
        found.append("cargo")
    if (d / "go.mod").is_file():
        found.append("go")
    if (d / "package.json").is_file():
        found.append("npm")
    if (
        (d / "pyproject.toml").is_file()
        or (d / "setup.py").is_file()
        or any((d / v).is_dir() for v in _PY_VENV_DIRS)
    ):
        found.append("python")
    return tuple(found)


def _walk(root: Path, ignore: list[str], max_depth: int,
          out: dict[Path, ProjectDir]) -> None:
    def rec(d: Path, depth: int) -> None:
        types = markers(d)
        if types:
            resolved = d.resolve()
            out.setdefault(resolved, ProjectDir(resolved, d.name, types))
            return
        if depth >= max_depth:
            return
        try:
            entries = sorted(os.scandir(d), key=lambda e: e.name)
        except OSError:
            return
        for entry in entries:
            try:
                is_dir = entry.is_dir(follow_symlinks=False)
            except OSError:
                continue
            if not is_dir or entry.name in ALWAYS_IGNORE:
                continue
            if any(fnmatch(entry.name, pat) for pat in ignore):
                continue
            rec(Path(entry.path), depth + 1)

    rec(root, 0)


def find_projects(roots: list[str], ignore: list[str],
                  max_depth: int) -> list[ProjectDir]:
    missing = [r for r in roots if not Path(r).is_dir()]
    if missing:
        raise ProviderError(f"racine(s) introuvable(s) : {', '.join(missing)}")
    out: dict[Path, ProjectDir] = {}
    for r in roots:
        _walk(Path(r), ignore, max_depth, out)
    return sorted(out.values(), key=lambda p: (p.name.lower(), str(p.path)))
```

- [ ] **Step 5 : Lancer, vérifier le succès**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_providers_localproj_discovery.py -q`
Expected : PASS (10 tests).

- [ ] **Step 6 : Commit**

```bash
git add pyminidash/providers/localproj/__init__.py pyminidash/providers/localproj/discovery.py tests/test_providers_localproj_discovery.py
git commit -m "$(printf 'Ajoute localproj.discovery : scan et decouverte des projets\n\nParcours DFS multi-racines, ignores en dur + globs sur nom de dossier,\narret au 1er marqueur, dedup sur chemin resolu, tri par nom.\n\nCo-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>')"
```

---

## Task 4 : `gitinfo.py` — état Git via subprocess

**Files:**
- Create: `pyminidash/providers/localproj/gitinfo.py`
- Test: `tests/test_providers_localproj_gitinfo.py`

**Interfaces:**
- Consumes: rien.
- Produces :
  - `git_on_path() -> bool` (`shutil.which("git") is not None`).
  - `@dataclass(frozen=True) class GitInfo:` avec les champs :
    `branch: str`, `dirty_count: int`, `ahead: int | None`, `behind: int | None`,
    `upstream: str | None`, `commit_hash_short: str | None`, `commit_date: datetime | None`
    (tz-aware), `commit_subject: str | None`, `branches: tuple[str, ...]`,
    `remotes: tuple[str, ...]`.
  - `git_info(path: Path) -> GitInfo | None` — `None` si `path` n'est pas dans un dépôt Git ou si `git` échoue ; ne lève jamais.

- [ ] **Step 1 : Écrire les tests**

`tests/test_providers_localproj_gitinfo.py` :

```python
import shutil
import subprocess
from datetime import datetime

import pytest

from pyminidash.providers.localproj.gitinfo import GitInfo, git_info, git_on_path

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None, reason="git absent du PATH"
)


def _git(repo, *args):
    subprocess.run(("git", *args), cwd=repo, check=True,
                   capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "r"
    r.mkdir()
    _git(r, "init", "-b", "main")
    _git(r, "config", "user.email", "t@t.tt")
    _git(r, "config", "user.name", "T")
    (r / "f.txt").write_text("a", encoding="utf-8")
    _git(r, "add", ".")
    _git(r, "commit", "-m", "premier commit")
    return r


def test_git_on_path_true():
    assert git_on_path() is True


def test_clean_repo(repo):
    info = git_info(repo)
    assert isinstance(info, GitInfo)
    assert info.branch == "main"
    assert info.dirty_count == 0
    assert info.commit_subject == "premier commit"
    assert isinstance(info.commit_date, datetime)
    assert info.commit_date.tzinfo is not None
    assert "main" in info.branches


def test_dirty_count_includes_untracked(repo):
    (repo / "f.txt").write_text("modifié", encoding="utf-8")
    (repo / "nouveau.txt").write_text("x", encoding="utf-8")
    assert git_info(repo).dirty_count == 2


def test_branches_and_remotes(repo):
    _git(repo, "branch", "feature/x")
    _git(repo, "remote", "add", "origin", "git@example.com:me/r.git")
    info = git_info(repo)
    assert set(info.branches) == {"main", "feature/x"}
    assert info.remotes == ("origin git@example.com:me/r.git",)


def test_ahead_behind_vs_upstream(repo, tmp_path):
    bare = tmp_path / "bare.git"
    _git(repo, "clone", "--bare", str(repo), str(bare))
    _git(repo, "remote", "add", "origin", str(bare))
    _git(repo, "push", "-u", "origin", "main")
    (repo / "g.txt").write_text("x", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "local en avance")
    info = git_info(repo)
    assert info.upstream == "origin/main"
    assert info.ahead == 1
    assert info.behind == 0


def test_not_a_repo_returns_none(tmp_path):
    assert git_info(tmp_path) is None
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_providers_localproj_gitinfo.py -q`
Expected : FAIL (`ModuleNotFoundError`).

- [ ] **Step 3 : Implémenter `gitinfo.py`**

```python
"""État Git d'un répertoire, obtenu en invoquant le binaire `git`."""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

_TIMEOUT = 5


def git_on_path() -> bool:
    return shutil.which("git") is not None


@dataclass(frozen=True)
class GitInfo:
    branch: str
    dirty_count: int
    ahead: int | None
    behind: int | None
    upstream: str | None
    commit_hash_short: str | None
    commit_date: datetime | None
    commit_subject: str | None
    branches: tuple[str, ...]
    remotes: tuple[str, ...]


def _run(path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ("git", *args), cwd=path, capture_output=True, text=True,
        check=False, timeout=_TIMEOUT,
    )


def _parse_status(out: str) -> tuple[str, int, int | None, int | None, str | None]:
    branch = ""
    ahead = behind = None
    upstream = None
    dirty = 0
    for line in out.splitlines():
        if line.startswith("# branch.head "):
            head = line[len("# branch.head "):].strip()
            branch = "(HEAD détachée)" if head == "(detached)" else head
        elif line.startswith("# branch.upstream "):
            upstream = line[len("# branch.upstream "):].strip()
        elif line.startswith("# branch.ab "):
            parts = line.split()  # ["#", "branch.ab", "+A", "-B"]
            if len(parts) >= 4:
                try:
                    ahead = int(parts[2])
                    behind = -int(parts[3])
                except ValueError:
                    ahead = behind = None
        elif line[:2] in ("1 ", "2 ", "u ", "? "):
            dirty += 1
    return branch, dirty, ahead, behind, upstream


def git_info(path: Path) -> GitInfo | None:
    try:
        st = _run(path, "status", "--porcelain=v2", "--branch")
    except (OSError, subprocess.SubprocessError):
        return None
    if st.returncode != 0:
        return None
    branch, dirty, ahead, behind, upstream = _parse_status(st.stdout)

    h = d = s = None
    try:
        lg = _run(path, "log", "-1", "--format=%h%n%cI%n%s")
        if lg.returncode == 0 and lg.stdout.strip():
            parts = lg.stdout.split("\n", 2)
            h = parts[0].strip() or None
            if len(parts) > 1:
                try:
                    d = datetime.fromisoformat(parts[1].strip())
                except ValueError:
                    d = None
            s = parts[2].strip() if len(parts) > 2 else None
    except (OSError, subprocess.SubprocessError):
        pass

    branches: tuple[str, ...] = ()
    remotes: tuple[str, ...] = ()
    try:
        br = _run(path, "for-each-ref", "--format=%(refname:short)", "refs/heads")
        if br.returncode == 0:
            branches = tuple(x.strip() for x in br.stdout.splitlines() if x.strip())
        rm = _run(path, "remote", "-v")
        if rm.returncode == 0:
            seen: dict[str, str] = {}
            for line in rm.stdout.splitlines():
                cols = line.split()
                if len(cols) >= 2:
                    seen.setdefault(cols[0], cols[1])
            remotes = tuple(f"{n} {u}" for n, u in seen.items())
    except (OSError, subprocess.SubprocessError):
        pass

    return GitInfo(
        branch=branch, dirty_count=dirty, ahead=ahead, behind=behind,
        upstream=upstream, commit_hash_short=h, commit_date=d,
        commit_subject=s, branches=branches, remotes=remotes,
    )
```

- [ ] **Step 4 : Lancer, vérifier le succès**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_providers_localproj_gitinfo.py -q`
Expected : PASS (7 tests ; skip global si `git` absent).

- [ ] **Step 5 : Commit**

```bash
git add pyminidash/providers/localproj/gitinfo.py tests/test_providers_localproj_gitinfo.py
git commit -m "$(printf 'Ajoute localproj.gitinfo : etat Git via subprocess\n\nbranche, ahead/behind vs upstream (sans reseau), fichiers modifies,\ndernier commit, branches locales, remotes. Renvoie None hors depot.\n\nCo-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>')"
```

---

## Task 5 : Parsers simples — `node`, `cargo`, `gomod`, `python`

**Files:**
- Create: `pyminidash/providers/localproj/node.py`
- Create: `pyminidash/providers/localproj/cargo.py`
- Create: `pyminidash/providers/localproj/gomod.py`
- Create: `pyminidash/providers/localproj/python.py`
- Test: `tests/test_providers_localproj_parsers.py`

**Interfaces:**
- Consumes: rien.
- Produces (toutes les dataclasses sont `@dataclass(frozen=True)`, tous les parsers prennent `dir: Path` et ne lèvent jamais) :
  - `node.NodeInfo: readable: bool ; name: str | None ; version: str | None ; angular_version: str | None ; angular_material_version: str | None` — `node.parse_node(dir) -> NodeInfo`.
  - `cargo.CargoInfo: readable: bool ; name: str | None ; version: str | None ; edition: str | None ; rust_version: str | None ; members: tuple[str, ...]` — `cargo.parse_cargo(dir) -> CargoInfo`.
  - `gomod.GoInfo: readable: bool ; module: str | None ; name: str | None ; go_version: str | None` — `gomod.parse_gomod(dir) -> GoInfo`.
  - `python.PythonInfo: readable: bool ; name: str | None ; version: str | None` — `python.parse_python(dir) -> PythonInfo`.

- [ ] **Step 1 : Écrire les tests**

`tests/test_providers_localproj_parsers.py` :

```python
from pathlib import Path

from pyminidash.providers.localproj.cargo import parse_cargo
from pyminidash.providers.localproj.gomod import parse_gomod
from pyminidash.providers.localproj.node import parse_node
from pyminidash.providers.localproj.python import parse_python


def _w(p: Path, text: str):
    p.write_text(text, encoding="utf-8")


def test_parse_node_nominal(tmp_path):
    _w(tmp_path / "package.json", """
      {"name": "front", "version": "2.1.0",
       "dependencies": {"@angular/core": "^17.0.3"},
       "devDependencies": {"@angular/material": "~17.0.1"}}
    """)
    info = parse_node(tmp_path)
    assert info.readable is True
    assert (info.name, info.version) == ("front", "2.1.0")
    assert info.angular_version == "17.0.3"
    assert info.angular_material_version == "17.0.1"


def test_parse_node_malformed(tmp_path):
    _w(tmp_path / "package.json", "{ not json")
    info = parse_node(tmp_path)
    assert info.readable is False
    assert info.name is None


def test_parse_cargo_package(tmp_path):
    _w(tmp_path / "Cargo.toml", """
      [package]
      name = "mycrate"
      version = "0.4.2"
      edition = "2021"
      rust-version = "1.74"
    """)
    info = parse_cargo(tmp_path)
    assert (info.name, info.version, info.edition, info.rust_version) == (
        "mycrate", "0.4.2", "2021", "1.74")


def test_parse_cargo_workspace(tmp_path):
    _w(tmp_path / "Cargo.toml", """
      [workspace]
      members = ["crates/a", "crates/b"]
    """)
    info = parse_cargo(tmp_path)
    assert info.name == tmp_path.name
    assert info.members == ("crates/a", "crates/b")


def test_parse_cargo_malformed(tmp_path):
    _w(tmp_path / "Cargo.toml", "[package\nname =")
    assert parse_cargo(tmp_path).readable is False


def test_parse_gomod(tmp_path):
    _w(tmp_path / "go.mod", "module github.com/me/thing\n\ngo 1.22\n")
    info = parse_gomod(tmp_path)
    assert info.module == "github.com/me/thing"
    assert info.name == "thing"
    assert info.go_version == "1.22"


def test_parse_python_pep621(tmp_path):
    _w(tmp_path / "pyproject.toml", '[project]\nname = "pkg"\nversion = "1.2.3"\n')
    info = parse_python(tmp_path)
    assert (info.name, info.version) == ("pkg", "1.2.3")


def test_parse_python_poetry(tmp_path):
    _w(tmp_path / "pyproject.toml",
       '[tool.poetry]\nname = "poetrypkg"\nversion = "9.9.9"\n')
    info = parse_python(tmp_path)
    assert (info.name, info.version) == ("poetrypkg", "9.9.9")


def test_parse_python_venv_only(tmp_path):
    (tmp_path / ".venv").mkdir()
    info = parse_python(tmp_path)
    assert info.name == tmp_path.name
    assert info.version is None
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_providers_localproj_parsers.py -q`
Expected : FAIL (`ModuleNotFoundError`).

- [ ] **Step 3 : Implémenter `node.py`**

```python
"""Lecture de package.json (nom, version, Angular)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

_PREFIXES = "^~>=< "


@dataclass(frozen=True)
class NodeInfo:
    readable: bool
    name: str | None
    version: str | None
    angular_version: str | None
    angular_material_version: str | None


def _clean(spec: object) -> str | None:
    if not isinstance(spec, str):
        return None
    return spec.lstrip(_PREFIXES).strip() or None


def _dep(data: dict, pkg: str) -> str | None:
    for section in ("dependencies", "devDependencies"):
        block = data.get(section)
        if isinstance(block, dict) and pkg in block:
            return _clean(block[pkg])
    return None


def parse_node(dir: Path) -> NodeInfo:
    try:
        data = json.loads((dir / "package.json").read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError
    except (OSError, ValueError):
        return NodeInfo(False, None, None, None, None)
    name = data.get("name") if isinstance(data.get("name"), str) else None
    version = data.get("version") if isinstance(data.get("version"), str) else None
    return NodeInfo(
        True, name, version,
        _dep(data, "@angular/core"), _dep(data, "@angular/material"),
    )
```

- [ ] **Step 4 : Implémenter `cargo.py`**

```python
"""Lecture de Cargo.toml (package ou workspace)."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CargoInfo:
    readable: bool
    name: str | None
    version: str | None
    edition: str | None
    rust_version: str | None
    members: tuple[str, ...]


def parse_cargo(dir: Path) -> CargoInfo:
    try:
        data = tomllib.loads((dir / "Cargo.toml").read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return CargoInfo(False, None, None, None, None, ())
    pkg = data.get("package", {})
    if isinstance(pkg, dict) and pkg:
        return CargoInfo(
            True, pkg.get("name"), pkg.get("version"),
            pkg.get("edition"), pkg.get("rust-version"), (),
        )
    ws = data.get("workspace", {})
    members = ws.get("members", []) if isinstance(ws, dict) else []
    members = tuple(m for m in members if isinstance(m, str))
    return CargoInfo(True, dir.name, None, None, None, members)
```

- [ ] **Step 5 : Implémenter `gomod.py`**

```python
"""Lecture de go.mod (chemin de module, version de Go)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GoInfo:
    readable: bool
    module: str | None
    name: str | None
    go_version: str | None


def parse_gomod(dir: Path) -> GoInfo:
    try:
        lines = (dir / "go.mod").read_text(encoding="utf-8").splitlines()
    except OSError:
        return GoInfo(False, None, None, None)
    module = go_version = None
    for raw in lines:
        line = raw.strip()
        if line.startswith("module ") and module is None:
            module = line[len("module "):].strip()
        elif line.startswith("go ") and go_version is None:
            go_version = line[len("go "):].strip()
    name = module.rsplit("/", 1)[-1] if module else None
    return GoInfo(True, module, name, go_version)
```

- [ ] **Step 6 : Implémenter `python.py`**

```python
"""Lecture de pyproject.toml / setup.py (nom, version) — best effort."""
from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

_SETUP_NAME = re.compile(r"""name\s*=\s*['"]([^'"]+)['"]""")
_SETUP_VERSION = re.compile(r"""version\s*=\s*['"]([^'"]+)['"]""")


@dataclass(frozen=True)
class PythonInfo:
    readable: bool
    name: str | None
    version: str | None


def parse_python(dir: Path) -> PythonInfo:
    pyproject = dir / "pyproject.toml"
    if pyproject.is_file():
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            return PythonInfo(False, None, None)
        proj = data.get("project", {})
        if isinstance(proj, dict) and (proj.get("name") or proj.get("version")):
            return PythonInfo(True, proj.get("name"), proj.get("version"))
        poetry = data.get("tool", {}).get("poetry", {}) if isinstance(
            data.get("tool"), dict) else {}
        if isinstance(poetry, dict) and (poetry.get("name") or poetry.get("version")):
            return PythonInfo(True, poetry.get("name"), poetry.get("version"))
        return PythonInfo(True, dir.name, None)

    setup = dir / "setup.py"
    if setup.is_file():
        try:
            src = setup.read_text(encoding="utf-8")
        except OSError:
            return PythonInfo(False, None, None)
        n = _SETUP_NAME.search(src)
        v = _SETUP_VERSION.search(src)
        return PythonInfo(True, n.group(1) if n else dir.name,
                          v.group(1) if v else None)

    return PythonInfo(True, dir.name, None)   # .venv seul
```

- [ ] **Step 7 : Lancer, vérifier le succès**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_providers_localproj_parsers.py -q`
Expected : PASS (10 tests).

- [ ] **Step 8 : Commit**

```bash
git add pyminidash/providers/localproj/node.py pyminidash/providers/localproj/cargo.py pyminidash/providers/localproj/gomod.py pyminidash/providers/localproj/python.py tests/test_providers_localproj_parsers.py
git commit -m "$(printf 'Ajoute les parsers localproj node/cargo/gomod/python\n\nLecture best-effort de package.json, Cargo.toml, go.mod, pyproject.toml /\nsetup.py. Aucun ne leve : fichier illisible => readable=False.\n\nCo-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>')"
```

---

## Task 6 : `maven.py` — parsing du pom

**Files:**
- Create: `pyminidash/providers/localproj/maven.py`
- Create: `tests/fixtures/localproj/` (poms d'exemple, créés dans les tests via `tmp_path` — pas de fichier fixture permanent nécessaire)
- Test: `tests/test_providers_localproj_maven.py`

**Interfaces:**
- Consumes:
  - `pyminidash.providers.localproj.discovery.ALWAYS_IGNORE`
  - `pyminidash.providers.localproj.node.parse_node` (sous-scan Angular)
- Produces :
  - `@dataclass(frozen=True) class MavenInfo:` avec :
    `readable: bool`, `name: str | None`, `group_id: str | None`, `artifact_id: str | None`,
    `version: str | None`, `parent_gav: str | None`, `java_version: str | None`,
    `spring_boot_version: str | None`, `modules: tuple[str, ...]`,
    `libs: tuple[tuple[str, str], ...]` (paires `(artifactId, version)`),
    `frontend_plugin_version: str | None`, `frontend_node_version: str | None`,
    `frontend_npm_version: str | None`, `angular_version: str | None`,
    `angular_material_version: str | None`.
  - `parse_maven(project_dir: Path, libs: list[str]) -> MavenInfo` — ne lève jamais ; `pom.xml` illisible → `MavenInfo(readable=False, ...)` (tous les autres champs `None`/`()`).

- [ ] **Step 1 : Écrire les tests**

`tests/test_providers_localproj_maven.py` :

```python
from pathlib import Path

from pyminidash.providers.localproj.maven import parse_maven

NS = 'xmlns="http://maven.apache.org/POM/4.0.0"'


def _pom(dir: Path, body: str, name: str = "pom.xml"):
    (dir / name).write_text(
        f'<?xml version="1.0"?>\n<project {NS}>\n{body}\n</project>',
        encoding="utf-8")


def test_gav_and_name(tmp_path):
    _pom(tmp_path, """
      <groupId>com.example</groupId>
      <artifactId>app</artifactId>
      <version>1.4.0</version>
      <name>Mon Appli</name>
    """)
    info = parse_maven(tmp_path, [])
    assert info.readable is True
    assert (info.group_id, info.artifact_id, info.version) == (
        "com.example", "app", "1.4.0")
    assert info.name == "Mon Appli"


def test_group_and_version_inherited_from_parent(tmp_path):
    _pom(tmp_path, """
      <parent>
        <groupId>com.example</groupId>
        <artifactId>parent</artifactId>
        <version>3.2.1</version>
      </parent>
      <artifactId>child</artifactId>
    """)
    info = parse_maven(tmp_path, [])
    assert info.group_id == "com.example"
    assert info.version == "3.2.1"
    assert info.parent_gav == "com.example:parent:3.2.1"


def test_property_interpolation(tmp_path):
    _pom(tmp_path, """
      <artifactId>a</artifactId>
      <version>1.0</version>
      <properties><java.version>17</java.version></properties>
      <dependencies>
        <dependency>
          <groupId>com.google.guava</groupId>
          <artifactId>guava</artifactId>
          <version>${guava.version}</version>
        </dependency>
      </dependencies>
    """)
    # ${guava.version} non défini -> laissé littéral
    info = parse_maven(tmp_path, ["guava"])
    assert info.java_version == "17"
    assert info.libs == (("guava", "${guava.version}"),)


def test_parent_on_disk_properties_merge(tmp_path):
    parent = tmp_path / "parent"
    child = tmp_path / "parent" / "svc"
    child.mkdir(parents=True)
    _pom(parent, """
      <groupId>g</groupId><artifactId>p</artifactId><version>1</version>
      <properties><spring.version>6.1.2</spring.version></properties>
    """)
    _pom(child, """
      <parent>
        <groupId>g</groupId><artifactId>p</artifactId><version>1</version>
        <relativePath>../pom.xml</relativePath>
      </parent>
      <artifactId>svc</artifactId>
      <dependencies>
        <dependency>
          <groupId>org.springframework</groupId>
          <artifactId>spring-core</artifactId>
          <version>${spring.version}</version>
        </dependency>
      </dependencies>
    """)
    info = parse_maven(child, ["spring-core"])
    assert info.libs == (("spring-core", "6.1.2"),)


def test_java_version_from_compiler_plugin(tmp_path):
    _pom(tmp_path, """
      <artifactId>a</artifactId><version>1</version>
      <build><plugins><plugin>
        <artifactId>maven-compiler-plugin</artifactId>
        <configuration><release>21</release></configuration>
      </plugin></plugins></build>
    """)
    assert parse_maven(tmp_path, []).java_version == "21"


def test_spring_boot_from_starter_parent(tmp_path):
    _pom(tmp_path, """
      <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.2.1</version>
      </parent>
      <artifactId>a</artifactId>
    """)
    assert parse_maven(tmp_path, []).spring_boot_version == "3.2.1"


def test_spring_boot_from_dependency_management(tmp_path):
    _pom(tmp_path, """
      <artifactId>a</artifactId><version>1</version>
      <dependencyManagement><dependencies><dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-dependencies</artifactId>
        <version>3.1.5</version>
      </dependency></dependencies></dependencyManagement>
    """)
    assert parse_maven(tmp_path, []).spring_boot_version == "3.1.5"


def test_modules_list(tmp_path):
    _pom(tmp_path, """
      <artifactId>a</artifactId><version>1</version>
      <modules><module>core</module><module>web</module></modules>
    """)
    assert parse_maven(tmp_path, []).modules == ("core", "web")


def test_libs_present_and_absent(tmp_path):
    _pom(tmp_path, """
      <artifactId>a</artifactId><version>1</version>
      <dependencies><dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId><version>3.14.0</version>
      </dependency></dependencies>
    """)
    info = parse_maven(tmp_path, ["commons-lang3", "guava"])
    assert info.libs == (("commons-lang3", "3.14.0"),)


def test_frontend_maven_plugin(tmp_path):
    _pom(tmp_path, """
      <artifactId>a</artifactId><version>1</version>
      <build><plugins><plugin>
        <groupId>com.github.eirslett</groupId>
        <artifactId>frontend-maven-plugin</artifactId>
        <version>1.15.0</version>
        <configuration>
          <nodeVersion>v20.11.0</nodeVersion>
          <npmVersion>10.2.4</npmVersion>
        </configuration>
      </plugin></plugins></build>
    """)
    info = parse_maven(tmp_path, [])
    assert info.frontend_plugin_version == "1.15.0"
    assert info.frontend_node_version == "v20.11.0"
    assert info.frontend_npm_version == "10.2.4"


def test_angular_subscan(tmp_path):
    _pom(tmp_path, "<artifactId>a</artifactId><version>1</version>")
    front = tmp_path / "src" / "main" / "webapp"
    front.mkdir(parents=True)
    (front / "package.json").write_text(
        '{"dependencies": {"@angular/core": "17.1.0"}}', encoding="utf-8")
    assert parse_maven(tmp_path, []).angular_version == "17.1.0"


def test_malformed_pom(tmp_path):
    (tmp_path / "pom.xml").write_text("<project><broken", encoding="utf-8")
    info = parse_maven(tmp_path, [])
    assert info.readable is False
    assert info.artifact_id is None
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_providers_localproj_maven.py -q`
Expected : FAIL (`ModuleNotFoundError`).

- [ ] **Step 3 : Implémenter `maven.py`**

```python
"""Analyse statique d'un pom.xml : coordonnées, Java, Spring Boot, modules,
libs demandées, frontend-maven-plugin, et sous-scan Angular."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from pyminidash.providers.localproj.discovery import ALWAYS_IGNORE
from pyminidash.providers.localproj.node import parse_node

_PROP_RE = re.compile(r"\$\{([^}]+)\}")
_SUBSCAN_DEPTH = 3


@dataclass(frozen=True)
class MavenInfo:
    readable: bool
    name: str | None
    group_id: str | None
    artifact_id: str | None
    version: str | None
    parent_gav: str | None
    java_version: str | None
    spring_boot_version: str | None
    modules: tuple[str, ...]
    libs: tuple[tuple[str, str], ...]
    frontend_plugin_version: str | None
    frontend_node_version: str | None
    frontend_npm_version: str | None
    angular_version: str | None
    angular_material_version: str | None


_UNREADABLE = MavenInfo(False, None, None, None, None, None, None, None,
                        (), (), None, None, None, None, None)


def _txt(el: ET.Element | None, tag: str) -> str | None:
    if el is None:
        return None
    child = el.find(f"{{*}}{tag}")
    return child.text.strip() if child is not None and child.text else None


def _load_properties(pom_path: Path, root: ET.Element, depth: int = 3) -> dict[str, str]:
    """Propriétés du pom + celles des parents sur disque (enfant prioritaire)."""
    props: dict[str, str] = {}
    parent_el = root.find("{*}parent")
    if depth > 0 and parent_el is not None:
        rel = _txt(parent_el, "relativePath") or "../pom.xml"
        parent_path = (pom_path.parent / rel).resolve()
        if parent_path.is_file():
            try:
                proot = ET.parse(parent_path).getroot()
                props.update(_load_properties(parent_path, proot, depth - 1))
            except ET.ParseError:
                pass
    local = root.find("{*}properties")
    if local is not None:
        for child in local:
            tag = child.tag.split("}")[-1]
            if child.text:
                props[tag] = child.text.strip()
    return props


def _interpolate(value: str | None, props: dict[str, str]) -> str | None:
    if value is None:
        return None
    for _ in range(2):  # propriétés imbriquées
        if "${" not in value:
            break
        value = _PROP_RE.sub(lambda m: props.get(m.group(1), m.group(0)), value)
    return value


def _all_deps(root: ET.Element) -> list[ET.Element]:
    return root.findall(".//{*}dependencies/{*}dependency")


def _plugins(root: ET.Element) -> list[ET.Element]:
    return root.findall(".//{*}plugin")


def _java_version(root: ET.Element, props: dict[str, str]) -> str | None:
    for key in ("maven.compiler.release", "maven.compiler.source", "java.version"):
        if key in props:
            return props[key]
    for plugin in _plugins(root):
        if _txt(plugin, "artifactId") == "maven-compiler-plugin":
            cfg = plugin.find("{*}configuration")
            return _txt(cfg, "release") or _txt(cfg, "source")
    return None


def _spring_boot(root: ET.Element, parent_el: ET.Element | None) -> str | None:
    if parent_el is not None and _txt(parent_el, "artifactId") == "spring-boot-starter-parent":
        return _txt(parent_el, "version")
    for dep in _all_deps(root):
        if _txt(dep, "artifactId") == "spring-boot-dependencies":
            return _txt(dep, "version")
    for plugin in _plugins(root):
        if _txt(plugin, "artifactId") == "spring-boot-maven-plugin":
            return _txt(plugin, "version")
    return None


def _frontend(root: ET.Element) -> tuple[str | None, str | None, str | None]:
    for plugin in _plugins(root):
        if _txt(plugin, "artifactId") != "frontend-maven-plugin":
            continue
        version = _txt(plugin, "version")
        node = npm = None
        for cfg in plugin.iter("{http://maven.apache.org/POM/4.0.0}configuration"):
            node = node or _txt(cfg, "nodeVersion")
            npm = npm or _txt(cfg, "npmVersion")
        if node is None or npm is None:      # config sans namespace
            for cfg in plugin.iter():
                if cfg.tag.split("}")[-1] == "configuration":
                    node = node or _txt(cfg, "nodeVersion")
                    npm = npm or _txt(cfg, "npmVersion")
        return version, node, npm
    return None, None, None


def _angular_subscan(project_dir: Path) -> tuple[str | None, str | None]:
    def rec(d: Path, depth: int) -> tuple[str | None, str | None] | None:
        pkg = d / "package.json"
        if pkg.is_file():
            info = parse_node(d)
            if info.angular_version or info.angular_material_version:
                return info.angular_version, info.angular_material_version
        if depth <= 0:
            return None
        try:
            for entry in d.iterdir():
                if entry.is_dir() and entry.name not in ALWAYS_IGNORE:
                    hit = rec(entry, depth - 1)
                    if hit:
                        return hit
        except OSError:
            return None
        return None

    return rec(project_dir, _SUBSCAN_DEPTH) or (None, None)


def parse_maven(project_dir: Path, libs: list[str]) -> MavenInfo:
    pom = project_dir / "pom.xml"
    try:
        root = ET.parse(pom).getroot()
    except (OSError, ET.ParseError):
        return _UNREADABLE

    parent_el = root.find("{*}parent")
    props = _load_properties(pom, root)
    props.setdefault("project.version",
                     _txt(root, "version") or _txt(parent_el, "version") or "")
    props.setdefault("project.groupId",
                     _txt(root, "groupId") or _txt(parent_el, "groupId") or "")

    group_id = _txt(root, "groupId") or _txt(parent_el, "groupId")
    version = _txt(root, "version") or _txt(parent_el, "version")
    parent_gav = None
    if parent_el is not None:
        parent_gav = ":".join(x or "?" for x in (
            _txt(parent_el, "groupId"), _txt(parent_el, "artifactId"),
            _txt(parent_el, "version")))

    found_libs: list[tuple[str, str]] = []
    for dep in _all_deps(root):
        aid = _txt(dep, "artifactId")
        if aid in libs:
            raw = _txt(dep, "version")
            found_libs.append((aid, _interpolate(raw, props) or "managed"))

    fe_version, fe_node, fe_npm = _frontend(root)
    ang, ang_mat = _angular_subscan(project_dir)

    return MavenInfo(
        readable=True,
        name=_txt(root, "name"),
        group_id=group_id,
        artifact_id=_txt(root, "artifactId"),
        version=_interpolate(version, props),
        parent_gav=parent_gav,
        java_version=_interpolate(_java_version(root, props), props),
        spring_boot_version=_interpolate(_spring_boot(root, parent_el), props),
        modules=tuple(
            m.text.strip() for m in root.findall("{*}modules/{*}module")
            if m.text and m.text.strip()
        ),
        libs=tuple(found_libs),
        frontend_plugin_version=fe_version,
        frontend_node_version=fe_node,
        frontend_npm_version=fe_npm,
        angular_version=ang,
        angular_material_version=ang_mat,
    )
```

- [ ] **Step 4 : Lancer, vérifier le succès**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_providers_localproj_maven.py -q`
Expected : PASS (13 tests). Si `test_frontend_maven_plugin` échoue sur le namespace, ajuster `_frontend` pour n'utiliser que la 2e boucle (`cfg.tag.split("}")[-1] == "configuration"`) — la version sans namespace couvre les deux cas.

- [ ] **Step 5 : Commit**

```bash
git add pyminidash/providers/localproj/maven.py tests/test_providers_localproj_maven.py
git commit -m "$(printf 'Ajoute localproj.maven : analyse statique du pom\n\nCoordonnees + heritage parent, interpolation ${} avec parents sur disque,\nversion Java, Spring Boot, <modules>, libs demandees, frontend-maven-plugin,\nsous-scan Angular. pom illisible => readable=False.\n\nCo-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>')"
```

---

## Task 7 : `record.py` — assemblage des 16 champs + `show`

**Files:**
- Create: `pyminidash/providers/localproj/record.py`
- Test: `tests/test_providers_localproj_record.py`

**Interfaces:**
- Consumes:
  - `discovery.ProjectDir`, `gitinfo.GitInfo`
  - `maven.MavenInfo`, `node.NodeInfo`, `cargo.CargoInfo`, `gomod.GoInfo`, `python.PythonInfo`
  - `pyminidash.models` : `Record`, `Field`, `FieldRole`, `StatusLevel`, helpers `text`, `title`, `status`
- Produces :
  - `KNOWN_FIELDS: tuple[str, ...]` — les 16 clés dans l'ordre :
    `("name","type","version","branch","dirty","last_commit","path","commit_detail","sync","branches","remotes","stack","maven_coords","modules","libs","frontend_build")`
  - `@dataclass(frozen=True) class ParsedProject: maven: MavenInfo | None ; node: NodeInfo | None ; cargo: CargoInfo | None ; go: GoInfo | None ; python: PythonInfo | None`
  - `relative_date(dt: datetime, now: datetime) -> str`
  - `to_record(project: ProjectDir, parsed: ParsedProject, git: GitInfo | None, show: list[str] | None) -> Record`

- [ ] **Step 1 : Écrire les tests**

`tests/test_providers_localproj_record.py` :

```python
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pyminidash.models import FieldRole
from pyminidash.providers.localproj.discovery import ProjectDir
from pyminidash.providers.localproj.gitinfo import GitInfo
from pyminidash.providers.localproj.maven import MavenInfo
from pyminidash.providers.localproj.node import NodeInfo
from pyminidash.providers.localproj.record import (
    KNOWN_FIELDS, ParsedProject, relative_date, to_record,
)

_EMPTY = ParsedProject(None, None, None, None, None)


def _proj(types=("maven",)):
    return ProjectDir(Path("/x/app"), "app", types)


def _maven(**kw):
    base = dict(readable=True, name="Mon Appli", group_id="com.ex",
                artifact_id="app", version="1.4.0", parent_gav=None,
                java_version="17", spring_boot_version="3.2.1", modules=("core",),
                libs=(("guava", "33.0.0"),), frontend_plugin_version=None,
                frontend_node_version=None, frontend_npm_version=None,
                angular_version=None, angular_material_version=None)
    base.update(kw)
    return MavenInfo(**base)


def _git(**kw):
    base = dict(branch="main", dirty_count=0, ahead=2, behind=0,
                upstream="origin/main", commit_hash_short="a1b2c3d",
                commit_date=datetime(2026, 8, 28, 14, 3, tzinfo=timezone.utc),
                commit_subject="Fix null check", branches=("main", "dev"),
                remotes=("origin git@x:me/app.git",))
    base.update(kw)
    return GitInfo(**base)


def test_full_schema_keys_and_order():
    rec = to_record(_proj(), ParsedProject(_maven(), None, None, None, None),
                    _git(), None)
    assert rec.keys() == KNOWN_FIELDS


def test_homogeneous_across_types():
    a = to_record(_proj(("maven",)), ParsedProject(_maven(), None, None, None, None),
                  _git(), None)
    b = to_record(ProjectDir(Path("/x/g"), "g", ("go",)), _EMPTY, None, None)
    assert a.keys() == b.keys()


def test_title_and_badge_roles():
    rec = to_record(_proj(("maven", "npm")),
                    ParsedProject(_maven(), None, None, None, None), _git(), None)
    by = {f.key: f for f in rec.fields}
    assert by["name"].role is FieldRole.TITLE
    assert by["name"].value == "Mon Appli"
    assert by["type"].role is FieldRole.BADGE
    assert by["type"].value == "maven + npm"


def test_composites():
    rec = to_record(_proj(), ParsedProject(_maven(), None, None, None, None),
                    _git(), None)
    by = {f.key: f for f in rec.fields}
    assert by["stack"].value == "Java 17 · Spring Boot 3.2.1"
    assert by["maven_coords"].value == "com.ex:app:1.4.0"
    assert by["modules"].value == "core"
    assert by["libs"].value == "guava 33.0.0"
    assert by["sync"].value == "↑2 ↓0 vs origin/main"
    assert by["commit_detail"].value.startswith("a1b2c3d · 2026-08-28 14:03")


def test_dirty_levels():
    from pyminidash.models import StatusLevel
    clean = {f.key: f for f in to_record(_proj(), _EMPTY, _git(dirty_count=0), None).fields}
    dirty = {f.key: f for f in to_record(_proj(), _EMPTY, _git(dirty_count=3), None).fields}
    none = {f.key: f for f in to_record(_proj(), _EMPTY, None, None).fields}
    assert clean["dirty"].value == "propre" and clean["dirty"].level is StatusLevel.OK
    assert dirty["dirty"].value == "3 modifiés" and dirty["dirty"].level is StatusLevel.WARN
    assert none["dirty"].value == "" and none["dirty"].level is StatusLevel.NEUTRAL


def test_show_filters_and_orders():
    rec = to_record(_proj(), ParsedProject(_maven(), None, None, None, None),
                    _git(), ["version", "stack"])
    assert rec.keys() == ("name", "version", "stack")   # name forcé en tête


def test_show_keeps_name_if_listed():
    rec = to_record(_proj(), _EMPTY, None, ["branch", "name"])
    assert rec.keys() == ("branch", "name")


def test_relative_date_buckets():
    now = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)
    assert relative_date(now - timedelta(seconds=30), now) == "à l'instant"
    assert relative_date(now - timedelta(minutes=5), now) == "il y a 5 min"
    assert relative_date(now - timedelta(hours=3), now) == "il y a 3 h"
    assert relative_date(now - timedelta(days=2), now) == "il y a 2 j"
    assert relative_date(now - timedelta(days=20), now) == "il y a 2 sem"
    assert relative_date(now - timedelta(days=90), now) == "il y a 3 mois"
    assert relative_date(now - timedelta(days=800), now) == "il y a 2 ans"
    assert relative_date(now + timedelta(days=1), now) == "à l'instant"  # skew
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_providers_localproj_record.py -q`
Expected : FAIL (`ModuleNotFoundError`).

- [ ] **Step 3 : Implémenter `record.py`**

```python
"""Assemblage d'un ProjectDir + parsers + Git en un Record de 16 champs."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone

from pyminidash.models import (
    FieldRole, Record, StatusLevel, status, text, title,
)
from pyminidash.providers.localproj.discovery import ProjectDir
from pyminidash.providers.localproj.gitinfo import GitInfo
from pyminidash.providers.localproj.maven import MavenInfo
from pyminidash.providers.localproj.node import NodeInfo
from pyminidash.providers.localproj.cargo import CargoInfo
from pyminidash.providers.localproj.gomod import GoInfo
from pyminidash.providers.localproj.python import PythonInfo

KNOWN_FIELDS: tuple[str, ...] = (
    "name", "type", "version", "branch", "dirty", "last_commit", "path",
    "commit_detail", "sync", "branches", "remotes", "stack", "maven_coords",
    "modules", "libs", "frontend_build",
)

_MAX_BRANCHES = 20


@dataclass(frozen=True)
class ParsedProject:
    maven: MavenInfo | None
    node: NodeInfo | None
    cargo: CargoInfo | None
    go: GoInfo | None
    python: PythonInfo | None


def relative_date(dt: datetime, now: datetime) -> str:
    secs = (now - dt).total_seconds()
    if secs < 60:
        return "à l'instant"
    mins = secs / 60
    if mins < 60:
        return f"il y a {int(mins)} min"
    hours = mins / 60
    if hours < 24:
        return f"il y a {int(hours)} h"
    days = hours / 24
    if days < 7:
        return f"il y a {int(days)} j"
    if days < 35:
        return f"il y a {int(days / 7)} sem"
    if days < 365:
        return f"il y a {int(days / 30)} mois"
    years = int(days / 365)
    return f"il y a {years} an" + ("s" if years > 1 else "")


def _name(project: ProjectDir, p: ParsedProject) -> str:
    if p.maven and p.maven.name:
        return p.maven.name
    if p.maven and p.maven.artifact_id:
        return p.maven.artifact_id
    for info in (p.node, p.cargo, p.go, p.python):
        if info and info.name:
            return info.name
    return project.name


def _version(p: ParsedProject) -> str:
    for info in (p.maven, p.cargo, p.node, p.python):
        if info and getattr(info, "version", None):
            return info.version
    return ""


def _stack(p: ParsedProject) -> str:
    bits: list[str] = []
    if p.maven and p.maven.java_version:
        bits.append(f"Java {p.maven.java_version}")
    if p.maven and p.maven.spring_boot_version:
        bits.append(f"Spring Boot {p.maven.spring_boot_version}")
    ang = (p.node.angular_version if p.node else None) or \
          (p.maven.angular_version if p.maven else None)
    ang_mat = (p.node.angular_material_version if p.node else None) or \
              (p.maven.angular_material_version if p.maven else None)
    if ang:
        bits.append(f"Angular {ang}")
    if ang_mat:
        bits.append(f"Angular Material {ang_mat}")
    if p.go and p.go.go_version:
        bits.append(f"Go {p.go.go_version}")
    if p.cargo and p.cargo.edition:
        bits.append(f"Rust edition {p.cargo.edition}")
    if p.cargo and p.cargo.rust_version:
        bits.append(f"Rust {p.cargo.rust_version}")
    return " · ".join(bits)


def _maven_coords(m: MavenInfo | None) -> str:
    if not m:
        return ""
    if not m.readable:
        return "pom illisible"
    gav = ":".join(x or "?" for x in (m.group_id, m.artifact_id, m.version))
    return gav + (f" — parent {m.parent_gav}" if m.parent_gav else "")


def _modules(p: ParsedProject) -> str:
    if p.maven and p.maven.modules:
        return ", ".join(p.maven.modules)
    if p.cargo and p.cargo.members:
        return ", ".join(p.cargo.members)
    return ""


def _libs(m: MavenInfo | None) -> str:
    if not m or not m.libs:
        return ""
    return ", ".join(f"{a} {v}" for a, v in m.libs)


def _frontend_build(m: MavenInfo | None) -> str:
    if not m or not m.frontend_plugin_version:
        return ""
    bits = [f"frontend-maven-plugin {m.frontend_plugin_version}"]
    if m.frontend_node_version:
        bits.append(f"node {m.frontend_node_version}")
    if m.frontend_npm_version:
        bits.append(f"npm {m.frontend_npm_version}")
    return " · ".join(bits)


def _dirty_field(git: GitInfo | None):
    if git is None:
        return status("dirty", "État", "", level=StatusLevel.NEUTRAL,
                      role=FieldRole.NORMAL, summary=True)
    if git.dirty_count == 0:
        return status("dirty", "État", "propre", level=StatusLevel.OK,
                      role=FieldRole.NORMAL, summary=True)
    n = git.dirty_count
    return status("dirty", "État", f"{n} modifié{'s' if n > 1 else ''}",
                  level=StatusLevel.WARN, role=FieldRole.NORMAL, summary=True)


def _git_fields(git: GitInfo | None) -> dict[str, str]:
    if git is None:
        return {k: "" for k in
                ("branch", "last_commit", "commit_detail", "sync", "branches", "remotes")}
    last_commit = commit_detail = ""
    if git.commit_date is not None:
        last_commit = relative_date(git.commit_date, datetime.now(timezone.utc))
        commit_detail = (f'{git.commit_hash_short} · '
                         f'{git.commit_date:%Y-%m-%d %H:%M} · '
                         f'"{git.commit_subject or ""}"')
    sync = ""
    if git.upstream and git.ahead is not None and git.behind is not None:
        sync = f"↑{git.ahead} ↓{git.behind} vs {git.upstream}"
    branches = list(git.branches[:_MAX_BRANCHES])
    extra = len(git.branches) - _MAX_BRANCHES
    branches_str = ", ".join(branches) + (f" +{extra}" if extra > 0 else "")
    return {
        "branch": git.branch,
        "last_commit": last_commit,
        "commit_detail": commit_detail,
        "sync": sync,
        "branches": branches_str,
        "remotes": " , ".join(git.remotes),
    }


def to_record(project: ProjectDir, parsed: ParsedProject,
              git: GitInfo | None, show: list[str] | None) -> Record:
    g = _git_fields(git)
    fields = [
        title("name", "Projet", _name(project, parsed)),
        text("type", "Type", " + ".join(project.types), role=FieldRole.BADGE),
        text("version", "Version", _version(parsed), summary=True),
        text("branch", "Branche", g["branch"], summary=True),
        _dirty_field(git),
        text("last_commit", "Dernier commit", g["last_commit"], summary=True),
        text("path", "Chemin", str(project.path)),
        text("commit_detail", "Commit", g["commit_detail"]),
        text("sync", "Sync", g["sync"]),
        text("branches", "Branches", g["branches"]),
        text("remotes", "Remotes", g["remotes"]),
        text("stack", "Stack", _stack(parsed)),
        text("maven_coords", "Coordonnées Maven", _maven_coords(parsed.maven)),
        text("modules", "Modules", _modules(parsed)),
        text("libs", "Libs", _libs(parsed.maven)),
        text("frontend_build", "Build frontend", _frontend_build(parsed.maven)),
    ]
    if show is None:
        return Record(*fields)

    wanted = list(show)
    if "name" not in wanted:
        wanted = ["name", *wanted]
    by_key = {f.key: f for f in fields}
    picked = []
    for key in wanted:
        f = by_key[key]
        if f.role in (FieldRole.TITLE, FieldRole.BADGE):
            picked.append(f)
        else:
            picked.append(replace(f, summary=True))
    return Record(*picked)
```

- [ ] **Step 4 : Lancer, vérifier le succès**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_providers_localproj_record.py -q`
Expected : PASS (9 tests).

- [ ] **Step 5 : Commit**

```bash
git add pyminidash/providers/localproj/record.py tests/test_providers_localproj_record.py
git commit -m "$(printf 'Ajoute localproj.record : assemblage des 16 champs + show\n\nConstructeur unique to_record (records homogenes garantis), composites\nstack/maven_coords/libs/frontend_build, dates relatives, filtrage show.\n\nCo-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>')"
```

---

## Task 8 : Orchestration `__init__.py` + enregistrement + docs

**Files:**
- Modify: `pyminidash/providers/localproj/__init__.py`
- Modify: `pyminidash/providers/__init__.py`
- Modify: `config.example.toml`
- Modify: `README.md`
- Modify: `docs/ETAT.md`
- Test: `tests/test_providers_localproj.py`, `tests/test_example_config.py` (vérifier qu'il passe toujours)

**Interfaces:**
- Consumes: tous les modules `localproj.*` des tâches 3-7.
- Produces :
  - `local_projects(roots: list[str], ignore: list[str] | None = None, max_depth: int = 5, libs: list[str] | None = None, show: list[str] | None = None) -> list[Record]` enregistré sous `@provider("local_projects", validate=_validate_cfg)`.
  - `_validate_cfg(params: dict) -> None` — lève `ValueError` si `show` n'est pas une `list[str]` ou contient une clé absente de `record.KNOWN_FIELDS`.

- [ ] **Step 1 : Écrire les tests d'intégration**

`tests/test_providers_localproj.py` :

```python
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

from pyminidash.config import ConfigError, load_config
from pyminidash.providers.localproj import local_projects
from pyminidash.providers.localproj.record import KNOWN_FIELDS


def _touch(p: Path, content: str = "x"):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


@pytest.fixture
def tree(tmp_path):
    _touch(tmp_path / "svc" / "pom.xml",
           '<project xmlns="http://maven.apache.org/POM/4.0.0">'
           '<groupId>g</groupId><artifactId>svc</artifactId>'
           '<version>1.0</version></project>')
    _touch(tmp_path / "front" / "package.json",
           '{"name": "front", "version": "2.0.0"}')
    _touch(tmp_path / "tool" / "go.mod", "module ex.com/tool\ngo 1.22\n")
    return tmp_path


def test_returns_homogeneous_records(tree):
    recs = local_projects([str(tree)])
    assert len(recs) == 3
    assert all(r.keys() == KNOWN_FIELDS for r in recs)


def test_sorted_by_name(tree):
    recs = local_projects([str(tree)])
    names = [next(f.value for f in r.fields if f.key == "name") for r in recs]
    assert names == sorted(names, key=str.lower)


def test_show_restricts_columns(tree):
    recs = local_projects([str(tree)], show=["version", "branch"])
    assert all(r.keys() == ("name", "version", "branch") for r in recs)


def test_missing_root_is_provider_error(tmp_path):
    from pyminidash.errors import ProviderError
    with pytest.raises(ProviderError):
        local_projects([str(tmp_path / "absent")])


@pytest.mark.skipif(shutil.which("git") is None, reason="git absent")
def test_git_fields_populated(tmp_path):
    r = tmp_path / "repo"
    _touch(r / "go.mod", "module ex.com/r\ngo 1.21\n")
    for args in (("init", "-b", "main"), ("config", "user.email", "a@a.aa"),
                 ("config", "user.name", "A"), ("add", "."),
                 ("commit", "-m", "init")):
        subprocess.run(("git", *args), cwd=r, check=True, capture_output=True)
    rec = local_projects([str(tmp_path)])[0]
    by = {f.key: f.value for f in rec.fields}
    assert by["branch"] == "main"
    assert by["dirty"] == "propre"


def _write_cfg(tmp_path, body):
    p = tmp_path / "config.toml"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


def test_config_rejects_unknown_show_key(tmp_path):
    p = _write_cfg(tmp_path, """
        [[groups]]
        id = "g"
        title = "G"
        type = "cards"
          [[groups.blocks]]
          provider = "local_projects"
          params = { roots = ["."], show = ["version", "bogus"] }
    """)
    with pytest.raises(ConfigError, match="bogus"):
        load_config(p)


def test_config_requires_roots(tmp_path):
    p = _write_cfg(tmp_path, """
        [[groups]]
        id = "g"
        title = "G"
        type = "cards"
          [[groups.blocks]]
          provider = "local_projects"
          params = { }
    """)
    with pytest.raises(ConfigError):
        load_config(p)
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_providers_localproj.py -q`
Expected : FAIL (`ImportError: cannot import name 'local_projects'`).

- [ ] **Step 3 : Implémenter `pyminidash/providers/localproj/__init__.py`**

```python
"""Provider `local_projects` : inspection de projets locaux (disque + Git)."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from pyminidash.models import Record
from pyminidash.registry import provider
from pyminidash.providers.localproj.discovery import ProjectDir, find_projects
from pyminidash.providers.localproj.gitinfo import git_info, git_on_path
from pyminidash.providers.localproj.maven import parse_maven
from pyminidash.providers.localproj.node import parse_node
from pyminidash.providers.localproj.cargo import parse_cargo
from pyminidash.providers.localproj.gomod import parse_gomod
from pyminidash.providers.localproj.python import parse_python
from pyminidash.providers.localproj.record import (
    KNOWN_FIELDS, ParsedProject, to_record,
)

_GIT_WORKERS = 8
_DEFAULT_LIBS = ("guava", "commons-lang3")


def _validate_cfg(params: dict) -> None:
    show = params.get("show")
    if show is None:
        return
    if not isinstance(show, list) or not all(isinstance(s, str) for s in show):
        raise ValueError("show doit être une liste de chaînes")
    unknown = [s for s in show if s not in KNOWN_FIELDS]
    if unknown:
        raise ValueError(
            f"show : champ(s) inconnu(s) {unknown} ; "
            f"connus : {', '.join(KNOWN_FIELDS)}"
        )


def _parse_all(project: ProjectDir, libs: list[str]) -> ParsedProject:
    t = project.types
    return ParsedProject(
        maven=parse_maven(project.path, libs) if "maven" in t else None,
        node=parse_node(project.path) if "npm" in t else None,
        cargo=parse_cargo(project.path) if "cargo" in t else None,
        go=parse_gomod(project.path) if "go" in t else None,
        python=parse_python(project.path) if "python" in t else None,
    )


@provider("local_projects", validate=_validate_cfg)
def local_projects(roots: list[str], ignore: list[str] | None = None,
                   max_depth: int = 5, libs: list[str] | None = None,
                   show: list[str] | None = None) -> list[Record]:
    ignore = list(ignore) if ignore else []
    libs = list(libs) if libs is not None else list(_DEFAULT_LIBS)

    projects = find_projects(roots, ignore, max_depth)   # ProviderError si root KO
    parsed = [_parse_all(p, libs) for p in projects]

    if git_on_path() and projects:
        with ThreadPoolExecutor(max_workers=_GIT_WORKERS) as pool:
            gits = list(pool.map(lambda p: git_info(p.path), projects))
    else:
        gits = [None] * len(projects)

    return [to_record(pr, pa, g, show)
            for pr, pa, g in zip(projects, parsed, gits)]
```

- [ ] **Step 4 : Enregistrer le provider**

Dans `pyminidash/providers/__init__.py`, ajouter `localproj` à la ligne d'import :

```python
"""Import des modules de providers intégrés → enregistrement au chargement."""
from pyminidash.providers import (  # noqa: F401
    bamboo, bitbucket, http, jira, localproj, system,
)
```

- [ ] **Step 5 : Lancer les tests d'intégration**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_providers_localproj.py -q`
Expected : PASS (8 tests).

- [ ] **Step 6 : Mettre à jour `config.example.toml`**

Ajouter un groupe avant la fin du fichier :

```toml
[[groups]]
id = "projets"
title = "Projets locaux"
type = "cards"

  [[groups.blocks]]
  title    = "Tous les projets"
  provider = "local_projects"
  timeout  = 60          # champ de bloc, PAS dans params : le défaut runner (10 s)
                         # est trop court pour un gros scan (~300 projets).
  params   = { roots = ["D:/projet"], ignore = ["archive-*"], libs = ["guava", "commons-lang3"] }

  [[groups.blocks]]
  title    = "Projets Rust (vue resserrée)"
  provider = "local_projects"
  timeout  = 60
  params   = { roots = ["D:/rust"], show = ["name", "version", "branch", "dirty", "stack"] }
```

- [ ] **Step 7 : Mettre à jour `README.md`**

Dans le tableau « Providers intégrés », ajouter la ligne :

```markdown
| `local_projects` | table / cards | `roots: list[str]`, `ignore: list[str] = []`, `max_depth: int = 5`, `libs: list[str] = ["guava","commons-lang3"]`, `show: list[str] = None` — poser `timeout = 60` au bloc |
```

- [ ] **Step 8 : Mettre à jour `docs/ETAT.md`**

- Ligne du tableau des providers : passer de 14 à 15 providers, ajouter `local_projects`.
- Section « Ce qui reste à faire » : retirer « Prochain gros morceau : provider inspection de projets locaux », le remplacer par une entrée « Fait (PR #4) » avec un lien vers la spec `docs/superpowers/specs/2026-08-30-pyminidash-local-projects-design.md`.
- Mettre à jour le compteur de tests et le hash de `main` en tête de fichier après le merge (à faire au moment du merge, pas ici).

- [ ] **Step 9 : Lancer toute la suite**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected : PASS — tous les tests existants + les nouveaux. `test_example_config.py` doit toujours valider `config.example.toml` (le nouveau groupe est syntaxiquement correct ; `roots` pointe un chemin qui n'est pas vérifié au démarrage).

- [ ] **Step 10 : Commit**

```bash
git add pyminidash/providers/localproj/__init__.py pyminidash/providers/__init__.py config.example.toml README.md docs/ETAT.md tests/test_providers_localproj.py
git commit -m "$(printf 'Ajoute le provider local_projects (orchestration + doc)\n\nDecouverte multi-racines, parsing par ecosysteme, Git parallelise\n(ThreadPoolExecutor), parametres ignore/max_depth/libs/show. Exemple de\nconfig, entree README, mise a jour ETAT.\n\nCo-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>')"
```

---

## Task 9 : Revue de branche et finalisation

**Files:** aucun changement de code a priori.

- [ ] **Step 1 : Vérifier la suite complète**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected : tout vert, warnings inchangés (`StarletteDeprecationWarning` toléré).

- [ ] **Step 2 : Vérifier le lancement réel**

```bash
./.venv/Scripts/python.exe -m pyminidash --config config.example.toml --port 8000
```
Ouvrir `http://localhost:8000/groups/projets`, vérifier que le bloc « Tous les projets » se calcule (adapter `roots` dans une copie locale de config si `D:/projet` n'existe pas dans l'environnement de test).

- [ ] **Step 3 : Suivre `superpowers:finishing-a-development-branch`**

Revue globale de branche, puis PR `#4` vers `main` avec récapitulatif (nouveau provider, hook `validate`, tweak rendu). Mettre à jour l'en-tête de `docs/ETAT.md` (hash `main`, compteur de tests) dans le commit de merge ou juste après.

---

## Self-Review

**1. Spec coverage**

| Section spec | Tâche |
|---|---|
| §2 config (`roots`/`ignore`/`max_depth`/`libs`/`show`), validation | T1 (hook), T3 (`roots` runtime), T8 (`_validate_cfg`, exemple) |
| §2 `timeout = 60` recommandé | T8 step 6/7 (config.example, README) |
| §3 découverte (ignorés, marqueurs, DFS, dédup, tri, arrêt 1er marqueur) | T3 |
| §3 sous-scan Maven | T6 (`_angular_subscan`) |
| §4 Git (status v2, log, for-each-ref, remote ; `None` hors dépôt ; détaché) | T4 |
| §4 parallélisation `ThreadPoolExecutor(8)` | T8 |
| §5.1 maven (GAV, parent, `${}`, parent sur disque, Java, Spring Boot, modules, libs, frontend) | T6 |
| §5.2-5.5 node/cargo/gomod/python | T5 |
| §5 composites (`version`, `stack`, `maven_coords`, `modules`, `libs`, `frontend_build`) | T7 |
| §6 schéma 16 champs, ordre, tiers résumé/replié | T7 |
| §6 `show` (filtre, ordre, `name` forcé, à plat) | T7 |
| §6 date relative | T7 (`relative_date`) |
| §7 hook `validate` (registry + config) | T1 |
| §8 masquage champs repliés vides | T2 |
| §9 structure de fichiers | T3-T8 |
| §10 orchestration | T8 |
| §11 plan de tests | tests dans chaque tâche |
| §12 risques | pris en compte (timeout bloc, parallélisation, parsing défensif) |

Pas de gap identifié.

**2. Placeholder scan** — les steps « docs » (T8 step 8, T9) décrivent des éditions de prose (ETAT.md, README) : le contenu exact à écrire y est spécifié (compteurs, lignes de tableau, liens). Aucun `TODO`/`TBD` dans le code. Le seul « à ajuster si » est la note namespace de `_frontend` en T6 step 4, avec la solution donnée.

**3. Type consistency**

- `ProjectDir(path, name, types)` — identique en T3, consommé tel quel en T6/T7/T8.
- `GitInfo` — 10 champs définis en T4, consommés en T7 (`_git_fields`, `_dirty_field`) avec les mêmes noms (`dirty_count`, `commit_hash_short`, `commit_date`, `upstream`, `ahead`, `behind`, `branches`, `remotes`).
- `MavenInfo` — 15 champs définis en T6, consommés en T7 (`_stack`, `_maven_coords`, `_libs`, `_frontend_build`) : `java_version`, `spring_boot_version`, `parent_gav`, `modules`, `libs` (paires), `frontend_plugin_version`/`frontend_node_version`/`frontend_npm_version`, `angular_version`, `angular_material_version`, `group_id`, `artifact_id`, `version`, `readable`, `name`. Cohérent.
- `NodeInfo`/`CargoInfo`/`GoInfo`/`PythonInfo` — champs de T5 consommés en T7 (`info.name`, `info.version`, `cargo.edition`, `cargo.rust_version`, `cargo.members`, `go.go_version`, `node.angular_version`, `node.angular_material_version`). Cohérent (noter : `GoInfo` n'a pas de `.version` — `_version()` ne l'interroge pas).
- `parse_maven(project_dir, libs)` — signature à 2 args en T6, appelée avec 2 args en T8 (`_parse_all`).
- `to_record(project, parsed, git, show)` — 4 args en T7, appelé avec 4 args en T8.
- `KNOWN_FIELDS` — défini en T7, importé en T8 (`_validate_cfg`) et dans les tests.
- `provider(name, *, validate=...)` — T1, utilisé en T8.

Aucune incohérence.

---

## Execution Handoff

**Plan complet et enregistré dans `docs/superpowers/plans/2026-08-30-pyminidash-local-projects.md`. Deux options d'exécution :**

**1. Subagent-Driven (recommandé)** — je dispatche un sous-agent frais par tâche, revue entre chaque, itération rapide.

**2. Inline Execution** — exécution des tâches dans cette session via `executing-plans`, exécution par lots avec points de contrôle.

**Quelle approche ?**
