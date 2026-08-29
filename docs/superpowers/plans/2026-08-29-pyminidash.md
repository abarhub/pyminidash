# pyminidash Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construire un mini-dashboard web local qui affiche des groupes définis en config TOML, chaque groupe rendant des tableaux ou des cards produits par des providers Python intégrés.

**Architecture:** FastAPI + HTMX, fragments HTML rendus côté serveur. Un registre de providers (fonctions décorées `@provider`) produit des `list[Record]` ; un runner les exécute dans un thread avec timeout ; des transformateurs de rendu convertissent les records en vues table/cards ; des routes servent la page d'un groupe (placeholders auto-chargés) et le fragment d'un bloc (exécuté à chaque affichage / recalcul). Aucune persistance.

**Tech Stack:** Python 3.13, `uv`, FastAPI, Uvicorn, Jinja2, HTMX (vendu), `httpx`, `psutil`, Pydantic v2, `tomllib` (stdlib). Tests : `pytest`, `pytest-asyncio`, `respx`.

**Spec:** `docs/superpowers/specs/2026-08-29-pyminidash-design.md`

## Global Constraints

- Python `>=3.13`. Gestionnaire de paquets et lanceur : `uv` (`uv run`, `uv sync`). `python` seul n'est pas sur le PATH — toujours `uv run python`.
- Plateforme de dev : Windows 11, shell PowerShell + Bash disponible. Les chemins de test doivent rester cross-platform (`tmp_path`, pas de chemin en dur).
- Providers : **catalogue intégré uniquement**, pas de découverte de plugins. Un provider s'enregistre par le décorateur `@provider("nom")` à l'import de son module.
- Paramètres des providers : viennent **uniquement** de la config, jamais du front.
- Un provider retourne une **`list[Record]`** ; 1 record = 1 ligne de table **ou** 1 card. Records homogènes (mêmes `key`, même ordre).
- Recalcul : granularité = le provider (un bloc). Le bouton « Tout recalculer » ne concerne que le groupe affiché.
- À l'ouverture d'un groupe : tous les blocs se calculent automatiquement, avec un état de chargement.
- Aucune persistance : pas de cache, pas de base de données.
- Format de config : TOML, lu par `tomllib`. Adressage des blocs : index automatique dans la liste.
- Timeout par défaut d'un provider : `10.0` s, surchargeable par bloc (`timeout` en config).
- Langue de l'UI et des messages d'erreur destinés à l'utilisateur : français.
- TDD strict : test qui échoue → implémentation minimale → test qui passe → commit. Commits fréquents.

---

## File Structure

Fichiers créés (tous sous `D:\projet\pyminidash\`) :

| Fichier | Responsabilité |
|---|---|
| `pyproject.toml` | *(modifié)* dépendances, script console, config pytest |
| `pyminidash/__init__.py` | marqueur de package (vide) |
| `pyminidash/models.py` | `Field`, `Record`, enums, helpers de construction de champs |
| `pyminidash/format.py` | `format_value(field) -> str` : formatage d'une valeur selon son type |
| `pyminidash/registry.py` | `@provider`, `REGISTRY`, `ProviderDef`, `get_provider`, `validate_params` |
| `pyminidash/config.py` | modèles Pydantic, `load_config`, `ConfigError` |
| `pyminidash/runner.py` | `run_block`, `BlockOk`, `BlockError`, `DEFAULT_TIMEOUT` |
| `pyminidash/web/__init__.py` | marqueur de package (vide) |
| `pyminidash/web/render.py` | `to_table`, `to_cards`, `TableView`, `CardView`, `Column` |
| `pyminidash/web/app.py` | `create_app(config) -> FastAPI` |
| `pyminidash/web/routes.py` | `router` : `/`, `/groups/{id}`, `/groups/{id}/blocks/{n}` |
| `pyminidash/web/templates/*.html` | `base`, `group`, `_loading`, `_field`, `_block_head`, `_table`, `_cards`, `_error` |
| `pyminidash/web/static/app.css` | feuille de style |
| `pyminidash/web/static/app.js` | toggle « afficher plus », bouton « Tout recalculer » |
| `pyminidash/web/static/htmx.min.js` | HTMX vendu |
| `pyminidash/providers/__init__.py` | importe `system` et `http` pour déclencher l'enregistrement |
| `pyminidash/providers/system.py` | `disk_usage`, `top_processes` |
| `pyminidash/providers/http.py` | `http_check`, `http_json` |
| `pyminidash/__main__.py` | `main()` : CLI, charge la config, lance Uvicorn |
| `config.example.toml` | config d'exemple |
| `tests/conftest.py` | isolation du registre, providers factices |
| `tests/test_*.py` | un fichier par module |
| `README.md` | *(modifié)* mode d'emploi |

---

## Task 1: Scaffold du projet + modèle de données

**Files:**
- Modify: `pyproject.toml`
- Create: `pyminidash/__init__.py`, `pyminidash/models.py`
- Create: `tests/__init__.py`, `tests/test_models.py`

**Interfaces:**
- Consumes: rien (première tâche).
- Produces :
  - `FieldType(str, Enum)` : `TEXT="text"`, `NUMBER="number"`, `BYTES="bytes"`, `PERCENT="percent"`, `STATUS="status"`, `LINK="link"`, `DATETIME="datetime"`, `DURATION="duration"`
  - `StatusLevel(str, Enum)` : `OK="ok"`, `WARN="warn"`, `ERROR="error"`, `NEUTRAL="neutral"`
  - `FieldRole(str, Enum)` : `NORMAL="normal"`, `TITLE="title"`, `BADGE="badge"`
  - `Field` — dataclass frozen : `key: str`, `label: str`, `value: Any`, `type: FieldType = FieldType.TEXT`, `role: FieldRole = FieldRole.NORMAL`, `summary: bool = False`, `level: StatusLevel | None = None`, `url: str | None = None`
  - `Record` — `__init__(self, *fields: Field)`, attribut `fields: tuple[Field, ...]`, méthode `keys(self) -> tuple[str, ...]`, `__eq__`
  - Helpers renvoyant `Field` :
    - `text(key, label, value, *, summary=False, role=FieldRole.NORMAL)`
    - `number(key, label, value, *, summary=False, role=FieldRole.NORMAL)`
    - `bytes_(key, label, value, *, summary=False, role=FieldRole.NORMAL)`
    - `percent(key, label, value, *, summary=False, role=FieldRole.NORMAL)`
    - `datetime_(key, label, value, *, summary=False, role=FieldRole.NORMAL)`
    - `duration(key, label, value, *, summary=False, role=FieldRole.NORMAL)`
    - `status(key, label, value, *, level: StatusLevel, summary=False, role=FieldRole.BADGE)`
    - `link(key, label, value, url, *, summary=False, role=FieldRole.NORMAL)`
    - `title(key, label, value)` → `role=FieldRole.TITLE`, `type=FieldType.TEXT`

- [ ] **Step 1: Remplacer `pyproject.toml`**

```toml
[project]
name = "pyminidash"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "jinja2>=3.1",
    "httpx>=0.27",
    "psutil>=6.0",
]

[project.scripts]
pyminidash = "pyminidash.__main__:main"

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "respx>=0.21",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

- [ ] **Step 2: Synchroniser l'environnement**

Run: `uv sync`
Expected: résolution + installation OK, un `uv.lock` mis à jour.

- [ ] **Step 3: Créer les marqueurs de package**

Créer `pyminidash/__init__.py` (vide) et `tests/__init__.py` (vide).

- [ ] **Step 4: Écrire le test qui échoue** — `tests/test_models.py`

```python
from datetime import datetime

from pyminidash.models import (
    Field, FieldRole, FieldType, Record, StatusLevel,
    bytes_, datetime_, duration, link, number, percent, status, text, title,
)


def test_text_helper_defaults():
    f = text("name", "Nom", "chrome")
    assert f == Field(key="name", label="Nom", value="chrome", type=FieldType.TEXT)
    assert f.role is FieldRole.NORMAL
    assert f.summary is False


def test_title_helper_sets_role():
    f = title("mount", "Disque", "C:\\")
    assert f.role is FieldRole.TITLE
    assert f.type is FieldType.TEXT


def test_status_helper_requires_level_and_defaults_to_badge():
    f = status("state", "État", "UP", level=StatusLevel.OK, summary=True)
    assert f.type is FieldType.STATUS
    assert f.level is StatusLevel.OK
    assert f.role is FieldRole.BADGE
    assert f.summary is True


def test_link_helper_carries_url():
    f = link("url", "URL", "voir", "https://example.test")
    assert f.type is FieldType.LINK
    assert f.url == "https://example.test"


def test_typed_helpers_set_their_type():
    assert number("n", "N", 3).type is FieldType.NUMBER
    assert bytes_("b", "B", 1024).type is FieldType.BYTES
    assert percent("p", "P", 50).type is FieldType.PERCENT
    assert datetime_("d", "D", datetime(2026, 1, 1)).type is FieldType.DATETIME
    assert duration("t", "T", 90).type is FieldType.DURATION


def test_record_keys_and_equality():
    r1 = Record(text("a", "A", "1"), text("b", "B", "2"))
    r2 = Record(text("a", "A", "1"), text("b", "B", "2"))
    assert r1 == r2
    assert r1.keys() == ("a", "b")


def test_field_is_frozen():
    import dataclasses
    import pytest
    f = text("a", "A", "1")
    with pytest.raises(dataclasses.FrozenInstanceError):
        f.value = "2"
```

- [ ] **Step 5: Lancer le test, vérifier l'échec**

Run: `uv run pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pyminidash.models'`

- [ ] **Step 6: Écrire `pyminidash/models.py`**

```python
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
```

- [ ] **Step 7: Lancer le test, vérifier le succès**

Run: `uv run pytest tests/test_models.py -v`
Expected: PASS (7 tests)

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "Ajoute le scaffold du projet et le modèle de données (Field, Record)"
```

---

## Task 2: Formatage des valeurs (`format.py`)

**Files:**
- Create: `pyminidash/format.py`
- Create: `tests/test_format.py`

**Interfaces:**
- Consumes: `pyminidash.models` (`Field`, `FieldType`).
- Produces: `format_value(field: Field) -> str` — texte prêt à afficher pour tous les types **sauf** la mise en forme HTML de `status` (pastille) et `link` (ancre), qui reste au template. Pour `status` et `link`, `format_value` renvoie `str(field.value)`.
  - `TEXT` / `STATUS` / `LINK` : `str(value)` (`""` si `value is None`)
  - `NUMBER` : `f"{value:g}"` si `value` est `int`/`float`, sinon `str(value)`
  - `BYTES` : base 1024, `"512 B"`, `"1.5 KB"`, `"218.0 GB"` … unités `B KB MB GB TB PB`
  - `PERCENT` : `f"{float(value):g} %"` (ex. `"76 %"`)
  - `DATETIME` : `value.strftime("%Y-%m-%d %H:%M:%S")` si `datetime`, sinon `str(value)`
  - `DURATION` : `value` en secondes → `"820 ms"` (<1 s), `"45 s"` (<60 s), `"3 min 5 s"` (<1 h), `"2 h 10 min"` (≥1 h)

- [ ] **Step 1: Écrire le test qui échoue** — `tests/test_format.py`

```python
from datetime import datetime

from pyminidash.format import format_value
from pyminidash.models import bytes_, datetime_, duration, link, number, percent, status, text
from pyminidash.models import StatusLevel


def test_text_none_is_empty():
    assert format_value(text("k", "L", None)) == ""


def test_number_trims():
    assert format_value(number("k", "L", 18.20)) == "18.2"
    assert format_value(number("k", "L", 910)) == "910"


def test_bytes_humanized():
    assert format_value(bytes_("k", "L", 512)) == "512 B"
    assert format_value(bytes_("k", "L", 1536)) == "1.5 KB"
    assert format_value(bytes_("k", "L", 234881024000)) == "218.8 GB"


def test_percent():
    assert format_value(percent("k", "L", 76)) == "76 %"


def test_datetime():
    assert format_value(datetime_("k", "L", datetime(2026, 8, 29, 14, 32, 7))) == "2026-08-29 14:32:07"


def test_duration():
    assert format_value(duration("k", "L", 0.82)) == "820 ms"
    assert format_value(duration("k", "L", 45)) == "45 s"
    assert format_value(duration("k", "L", 185)) == "3 min 5 s"
    assert format_value(duration("k", "L", 7800)) == "2 h 10 min"


def test_status_and_link_return_plain_text():
    assert format_value(status("k", "L", "UP", level=StatusLevel.OK)) == "UP"
    assert format_value(link("k", "L", "voir", "https://x.test")) == "voir"
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `uv run pytest tests/test_format.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pyminidash.format'`

- [ ] **Step 3: Écrire `pyminidash/format.py`**

```python
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
```

- [ ] **Step 4: Lancer le test, vérifier le succès**

Run: `uv run pytest tests/test_format.py -v`
Expected: PASS. Si `test_bytes_humanized` diverge de quelques dixièmes, ajuster la valeur **attendue** dans le test sur la sortie réelle (l'algorithme fait foi), pas l'inverse.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "Ajoute le formatage des valeurs (format_value)"
```

---

## Task 3: Registre de providers (`registry.py`)

**Files:**
- Create: `pyminidash/registry.py`
- Create: `tests/test_registry.py`

**Interfaces:**
- Consumes: `pyminidash.models` (type de retour `list[Record]`, non contraint à l'exécution).
- Produces:
  - `REGISTRY: dict[str, ProviderDef]` — dict global module-level
  - `ProviderDef` — dataclass : `name: str`, `func: Callable[..., list]`, `signature: inspect.Signature`
  - `provider(name: str)` — décorateur ; lève `ValueError` si `name` déjà présent ; renvoie la fonction inchangée
  - `get_provider(name: str) -> ProviderDef` — lève `ValueError` avec la liste triée des providers disponibles si absent
  - `list_providers() -> list[str]` — noms triés
  - `validate_params(pdef: ProviderDef, params: dict) -> None` — `pdef.signature.bind(**params)` ; sur `TypeError`, lève `ValueError(f"{pdef.name}: {msg} ; signature attendue: {pdef.signature}")`

- [ ] **Step 1: Écrire le test qui échoue** — `tests/test_registry.py`

```python
import pytest

from pyminidash.models import Record, text
from pyminidash.registry import (
    REGISTRY, get_provider, list_providers, provider, validate_params,
)


@pytest.fixture(autouse=True)
def _clean_registry():
    saved = dict(REGISTRY)
    REGISTRY.clear()
    yield
    REGISTRY.clear()
    REGISTRY.update(saved)


def test_decorator_registers_and_returns_function():
    @provider("demo")
    def demo(a: int, b: str = "x"):
        return [Record(text("k", "L", f"{a}{b}"))]

    assert demo(1) == [Record(text("k", "L", "1x"))]
    assert "demo" in REGISTRY
    assert list_providers() == ["demo"]


def test_duplicate_name_raises():
    @provider("demo")
    def demo():
        return []

    with pytest.raises(ValueError, match="demo"):
        @provider("demo")
        def demo2():
            return []


def test_get_provider_unknown_lists_available():
    @provider("alpha")
    def alpha():
        return []

    with pytest.raises(ValueError, match="alpha"):
        get_provider("beta")


def test_validate_params_ok():
    @provider("p")
    def p(paths: list, limit: int = 3):
        return []

    validate_params(get_provider("p"), {"paths": ["a"], "limit": 5})


def test_validate_params_missing_required():
    @provider("p")
    def p(paths: list):
        return []

    with pytest.raises(ValueError, match="signature attendue"):
        validate_params(get_provider("p"), {})


def test_validate_params_unknown_key():
    @provider("p")
    def p(limit: int = 3):
        return []

    with pytest.raises(ValueError, match="signature attendue"):
        validate_params(get_provider("p"), {"nope": 1})
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `uv run pytest tests/test_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pyminidash.registry'`

- [ ] **Step 3: Écrire `pyminidash/registry.py`**

```python
"""Registre global des providers. Un provider est une fonction décorée
@provider("nom") ; ses modules sont importés au démarrage pour l'enregistrer."""
from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class ProviderDef:
    name: str
    func: Callable[..., list]
    signature: inspect.Signature


REGISTRY: dict[str, ProviderDef] = {}


def provider(name: str) -> Callable[[Callable[..., list]], Callable[..., list]]:
    def decorator(func: Callable[..., list]) -> Callable[..., list]:
        if name in REGISTRY:
            raise ValueError(f"provider '{name}' déjà enregistré")
        REGISTRY[name] = ProviderDef(name=name, func=func,
                                     signature=inspect.signature(func))
        return func

    return decorator


def list_providers() -> list[str]:
    return sorted(REGISTRY)


def get_provider(name: str) -> ProviderDef:
    try:
        return REGISTRY[name]
    except KeyError:
        available = ", ".join(list_providers()) or "(aucun)"
        raise ValueError(
            f"provider inconnu: '{name}' ; providers disponibles : {available}"
        ) from None


def validate_params(pdef: ProviderDef, params: dict) -> None:
    try:
        pdef.signature.bind(**params)
    except TypeError as exc:
        raise ValueError(
            f"{pdef.name}: {exc} ; signature attendue: {pdef.signature}"
        ) from None
```

- [ ] **Step 4: Lancer le test, vérifier le succès**

Run: `uv run pytest tests/test_registry.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "Ajoute le registre de providers (@provider, get_provider, validate_params)"
```

---

## Task 4: Chargement et validation de la config (`config.py`)

**Files:**
- Create: `pyminidash/config.py`
- Create: `tests/conftest.py`
- Create: `tests/test_config.py`

**Interfaces:**
- Consumes: `pyminidash.registry` (`get_provider`, `validate_params`).
- Produces:
  - `ConfigError(Exception)`
  - `BlockConfig(BaseModel)` : `provider: str`, `params: dict[str, Any] = {}`, `title: str | None = None`, `timeout: float | None = None`. **Après validation, `title` est toujours une `str`** (défaut = `provider`).
  - `GroupConfig(BaseModel)` : `id: str`, `title: str`, `type: Literal["table", "cards"]`, `blocks: list[BlockConfig]` (min 1).
  - `AppConfig(BaseModel)` : `title: str = "pyminidash"`, `default_group: str | None = None`. **Après validation, `default_group` est toujours une `str`** (défaut = `groups[0].id`).
  - `Config(BaseModel)` : `app: AppConfig`, `groups: list[GroupConfig]` (min 1).
  - `load_config(path: str | Path) -> Config` — lève `ConfigError` sur : fichier absent, TOML invalide, échec de validation Pydantic, id de groupe en double, `default_group` inexistant, provider inconnu, paramètres invalides.
- Note : `config.py` n'importe **pas** `pyminidash.providers`. C'est `__main__` (Task 11) et les tests qui garantissent l'enregistrement des providers avant `load_config`.

- [ ] **Step 1: Écrire `tests/conftest.py`**

```python
"""Fixtures partagées : isolation du registre global + providers factices."""
import pytest

from pyminidash.models import Record, status, text, title
from pyminidash.models import StatusLevel
from pyminidash.registry import REGISTRY, provider


@pytest.fixture(autouse=True)
def _registry_snapshot():
    """Restaure REGISTRY à l'état d'avant-test (évite les fuites entre tests)."""
    saved = dict(REGISTRY)
    yield
    REGISTRY.clear()
    REGISTRY.update(saved)


@pytest.fixture
def dummy_providers():
    """Enregistre des providers de test. Nettoyage assuré par _registry_snapshot."""
    @provider("dummy_rows")
    def dummy_rows(n: int = 2):
        return [
            Record(
                title("name", "Nom", f"item{i}"),
                status("state", "État", "UP", level=StatusLevel.OK, summary=True),
                text("detail", "Détail", f"ligne cachée {i}"),
            )
            for i in range(n)
        ]

    @provider("dummy_boom")
    def dummy_boom():
        raise RuntimeError("boom interne")

    @provider("dummy_empty")
    def dummy_empty():
        return []

    return ["dummy_rows", "dummy_boom", "dummy_empty"]
```

- [ ] **Step 2: Écrire le test qui échoue** — `tests/test_config.py`

```python
import textwrap

import pytest

from pyminidash.config import ConfigError, load_config


def _write(tmp_path, body: str):
    p = tmp_path / "config.toml"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


def test_missing_file(tmp_path):
    with pytest.raises(ConfigError, match="introuvable"):
        load_config(tmp_path / "absent.toml")


def test_invalid_toml(tmp_path, dummy_providers):
    p = _write(tmp_path, "this is = = not toml")
    with pytest.raises(ConfigError, match="TOML"):
        load_config(p)


def test_valid_config_resolves_defaults(tmp_path, dummy_providers):
    p = _write(tmp_path, """
        [[groups]]
        id = "g1"
        title = "Groupe 1"
        type = "table"
          [[groups.blocks]]
          provider = "dummy_rows"
          params = { n = 3 }
    """)
    cfg = load_config(p)
    assert cfg.app.title == "pyminidash"
    assert cfg.app.default_group == "g1"          # défaut = 1er groupe
    assert cfg.groups[0].blocks[0].title == "dummy_rows"  # défaut = nom du provider


def test_duplicate_group_id(tmp_path, dummy_providers):
    p = _write(tmp_path, """
        [[groups]]
        id = "dup"
        title = "A"
        type = "table"
          [[groups.blocks]]
          provider = "dummy_rows"
        [[groups]]
        id = "dup"
        title = "B"
        type = "cards"
          [[groups.blocks]]
          provider = "dummy_rows"
    """)
    with pytest.raises(ConfigError, match="double"):
        load_config(p)


def test_unknown_default_group(tmp_path, dummy_providers):
    p = _write(tmp_path, """
        [app]
        default_group = "nope"
        [[groups]]
        id = "g1"
        title = "A"
        type = "table"
          [[groups.blocks]]
          provider = "dummy_rows"
    """)
    with pytest.raises(ConfigError, match="default_group"):
        load_config(p)


def test_unknown_provider(tmp_path, dummy_providers):
    p = _write(tmp_path, """
        [[groups]]
        id = "g1"
        title = "A"
        type = "table"
          [[groups.blocks]]
          provider = "does_not_exist"
    """)
    with pytest.raises(ConfigError, match="does_not_exist"):
        load_config(p)


def test_bad_params(tmp_path, dummy_providers):
    p = _write(tmp_path, """
        [[groups]]
        id = "g1"
        title = "A"
        type = "table"
          [[groups.blocks]]
          provider = "dummy_rows"
          params = { unexpected = 1 }
    """)
    with pytest.raises(ConfigError, match="signature attendue"):
        load_config(p)


def test_bad_group_type(tmp_path, dummy_providers):
    p = _write(tmp_path, """
        [[groups]]
        id = "g1"
        title = "A"
        type = "grid"
          [[groups.blocks]]
          provider = "dummy_rows"
    """)
    with pytest.raises(ConfigError):
        load_config(p)


def test_empty_blocks_rejected(tmp_path, dummy_providers):
    p = _write(tmp_path, """
        [[groups]]
        id = "g1"
        title = "A"
        type = "table"
        blocks = []
    """)
    with pytest.raises(ConfigError):
        load_config(p)
```

- [ ] **Step 3: Lancer le test, vérifier l'échec**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pyminidash.config'`

- [ ] **Step 4: Écrire `pyminidash/config.py`**

```python
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
```

- [ ] **Step 5: Lancer le test, vérifier le succès**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS (10 tests)

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "Ajoute le chargement et la validation de la config TOML"
```

---

## Task 5: Exécution d'un bloc (`runner.py`)

**Files:**
- Create: `pyminidash/runner.py`
- Create: `tests/test_runner.py`

**Interfaces:**
- Consumes: `pyminidash.config` (`BlockConfig`), `pyminidash.registry` (`get_provider`), `pyminidash.models` (`Record`).
- Produces:
  - `DEFAULT_TIMEOUT: float = 10.0`
  - `BlockError` — dataclass : `kind: str` (`"exception"` | `"timeout"` | `"invalid_result"`), `message: str`
  - `BlockOk` — dataclass : `records: list[Record]`, `computed_at: datetime`
  - `BlockResult = BlockOk | BlockError` (alias d'union)
  - `async run_block(block: BlockConfig) -> BlockResult` :
    - résout le provider, exécute `func(**block.params)` dans un thread (`asyncio.to_thread`) sous `asyncio.wait_for(timeout = block.timeout or DEFAULT_TIMEOUT)`
    - `TimeoutError` → `BlockError("timeout", f"timeout après {timeout:g} s")`
    - toute autre exception → `BlockError("exception", f"{type(e).__name__}: {e}")` + log `logging.getLogger("pyminidash.runner").exception(...)`
    - résultat non conforme (pas une `list[Record]`, ou records hétérogènes) → `BlockError("invalid_result", <détail>)`
    - sinon → `BlockOk(records, datetime.now())`
    - liste vide = valide → `BlockOk([], ...)`

- [ ] **Step 1: Écrire le test qui échoue** — `tests/test_runner.py`

```python
import pytest

from pyminidash.config import BlockConfig
from pyminidash.models import Record, text
from pyminidash.registry import provider
from pyminidash.runner import BlockError, BlockOk, run_block


async def test_ok_returns_records():
    @provider("r_ok")
    def r_ok(n: int = 2):
        return [Record(text("k", "L", str(i))) for i in range(n)]

    res = await run_block(BlockConfig(provider="r_ok", params={"n": 3}))
    assert isinstance(res, BlockOk)
    assert len(res.records) == 3
    assert res.computed_at is not None


async def test_empty_list_is_ok():
    @provider("r_empty")
    def r_empty():
        return []

    res = await run_block(BlockConfig(provider="r_empty"))
    assert isinstance(res, BlockOk)
    assert res.records == []


async def test_exception_becomes_block_error():
    @provider("r_boom")
    def r_boom():
        raise RuntimeError("cassé")

    res = await run_block(BlockConfig(provider="r_boom"))
    assert isinstance(res, BlockError)
    assert res.kind == "exception"
    assert "RuntimeError" in res.message and "cassé" in res.message


async def test_timeout_becomes_block_error():
    @provider("r_slow")
    def r_slow():
        import time
        time.sleep(0.5)
        return []

    res = await run_block(BlockConfig(provider="r_slow", timeout=0.1))
    assert isinstance(res, BlockError)
    assert res.kind == "timeout"


async def test_non_list_result_is_invalid():
    @provider("r_bad")
    def r_bad():
        return "pas une liste"

    res = await run_block(BlockConfig(provider="r_bad"))
    assert isinstance(res, BlockError)
    assert res.kind == "invalid_result"


async def test_heterogeneous_records_invalid():
    @provider("r_het")
    def r_het():
        return [Record(text("a", "A", "1")), Record(text("b", "B", "2"))]

    res = await run_block(BlockConfig(provider="r_het"))
    assert isinstance(res, BlockError)
    assert res.kind == "invalid_result"
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `uv run pytest tests/test_runner.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pyminidash.runner'`

- [ ] **Step 3: Écrire `pyminidash/runner.py`**

```python
"""Exécution d'un bloc : appelle le provider dans un thread, avec timeout,
et normalise le résultat ou l'erreur."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime

from pyminidash.config import BlockConfig
from pyminidash.models import Record
from pyminidash.registry import get_provider

log = logging.getLogger("pyminidash.runner")

DEFAULT_TIMEOUT: float = 10.0


@dataclass(frozen=True)
class BlockError:
    kind: str  # "exception" | "timeout" | "invalid_result"
    message: str


@dataclass(frozen=True)
class BlockOk:
    records: list[Record]
    computed_at: datetime


BlockResult = BlockOk | BlockError


def _check_records(result: object) -> str | None:
    if not isinstance(result, list) or any(not isinstance(r, Record) for r in result):
        return "le provider n'a pas renvoyé une list[Record]"
    if result:
        expected = result[0].keys()
        for r in result[1:]:
            if r.keys() != expected:
                return (f"records hétérogènes : attendu {expected}, "
                        f"obtenu {r.keys()}")
    return None


async def run_block(block: BlockConfig) -> BlockResult:
    pdef = get_provider(block.provider)
    timeout = block.timeout or DEFAULT_TIMEOUT
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(pdef.func, **block.params), timeout
        )
    except (asyncio.TimeoutError, TimeoutError):
        log.warning("bloc '%s' : timeout après %gs", block.provider, timeout)
        return BlockError("timeout", f"timeout après {timeout:g} s")
    except Exception as exc:  # noqa: BLE001 — on veut tout attraper
        log.exception("bloc '%s' : exception du provider", block.provider)
        return BlockError("exception", f"{type(exc).__name__}: {exc}")

    problem = _check_records(result)
    if problem:
        log.error("bloc '%s' : %s", block.provider, problem)
        return BlockError("invalid_result", problem)
    return BlockOk(records=result, computed_at=datetime.now())
```

- [ ] **Step 4: Lancer le test, vérifier le succès**

Run: `uv run pytest tests/test_runner.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "Ajoute le runner (exécution d'un bloc avec timeout et normalisation)"
```

---

## Task 6: Transformateurs de rendu (`web/render.py`)

**Files:**
- Create: `pyminidash/web/__init__.py` (vide)
- Create: `pyminidash/web/render.py`
- Create: `tests/test_render.py`

**Interfaces:**
- Consumes: `pyminidash.models` (`Record`, `Field`, `FieldRole`).
- Produces:
  - `Column` — dataclass : `key: str`, `label: str`
  - `TableView` — dataclass : `columns: list[Column]`, `rows: list[list[Field]]` (chaque ligne = les `Field` dans l'ordre des colonnes)
  - `CardView` — dataclass : `title: str | None`, `badge: Field | None`, `summary_fields: list[Field]`, `hidden_fields: list[Field]`
  - `to_table(records: list[Record]) -> TableView` — colonnes = champs du **1er** record dans l'ordre ; une ligne par record. Précondition : `records` non vide (l'appelant gère le cas vide).
  - `to_cards(records: list[Record]) -> list[CardView]` — par record : 1er champ `role=TITLE` → `title` (via `format_value`), 1er champ `role=BADGE` → `badge`, puis les champs restants classés `summary` vs caché selon `Field.summary`. Un champ consommé comme titre/badge n'apparaît pas dans les listes summary/hidden.

- [ ] **Step 1: Écrire le test qui échoue** — `tests/test_render.py`

```python
from pyminidash.models import Record, StatusLevel, bytes_, status, text, title
from pyminidash.web.render import to_cards, to_table


def _disk_records():
    return [
        Record(
            title("mount", "Disque", "C:\\"),
            status("pct", "%", "76 %", level=StatusLevel.WARN, summary=True),
            bytes_("free", "Libre", 218 * 1024**3, summary=True),
            bytes_("total", "Total", 930 * 1024**3),
        ),
        Record(
            title("mount", "Disque", "D:\\"),
            status("pct", "%", "91 %", level=StatusLevel.ERROR, summary=True),
            bytes_("free", "Libre", 210 * 1024**3, summary=True),
            bytes_("total", "Total", 1800 * 1024**3),
        ),
    ]


def test_to_table_column_order_follows_first_record():
    view = to_table(_disk_records())
    assert [c.key for c in view.columns] == ["mount", "pct", "free", "total"]
    assert [c.label for c in view.columns] == ["Disque", "%", "Libre", "Total"]
    assert len(view.rows) == 2
    assert view.rows[0][0].value == "C:\\"


def test_to_cards_extracts_title_badge_and_splits_summary():
    cards = to_cards(_disk_records())
    assert cards[0].title == "C:\\"
    assert cards[0].badge.key == "pct"
    assert [f.key for f in cards[0].summary_fields] == ["free"]
    assert [f.key for f in cards[0].hidden_fields] == ["total"]


def test_to_cards_without_title_or_badge():
    recs = [Record(text("a", "A", "1", summary=True), text("b", "B", "2"))]
    card = to_cards(recs)[0]
    assert card.title is None
    assert card.badge is None
    assert [f.key for f in card.summary_fields] == ["a"]
    assert [f.key for f in card.hidden_fields] == ["b"]
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `uv run pytest tests/test_render.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pyminidash.web'`

- [ ] **Step 3: Écrire `pyminidash/web/render.py`**

```python
"""Transforme une list[Record] en structures prêtes pour les templates."""
from __future__ import annotations

from dataclasses import dataclass

from pyminidash.format import format_value
from pyminidash.models import Field, FieldRole, Record


@dataclass(frozen=True)
class Column:
    key: str
    label: str


@dataclass(frozen=True)
class TableView:
    columns: list[Column]
    rows: list[list[Field]]


@dataclass(frozen=True)
class CardView:
    title: str | None
    badge: Field | None
    summary_fields: list[Field]
    hidden_fields: list[Field]


def to_table(records: list[Record]) -> TableView:
    columns = [Column(f.key, f.label) for f in records[0].fields]
    rows = [list(r.fields) for r in records]
    return TableView(columns=columns, rows=rows)


def to_cards(records: list[Record]) -> list[CardView]:
    cards: list[CardView] = []
    for record in records:
        title_text: str | None = None
        badge: Field | None = None
        summary: list[Field] = []
        hidden: list[Field] = []
        for f in record.fields:
            if f.role is FieldRole.TITLE and title_text is None:
                title_text = format_value(f)
            elif f.role is FieldRole.BADGE and badge is None:
                badge = f
            elif f.summary:
                summary.append(f)
            else:
                hidden.append(f)
        cards.append(CardView(title_text, badge, summary, hidden))
    return cards
```

- [ ] **Step 4: Lancer le test, vérifier le succès**

Run: `uv run pytest tests/test_render.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "Ajoute les transformateurs de rendu (to_table, to_cards)"
```

---

## Task 7: App FastAPI + page d'un groupe

**Files:**
- Create: `pyminidash/web/app.py`
- Create: `pyminidash/web/routes.py`
- Create: `pyminidash/web/templates/base.html`, `group.html`, `_loading.html`
- Create: `pyminidash/web/static/app.css`, `pyminidash/web/static/app.js`
- Create: `pyminidash/web/static/htmx.min.js` (téléchargé)
- Create: `tests/test_routes_pages.py`

**Interfaces:**
- Consumes: `pyminidash.config` (`Config`, `GroupConfig`).
- Produces:
  - `pyminidash/web/app.py` :
    - `TEMPLATES_DIR: Path`, `STATIC_DIR: Path` (constantes module)
    - `create_app(config: Config) -> FastAPI` — pose `app.state.config = config` et `app.state.templates = Jinja2Templates(directory=TEMPLATES_DIR)` avec le filtre Jinja `format_field = format_value` ; monte `/static` ; inclut `routes.router`.
  - `pyminidash/web/routes.py` :
    - `router: APIRouter`
    - `_get_group(request: Request, group_id: str) -> GroupConfig` — `HTTPException(404)` si absent
    - `GET /` → `RedirectResponse(f"/groups/{config.app.default_group}")`
    - `GET /groups/{group_id}` → `TemplateResponse("group.html", ...)` ; contexte : `config`, `group`, `active_group_id`. La page contient un placeholder par bloc avec `hx-get="/groups/{id}/blocks/{index0}" hx-trigger="load, refresh"`.
- Le fragment de bloc (`/groups/{id}/blocks/{n}`) est ajouté en Task 8.

- [ ] **Step 1: Télécharger HTMX**

Run:
```bash
curl -L -o pyminidash/web/static/htmx.min.js https://unpkg.com/htmx.org@2.0.4/dist/htmx.min.js
```
Expected: fichier ~48 KB non vide. Vérifier : `head -c 60 pyminidash/web/static/htmx.min.js` doit afficher un en-tête de version HTMX. Si `curl` échoue (réseau), récupérer le fichier autrement et le placer au même chemin — c'est la seule étape en ligne du plan.

- [ ] **Step 2: Écrire le test qui échoue** — `tests/test_routes_pages.py`

```python
import pytest
from fastapi.testclient import TestClient

from pyminidash.config import Config
from pyminidash.web.app import create_app


@pytest.fixture
def client(dummy_providers):
    config = Config.model_validate({
        "app": {"title": "Test Dash"},
        "groups": [
            {"id": "sys", "title": "Système", "type": "table",
             "blocks": [{"provider": "dummy_rows", "params": {"n": 2}},
                        {"provider": "dummy_empty"}]},
            {"id": "apis", "title": "APIs", "type": "cards",
             "blocks": [{"provider": "dummy_rows"}]},
        ],
    })
    return TestClient(create_app(config))


def test_root_redirects_to_default_group(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "/groups/sys"


def test_group_page_lists_groups_in_sidebar(client):
    html = client.get("/groups/sys").text
    assert "Système" in html and "APIs" in html
    assert "Test Dash" in html


def test_group_page_has_one_placeholder_per_block(client):
    html = client.get("/groups/sys").text
    assert html.count('hx-get="/groups/sys/blocks/0"') == 1
    assert html.count('hx-get="/groups/sys/blocks/1"') == 1
    assert 'hx-trigger="load, refresh"' in html
    assert 'id="recalc-all"' in html


def test_unknown_group_is_404(client):
    assert client.get("/groups/nope").status_code == 404
```

- [ ] **Step 3: Lancer le test, vérifier l'échec**

Run: `uv run pytest tests/test_routes_pages.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pyminidash.web.app'`

- [ ] **Step 4: Écrire `pyminidash/web/app.py`**

```python
"""Fabrique de l'application FastAPI."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from pyminidash.config import Config
from pyminidash.format import format_value
from pyminidash.web import routes

_HERE = Path(__file__).parent
TEMPLATES_DIR = _HERE / "templates"
STATIC_DIR = _HERE / "static"


def create_app(config: Config) -> FastAPI:
    app = FastAPI(title=config.app.title)
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    templates.env.filters["format_field"] = format_value

    app.state.config = config
    app.state.templates = templates

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.include_router(routes.router)
    return app
```

- [ ] **Step 5: Écrire `pyminidash/web/routes.py`**

```python
"""Routes HTTP. La page d'un groupe pose un placeholder auto-chargé par bloc ;
le fragment d'un bloc est servi par block_fragment (Task 8)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from pyminidash.config import GroupConfig

router = APIRouter()


def _get_group(request: Request, group_id: str) -> GroupConfig:
    for group in request.app.state.config.groups:
        if group.id == group_id:
            return group
    raise HTTPException(status_code=404, detail=f"groupe inconnu : {group_id}")


@router.get("/")
def index(request: Request) -> RedirectResponse:
    default = request.app.state.config.app.default_group
    return RedirectResponse(url=f"/groups/{default}")


@router.get("/groups/{group_id}", response_class=HTMLResponse)
def group_page(request: Request, group_id: str) -> HTMLResponse:
    group = _get_group(request, group_id)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name="group.html",
        context={
            "config": request.app.state.config,
            "group": group,
            "active_group_id": group_id,
        },
    )
```

- [ ] **Step 6: Écrire les templates**

`pyminidash/web/templates/base.html` :
```html
<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ config.app.title }}</title>
  <link rel="stylesheet" href="/static/app.css">
  <script src="/static/htmx.min.js" defer></script>
  <script src="/static/app.js" defer></script>
</head>
<body>
  <nav class="sidebar">
    <div class="brand">{{ config.app.title }}</div>
    <ul>
      {% for g in config.groups %}
      <li>
        <a href="/groups/{{ g.id }}"
           class="{{ 'active' if g.id == active_group_id else '' }}">{{ g.title }}</a>
      </li>
      {% endfor %}
    </ul>
  </nav>
  <main class="content">
    {% block content %}{% endblock %}
  </main>
</body>
</html>
```

`pyminidash/web/templates/group.html` :
```html
{% extends "base.html" %}
{% block content %}
<header class="group-head">
  <h1>{{ group.title }}</h1>
  <button id="recalc-all" type="button">↻ Tout recalculer</button>
</header>
<div class="blocks">
  {% for block in group.blocks %}
  {% set url = "/groups/" ~ group.id ~ "/blocks/" ~ loop.index0 %}
  <section class="block">
    <div class="block-body" hx-get="{{ url }}" hx-trigger="load, refresh"
         hx-swap="innerHTML">
      {% include "_loading.html" %}
    </div>
  </section>
  {% endfor %}
</div>
{% endblock %}
```

`pyminidash/web/templates/_loading.html` :
```html
<div class="loading">Calcul en cours…</div>
```

- [ ] **Step 7: Écrire `pyminidash/web/static/app.css`**

```css
* { box-sizing: border-box; }
body {
  margin: 0; display: flex; min-height: 100vh;
  font: 14px/1.5 system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
  color: #e7e7e7; background: #141414;
}
.sidebar {
  width: 210px; flex: none; background: #1b1b1b;
  border-right: 1px solid #333; padding: 14px 0;
}
.sidebar .brand { font-weight: 700; padding: 0 16px 12px; }
.sidebar ul { list-style: none; margin: 0; padding: 0; }
.sidebar a {
  display: block; padding: 8px 16px; color: #cfcfcf; text-decoration: none;
}
.sidebar a:hover { background: #262626; }
.sidebar a.active { background: #3b82f6; color: #fff; font-weight: 600; }
.content { flex: 1; padding: 18px 22px; min-width: 0; }
.group-head { display: flex; align-items: center; justify-content: space-between; }
.group-head h1 { font-size: 20px; margin: 0; }
button {
  background: #2b2b2b; color: #e7e7e7; border: 1px solid #444;
  border-radius: 6px; padding: 4px 10px; cursor: pointer;
}
button:hover { background: #363636; }
.block { border: 1px solid #333; border-radius: 8px; margin-top: 14px; }
.block-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 8px 12px; border-bottom: 1px solid #333;
}
.block-head .meta { color: #9a9a9a; font-size: 12px; margin-left: 8px; }
.loading, .empty, .block-error { padding: 12px; color: #9a9a9a; }
.block-error { color: #fca5a5; }
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; }
th, td { text-align: left; padding: 6px 12px; border-bottom: 1px solid #2a2a2a; }
th { background: #1f1f1f; }
.card-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 12px; padding: 12px;
}
.card { border: 1px solid #333; border-radius: 8px; padding: 10px 12px; }
.card-top { display: flex; align-items: center; justify-content: space-between; }
.card-fields { margin: 6px 0 0; }
.card-fields > div { display: flex; justify-content: space-between; gap: 12px; }
.card-fields dt { color: #9a9a9a; margin: 0; }
.card-fields dd { margin: 0; }
.card-toggle { margin-top: 8px; font-size: 12px; }
.status::before { content: ""; }
.status-ok { color: #22c55e; }
.status-warn { color: #f59e0b; }
.status-error { color: #ef4444; }
.status-neutral { color: #9a9a9a; }
```

- [ ] **Step 8: Écrire `pyminidash/web/static/app.js`**

```javascript
document.addEventListener("click", (event) => {
  const target = event.target;

  if (target.id === "recalc-all") {
    document.querySelectorAll(".block-body").forEach((el) => {
      window.htmx.trigger(el, "refresh");
    });
    return;
  }

  if (target.classList.contains("card-toggle")) {
    const card = target.closest(".card");
    const more = card.querySelector(".more");
    if (!more) return;
    const hiddenNow = more.hasAttribute("hidden");
    if (hiddenNow) {
      more.removeAttribute("hidden");
      target.textContent = "afficher moins";
    } else {
      more.setAttribute("hidden", "");
      target.textContent = `afficher plus (${target.dataset.count})`;
    }
  }
});
```

- [ ] **Step 9: Lancer le test, vérifier le succès**

Run: `uv run pytest tests/test_routes_pages.py -v`
Expected: PASS (4 tests). Si `test_root_redirects_to_default_group` renvoie 200 (redirection suivie), c'est que `follow_redirects=False` manque — le garder.

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -m "Ajoute l'app FastAPI, la page d'un groupe et les assets statiques"
```

---

## Task 8: Fragment d'un bloc + templates table / cards / erreur

**Files:**
- Modify: `pyminidash/web/routes.py`
- Create: `pyminidash/web/templates/_field.html`, `_block_head.html`, `_table.html`, `_cards.html`, `_error.html`
- Create: `tests/test_routes_fragment.py`

**Interfaces:**
- Consumes: `pyminidash.runner` (`run_block`, `BlockOk`, `BlockError`), `pyminidash.web.render` (`to_table`, `to_cards`), `_get_group` (Task 7).
- Produces:
  - `GET /groups/{group_id}/blocks/{index}` (async) → fragment HTML :
    - groupe absent → 404 ; `index` hors `[0, len(blocks)-1]` → 404
    - `await run_block(block)` :
      - `BlockError` → `_error.html` (contexte `error`, `block`, `url`)
      - `BlockOk` + `group.type == "table"` → `_table.html` (contexte `table = to_table(records)` ou `None` si vide, `computed_at`, `block`, `url`)
      - `BlockOk` + `group.type == "cards"` → `_cards.html` (contexte `cards = to_cards(records)`, `computed_at`, `block`, `url`)
    - `url` passé au template = `f"/groups/{group_id}/blocks/{index}"` (utilisé par le bouton ↻ du bloc)

- [ ] **Step 1: Écrire le test qui échoue** — `tests/test_routes_fragment.py`

```python
import pytest
from fastapi.testclient import TestClient

from pyminidash.config import Config
from pyminidash.web.app import create_app


@pytest.fixture
def client(dummy_providers):
    config = Config.model_validate({
        "groups": [
            {"id": "sys", "title": "Système", "type": "table",
             "blocks": [{"provider": "dummy_rows", "params": {"n": 2}},
                        {"provider": "dummy_empty"},
                        {"provider": "dummy_boom"}]},
            {"id": "apis", "title": "APIs", "type": "cards",
             "blocks": [{"provider": "dummy_rows", "params": {"n": 1}}]},
        ],
    })
    return TestClient(create_app(config))


def test_table_fragment_has_headers_and_rows(client):
    html = client.get("/groups/sys/blocks/0").text
    assert "<table" in html
    assert "<th>Nom</th>" in html
    assert html.count("<tr>") == 3           # 1 en-tête + 2 lignes
    assert 'hx-get="/groups/sys/blocks/0"' in html   # bouton ↻ du bloc


def test_empty_table_fragment_shows_no_data(client):
    html = client.get("/groups/sys/blocks/1").text
    assert "aucune donnée" in html
    assert "<table" not in html


def test_provider_exception_renders_error_frame(client):
    html = client.get("/groups/sys/blocks/2").text
    assert "Erreur" in html
    assert "RuntimeError" in html


def test_cards_fragment_splits_summary_and_hidden(client):
    html = client.get("/groups/apis/blocks/0").text
    assert "item0" in html                    # titre de la card
    assert "afficher plus (1)" in html        # 1 champ caché (detail)
    assert "ligne cachée 0" in html           # présent dans le HTML, masqué en CSS
    assert 'class="card-fields more"' in html


def test_out_of_range_index_is_404(client):
    assert client.get("/groups/sys/blocks/9").status_code == 404
    assert client.get("/groups/sys/blocks/-1").status_code == 404


def test_unknown_group_fragment_is_404(client):
    assert client.get("/groups/nope/blocks/0").status_code == 404
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `uv run pytest tests/test_routes_fragment.py -v`
Expected: FAIL — 404 sur toutes les routes de fragment (route pas encore définie) → assertions de contenu échouent.

- [ ] **Step 3: Ajouter la route à `pyminidash/web/routes.py`**

Ajouter les imports en tête :
```python
from pyminidash.runner import BlockError, run_block
from pyminidash.web.render import to_cards, to_table
```

Ajouter la route en fin de fichier :
```python
@router.get("/groups/{group_id}/blocks/{index}", response_class=HTMLResponse)
async def block_fragment(request: Request, group_id: str, index: int) -> HTMLResponse:
    group = _get_group(request, group_id)
    if index < 0 or index >= len(group.blocks):
        raise HTTPException(status_code=404, detail="bloc inexistant")
    block = group.blocks[index]
    url = f"/groups/{group_id}/blocks/{index}"
    templates = request.app.state.templates

    result = await run_block(block)
    context = {
        "config": request.app.state.config,
        "group": group,
        "block": block,
        "url": url,
        "active_group_id": group_id,
        "computed_at": None,
    }

    if isinstance(result, BlockError):
        context["error"] = result
        return templates.TemplateResponse(
            request=request, name="_error.html", context=context
        )

    context["computed_at"] = result.computed_at
    if group.type == "table":
        context["table"] = to_table(result.records) if result.records else None
        return templates.TemplateResponse(
            request=request, name="_table.html", context=context
        )

    context["cards"] = to_cards(result.records)
    return templates.TemplateResponse(
        request=request, name="_cards.html", context=context
    )
```

- [ ] **Step 4: Écrire les templates de fragment**

`pyminidash/web/templates/_field.html` :
```html
{% macro field(f) -%}
{%- if f.type.value == "status" -%}
  <span class="status status-{{ f.level.value if f.level else 'neutral' }}">● {{ f.value }}</span>
{%- elif f.type.value == "link" -%}
  <a href="{{ f.url }}" target="_blank" rel="noopener">{{ f.value }}</a>
{%- else -%}
  {{ f | format_field }}
{%- endif -%}
{%- endmacro %}
```

`pyminidash/web/templates/_block_head.html` :
```html
<div class="block-head">
  <div>
    <strong>{{ block.title }}</strong>
    <span class="meta">provider: {{ block.provider }}{% if computed_at %} · {{ computed_at.strftime('%H:%M:%S') }}{% endif %}</span>
  </div>
  <button type="button" class="recalc-one" title="Recalculer ce bloc"
          hx-get="{{ url }}" hx-target="closest .block-body" hx-swap="innerHTML">↻</button>
</div>
```

`pyminidash/web/templates/_table.html` :
```html
{% import "_field.html" as fld %}
{% include "_block_head.html" %}
{% if table %}
<div class="table-wrap">
  <table>
    <thead>
      <tr>{% for c in table.columns %}<th>{{ c.label }}</th>{% endfor %}</tr>
    </thead>
    <tbody>
      {% for row in table.rows %}
      <tr>{% for f in row %}<td>{{ fld.field(f) }}</td>{% endfor %}</tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% else %}
<p class="empty">aucune donnée</p>
{% endif %}
```

`pyminidash/web/templates/_cards.html` :
```html
{% import "_field.html" as fld %}
{% include "_block_head.html" %}
{% if cards %}
<div class="card-grid">
  {% for c in cards %}
  <article class="card">
    <div class="card-top">
      <strong>{{ c.title or "" }}</strong>
      {% if c.badge %}{{ fld.field(c.badge) }}{% endif %}
    </div>
    <dl class="card-fields">
      {% for f in c.summary_fields %}
      <div><dt>{{ f.label }}</dt><dd>{{ fld.field(f) }}</dd></div>
      {% endfor %}
    </dl>
    {% if c.hidden_fields %}
    <dl class="card-fields more" hidden>
      {% for f in c.hidden_fields %}
      <div><dt>{{ f.label }}</dt><dd>{{ fld.field(f) }}</dd></div>
      {% endfor %}
    </dl>
    <button type="button" class="card-toggle" data-count="{{ c.hidden_fields | length }}">afficher plus ({{ c.hidden_fields | length }})</button>
    {% endif %}
  </article>
  {% endfor %}
</div>
{% else %}
<p class="empty">aucune donnée</p>
{% endif %}
```

`pyminidash/web/templates/_error.html` :
```html
{% include "_block_head.html" %}
<div class="block-error">
  <p><strong>Erreur</strong> — {{ error.message }}</p>
  <p class="meta">{{ error.kind }}</p>
</div>
```

- [ ] **Step 5: Lancer le test, vérifier le succès**

Run: `uv run pytest tests/test_routes_fragment.py -v`
Expected: PASS (6 tests)

- [ ] **Step 6: Lancer toute la suite**

Run: `uv run pytest -v`
Expected: PASS (tous les tests des tâches 1 à 8)

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "Ajoute le fragment d'un bloc et les templates table/cards/erreur"
```

---

## Task 9: Providers système (`disk_usage`, `top_processes`)

**Files:**
- Create: `pyminidash/providers/__init__.py`
- Create: `pyminidash/providers/system.py`
- Create: `tests/test_providers_system.py`

**Interfaces:**
- Consumes: `pyminidash.registry` (`@provider`), `pyminidash.models` (helpers).
- Produces:
  - `pyminidash/providers/__init__.py` : `from pyminidash.providers import system, http  # noqa: F401` — l'import du package enregistre tous les providers intégrés. **À ce stade `http` n'existe pas encore** : n'importer que `system` ; la Task 10 ajoutera `http`.
  - `pyminidash/providers/system.py` :
    - `_level_for_percent(pct: float) -> StatusLevel` : `>= 90` → `ERROR`, `>= 75` → `WARN`, sinon `OK`
    - `disk_usage(paths: list[str]) -> list[Record]` — un record par chemin. Champs (ordre) : `mount` (`title`), `percent` (`status`, `role=BADGE`, `summary=True`, `value=f"{pct} %"`, `level=_level_for_percent`), `free` (`bytes_`, `summary=True`), `total` (`bytes_`), `used` (`bytes_`). Enregistré `@provider("disk_usage")`.
    - `_processes_to_records(samples: list[dict], limit: int) -> list[Record]` — trie `samples` par `cpu` décroissant, tronque à `limit`, un record par process. Champs : `name` (`title`), `cpu` (`number`, `role=BADGE`, `summary=True`), `memory` (`bytes_`, `summary=True`), `pid` (`number`), `username` (`text`), `status` (`text`). Chaque `sample` = `{"pid","name","username","status","cpu","memory"}`.
    - `top_processes(limit: int = 10) -> list[Record]` — échantillonne via `psutil` puis délègue à `_processes_to_records`. Enregistré `@provider("top_processes")`.

- [ ] **Step 1: Écrire le test qui échoue** — `tests/test_providers_system.py`

```python
from pyminidash.models import FieldRole, FieldType, StatusLevel
from pyminidash.providers.system import (
    _level_for_percent, _processes_to_records, disk_usage, top_processes,
)


def test_level_for_percent_thresholds():
    assert _level_for_percent(10) is StatusLevel.OK
    assert _level_for_percent(80) is StatusLevel.WARN
    assert _level_for_percent(95) is StatusLevel.ERROR


def test_disk_usage_on_tmp_path(tmp_path):
    records = disk_usage([str(tmp_path)])
    assert len(records) == 1
    assert records[0].keys() == ("mount", "percent", "free", "total", "used")
    mount, percent, *_ = records[0].fields
    assert mount.role is FieldRole.TITLE
    assert percent.type is FieldType.STATUS
    assert percent.role is FieldRole.BADGE
    assert percent.summary is True


def test_processes_to_records_sorts_and_truncates():
    samples = [
        {"pid": 1, "name": "a", "username": "u", "status": "running", "cpu": 5.0, "memory": 100},
        {"pid": 2, "name": "b", "username": "u", "status": "running", "cpu": 40.0, "memory": 200},
        {"pid": 3, "name": "c", "username": "u", "status": "running", "cpu": 12.0, "memory": 300},
    ]
    records = _processes_to_records(samples, limit=2)
    assert len(records) == 2
    assert [r.fields[0].value for r in records] == ["b", "c"]  # tri CPU desc
    assert records[0].keys() == ("name", "cpu", "memory", "pid", "username", "status")


def test_top_processes_smoke():
    records = top_processes(limit=3)
    assert 0 < len(records) <= 3
    keys = records[0].keys()
    assert all(r.keys() == keys for r in records)
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `uv run pytest tests/test_providers_system.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pyminidash.providers'`

- [ ] **Step 3: Écrire `pyminidash/providers/__init__.py`**

```python
"""Import des modules de providers intégrés → enregistrement au chargement."""
from pyminidash.providers import system  # noqa: F401
```

- [ ] **Step 4: Écrire `pyminidash/providers/system.py`**

```python
"""Providers système : espace disque et processus les plus gourmands."""
from __future__ import annotations

import shutil
import time

import psutil

from pyminidash.models import (
    Record, StatusLevel, bytes_, number, status, text, title, FieldRole,
)
from pyminidash.registry import provider


def _level_for_percent(pct: float) -> StatusLevel:
    if pct >= 90:
        return StatusLevel.ERROR
    if pct >= 75:
        return StatusLevel.WARN
    return StatusLevel.OK


@provider("disk_usage")
def disk_usage(paths: list[str]) -> list[Record]:
    records: list[Record] = []
    for path in paths:
        u = shutil.disk_usage(path)
        pct = round(u.used / u.total * 100) if u.total else 0
        records.append(Record(
            title("mount", "Disque", path),
            status("percent", "%", f"{pct} %", level=_level_for_percent(pct),
                   summary=True),
            bytes_("free", "Libre", u.free, summary=True),
            bytes_("total", "Total", u.total),
            bytes_("used", "Utilisé", u.used),
        ))
    return records


def _processes_to_records(samples: list[dict], limit: int) -> list[Record]:
    ordered = sorted(samples, key=lambda s: s["cpu"], reverse=True)[:limit]
    return [
        Record(
            title("name", "Processus", s["name"]),
            number("cpu", "CPU %", round(s["cpu"], 1), role=FieldRole.BADGE,
                   summary=True),
            bytes_("memory", "Mémoire", s["memory"], summary=True),
            number("pid", "PID", s["pid"]),
            text("username", "Utilisateur", s["username"]),
            text("status", "État", s["status"]),
        )
        for s in ordered
    ]


@provider("top_processes")
def top_processes(limit: int = 10) -> list[Record]:
    procs = list(psutil.process_iter(["pid", "name", "username", "status"]))
    for p in procs:
        try:
            p.cpu_percent(None)  # 1re mesure (renvoie 0.0)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    time.sleep(0.1)

    samples: list[dict] = []
    for p in procs:
        try:
            info = p.info
            samples.append({
                "pid": info["pid"],
                "name": info["name"] or "?",
                "username": info["username"] or "?",
                "status": info["status"] or "?",
                "cpu": p.cpu_percent(None),
                "memory": p.memory_info().rss,
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return _processes_to_records(samples, limit)
```

- [ ] **Step 5: Lancer le test, vérifier le succès**

Run: `uv run pytest tests/test_providers_system.py -v`
Expected: PASS (4 tests). `test_top_processes_smoke` peut être lent (~0,1 s) — normal.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "Ajoute les providers système (disk_usage, top_processes)"
```

---

## Task 10: Providers HTTP (`http_check`, `http_json`)

**Files:**
- Modify: `pyminidash/providers/__init__.py`
- Create: `pyminidash/providers/http.py`
- Create: `tests/test_providers_http.py`

**Interfaces:**
- Consumes: `pyminidash.registry` (`@provider`), `pyminidash.models` (helpers), `httpx`.
- Produces:
  - `pyminidash/providers/__init__.py` : ajouter `from pyminidash.providers import http  # noqa: F401`
  - `pyminidash/providers/http.py` :
    - `_dig(obj, path: str)` — `path == "$"` → `obj` ; sinon suit les segments séparés par `.` (`dict` uniquement) ; renvoie `None` si un segment manque.
    - `_check_level(code: int | None, latency_s: float) -> tuple[str, StatusLevel]` — `code is None` → `("DOWN", ERROR)` ; `code >= 400` → `(f"HTTP {code}", ERROR)` ; `latency_s >= 0.5` → `("SLOW", WARN)` ; sinon `("UP", OK)`.
    - `http_check(urls: list[str], timeout: float = 5.0) -> list[Record]` — un record par URL. Champs : `host` (`title`, = `urlsplit(url).netloc`), `state` (`status`, `role=BADGE`, `summary=True`), `code` (`number`, `summary=True`, `None` si pas de réponse), `latency` (`duration`, `summary=True`, en secondes), `url` (`link`, `url=url`), `error` (`text`, message d'exception ou `""`), `checked_at` (`datetime_`, `datetime.now()`). Attrape `httpx.RequestError` → `code=None`, `error=str(exc)`. Enregistré `@provider("http_check")`.
    - `http_json(url: str, rows_path: str, columns: list[str], timeout: float = 5.0) -> list[Record]` — `httpx.get(url, timeout=timeout)`, `resp.raise_for_status()` (une 4xx/5xx **remonte** → bloc en erreur, conforme à la spec), `data = resp.json()`, `rows = _dig(data, rows_path)`. Si `rows` n'est pas une `list` → `ValueError`. Un record par entrée ; un champ `text` par `column` (clé = la chaîne `column`, label = dernier segment, valeur = `_dig(entry, column)`). Enregistré `@provider("http_json")`.

- [ ] **Step 1: Écrire le test qui échoue** — `tests/test_providers_http.py`

```python
import httpx
import pytest
import respx

from pyminidash.models import FieldType, StatusLevel
from pyminidash.providers.http import _check_level, _dig, http_check, http_json


def test_dig():
    assert _dig({"a": {"b": 1}}, "$") == {"a": {"b": 1}}
    assert _dig({"a": {"b": 1}}, "a.b") == 1
    assert _dig({"a": {}}, "a.b.c") is None


def test_check_level():
    assert _check_level(None, 0.1) == ("DOWN", StatusLevel.ERROR)
    assert _check_level(503, 0.1) == ("HTTP 503", StatusLevel.ERROR)
    assert _check_level(200, 0.9) == ("SLOW", StatusLevel.WARN)
    assert _check_level(200, 0.05) == ("UP", StatusLevel.OK)


@respx.mock
def test_http_check_up_and_down():
    respx.get("https://ok.test/").mock(return_value=httpx.Response(200))
    respx.get("https://bad.test/").mock(side_effect=httpx.ConnectError("refused"))

    records = http_check(["https://ok.test/", "https://bad.test/"])
    assert records[0].keys() == (
        "host", "state", "code", "latency", "url", "error", "checked_at"
    )
    assert records[0].fields[1].value == "UP"
    assert records[0].fields[1].type is FieldType.STATUS
    assert records[1].fields[1].value == "DOWN"
    assert "refused" in records[1].fields[5].value


@respx.mock
def test_http_json_extracts_rows_and_columns():
    respx.get("https://api.test/users").mock(return_value=httpx.Response(
        200, json=[
            {"name": "Léa", "company": {"name": "Acme"}},
            {"name": "Sam", "company": {"name": "Globex"}},
        ],
    ))
    records = http_json("https://api.test/users", rows_path="$",
                        columns=["name", "company.name"])
    assert len(records) == 2
    assert records[0].keys() == ("name", "company.name")
    assert records[0].fields[0].value == "Léa"
    assert records[0].fields[1].value == "Acme"
    assert records[0].fields[1].label == "name"


@respx.mock
def test_http_json_raises_on_5xx():
    respx.get("https://api.test/boom").mock(return_value=httpx.Response(500))
    with pytest.raises(httpx.HTTPStatusError):
        http_json("https://api.test/boom", rows_path="$", columns=["x"])


@respx.mock
def test_http_json_raises_when_rows_not_a_list():
    respx.get("https://api.test/obj").mock(return_value=httpx.Response(
        200, json={"not": "a list"}))
    with pytest.raises(ValueError):
        http_json("https://api.test/obj", rows_path="$", columns=["x"])
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `uv run pytest tests/test_providers_http.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pyminidash.providers.http'`

- [ ] **Step 3: Mettre à jour `pyminidash/providers/__init__.py`**

```python
"""Import des modules de providers intégrés → enregistrement au chargement."""
from pyminidash.providers import http, system  # noqa: F401
```

- [ ] **Step 4: Écrire `pyminidash/providers/http.py`**

```python
"""Providers HTTP : contrôle d'endpoints et extraction de tableaux depuis une API JSON."""
from __future__ import annotations

import time
from datetime import datetime
from urllib.parse import urlsplit

import httpx

from pyminidash.models import (
    Record, StatusLevel, datetime_, duration, link, number, status, text, title,
    FieldRole,
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
```

- [ ] **Step 5: Lancer le test, vérifier le succès**

Run: `uv run pytest tests/test_providers_http.py -v`
Expected: PASS (6 tests)

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "Ajoute les providers HTTP (http_check, http_json)"
```

---

## Task 11: Point d'entrée CLI + câblage + config d'exemple + doc

**Files:**
- Create: `pyminidash/__main__.py`
- Modify: `pyminidash/config.py` (import des providers avant validation)
- Create: `config.example.toml`
- Create: `tests/test_main.py`, `tests/test_example_config.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `pyminidash.config` (`load_config`, `ConfigError`), `pyminidash.web.app` (`create_app`), `pyminidash.providers` (effet de bord : enregistrement).
- Produces:
  - `pyminidash/__main__.py` :
    - `build_parser() -> argparse.ArgumentParser` — options : `--config` (défaut `config.toml`, `Path`), `--host` (défaut `127.0.0.1`), `--port` (défaut `8000`, `int`), `--open` (`store_true`)
    - `main(argv: list[str] | None = None) -> None` — parse, `import pyminidash.providers`, `load_config` (sur `ConfigError` : message sur `stderr` + `raise SystemExit(2)`), `create_app`, si `--open` planifie `webbrowser.open` via `threading.Timer(1.0, ...)`, puis `uvicorn.run(app, host=..., port=...)`
  - `pyminidash/config.py` : ajouter en tête `import pyminidash.providers  # noqa: F401 — enregistre les providers intégrés avant toute validation`. (Retire la dépendance des tests à `dummy_providers` pour les providers réels, mais les tests existants continuent de fonctionner : ils utilisent `Config.model_validate` avec des providers factices, toujours valides.)
  - `config.example.toml` : config d'exemple complète et valide (voir Step 3).

- [ ] **Step 1: Écrire les tests qui échouent** — `tests/test_main.py`

```python
import pytest

from pyminidash.__main__ import build_parser, main


def test_parser_defaults():
    args = build_parser().parse_args([])
    assert str(args.config) == "config.toml"
    assert args.host == "127.0.0.1"
    assert args.port == 8000
    assert args.open is False


def test_main_exits_2_on_bad_config(tmp_path, capsys):
    bad = tmp_path / "c.toml"
    bad.write_text('[[groups]]\nid="g"\ntitle="G"\ntype="table"\n'
                   '  [[groups.blocks]]\n  provider="nope"\n', encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        main(["--config", str(bad)])
    assert exc.value.code == 2
    assert "nope" in capsys.readouterr().err


def test_main_starts_server(tmp_path, monkeypatch):
    started = {}

    def fake_run(app, host, port):
        started["host"] = host
        started["port"] = port

    monkeypatch.setattr("pyminidash.__main__.uvicorn.run", fake_run)
    cfg = tmp_path / "c.toml"
    cfg.write_text(
        '[[groups]]\nid="sys"\ntitle="Système"\ntype="table"\n'
        '  [[groups.blocks]]\n  provider="disk_usage"\n'
        '  params = { paths = ["."] }\n',
        encoding="utf-8",
    )
    main(["--config", str(cfg), "--port", "9123"])
    assert started == {"host": "127.0.0.1", "port": 9123}
```

`tests/test_example_config.py` :
```python
from pathlib import Path

import pyminidash.providers  # noqa: F401 — enregistre les providers réels
from pyminidash.config import load_config

EXAMPLE = Path(__file__).resolve().parent.parent / "config.example.toml"


def test_example_config_is_valid():
    cfg = load_config(EXAMPLE)
    assert cfg.app.default_group
    assert len(cfg.groups) >= 2
    # tous les providers référencés existent → pas d'exception levée
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `uv run pytest tests/test_main.py tests/test_example_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pyminidash.__main__'` et fichier `config.example.toml` absent.

- [ ] **Step 3: Écrire `config.example.toml`**

```toml
# Exemple de configuration pyminidash. Copier en config.toml et adapter.

[app]
title = "Mon dashboard"
default_group = "system"

[[groups]]
id = "system"
title = "Système"
type = "table"

  [[groups.blocks]]
  title = "Espace disque"
  provider = "disk_usage"
  params = { paths = ["."] }

  [[groups.blocks]]
  title = "Processus gourmands"
  provider = "top_processes"
  params = { limit = 10 }

[[groups]]
id = "apis"
title = "Monitoring APIs"
type = "cards"

  [[groups.blocks]]
  title = "Endpoints"
  provider = "http_check"
  params = { urls = [
    "https://jsonplaceholder.typicode.com/posts/1",
    "https://jsonplaceholder.typicode.com/this-endpoint-does-not-exist",
  ] }

[[groups]]
id = "data"
title = "Données"
type = "table"

  [[groups.blocks]]
  title = "Utilisateurs (jsonplaceholder)"
  provider = "http_json"
  params = { url = "https://jsonplaceholder.typicode.com/users", rows_path = "$", columns = ["name", "email", "company.name"] }
```

- [ ] **Step 4: Écrire `pyminidash/__main__.py`**

```python
"""Point d'entrée : pyminidash --config config.toml [--port 8000] [--open]."""
from __future__ import annotations

import argparse
import sys
import threading
import webbrowser
from pathlib import Path

import uvicorn

import pyminidash.providers  # noqa: F401 — enregistre les providers intégrés
from pyminidash.config import ConfigError, load_config
from pyminidash.web.app import create_app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pyminidash")
    parser.add_argument("--config", type=Path, default=Path("config.toml"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--open", action="store_true",
                        help="ouvrir le navigateur au démarrage")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"Erreur de configuration : {exc}", file=sys.stderr)
        raise SystemExit(2)

    app = create_app(config)

    if args.open:
        url = f"http://{args.host}:{args.port}/"
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Ajouter l'import des providers dans `pyminidash/config.py`**

En tête du fichier, après les imports stdlib/pydantic et **avant** `from pyminidash.registry import ...`, ajouter :
```python
import pyminidash.providers  # noqa: F401 — enregistre les providers intégrés avant validation
```

- [ ] **Step 6: Lancer les tests, vérifier le succès**

Run: `uv run pytest tests/test_main.py tests/test_example_config.py -v`
Expected: PASS (4 tests)

- [ ] **Step 7: Lancer toute la suite**

Run: `uv run pytest -v`
Expected: PASS (toutes les tâches). Aucun test ne doit dépendre du réseau (les providers HTTP sont mockés ; `test_example_config` ne fait que valider, sans appeler les providers).

- [ ] **Step 8: Smoke test manuel**

Run:
```bash
uv run pyminidash --config config.example.toml --port 8765
```
Ouvrir `http://127.0.0.1:8765/` : la sidebar liste Système / Monitoring APIs / Données ; le groupe Système calcule ses deux blocs (disque + processus) ; tester ↻ sur un bloc, « Tout recalculer », et « afficher plus » sur une card du groupe APIs. `Ctrl+C` pour arrêter.

- [ ] **Step 9: Mettre à jour `README.md`**

```markdown
# pyminidash

Mini-dashboard web local. Affiche des groupes définis dans un fichier TOML ;
chaque groupe rend des tableaux ou des cards produits par des *providers* Python
intégrés (espace disque, processus, contrôle d'endpoints HTTP, extraction JSON).

## Installation

```bash
uv sync
```

## Utilisation

```bash
cp config.example.toml config.toml   # puis adapter
uv run pyminidash --config config.toml --port 8000 --open
```

## Providers intégrés

| Provider | Usage | Paramètres |
|---|---|---|
| `disk_usage` | table / cards | `paths: list[str]` |
| `top_processes` | table / cards | `limit: int = 10` |
| `http_check` | table / cards | `urls: list[str]`, `timeout: float = 5` |
| `http_json` | table | `url: str`, `rows_path: str`, `columns: list[str]`, `timeout: float = 5` |

Ajouter un provider : écrire une fonction décorée `@provider("nom")` dans
`pyminidash/providers/` renvoyant une `list[Record]`, et l'importer depuis
`pyminidash/providers/__init__.py`.

## Développement

```bash
uv run pytest
```

Design : `docs/superpowers/specs/2026-08-29-pyminidash-design.md`
```

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -m "Ajoute le point d'entrée CLI, la config d'exemple et la doc"
```

---

## Self-Review

**Spec coverage :**

| Section de la spec | Tâche(s) |
|---|---|
| §2 Provider + `@provider` + exécution en thread + polyvalence | 3, 5, 9, 10 |
| §2 Record / Field / types / helpers | 1 |
| §2 Règles records (homogènes, liste vide) | 5 (validation), 8 (« aucune donnée ») |
| §3 Rendu table (ordre colonnes, formats) | 2, 6, 8 |
| §3 Rendu cards (title/badge/summary/hidden, repli client, retour replié) | 6, 8 (`app.js` Task 7) |
| §4 Config TOML + schéma + defaults | 4 |
| §4 Validation au démarrage (tous les cas) | 4, 11 (exit code) |
| §4 CLI `--config` | 11 |
| §5 Endpoints `/`, `/groups/{id}`, `/groups/{id}/blocks/{n}` | 7, 8 |
| §5 Flux : auto-chargement, ↻ par bloc, « Tout recalculer » limité au groupe | 7 (placeholders, bouton, JS), 8 (fragment, ↻) |
| §5 Templates listés | 7, 8 |
| §5 Pas de persistance | respecté (aucun cache écrit) |
| §5 Lancement Uvicorn + `--open` | 11 |
| §6 Erreurs au démarrage | 4, 11 |
| §6 Erreurs d'exécution d'un bloc (exception, timeout, forme invalide, vide) | 5, 8 |
| §6 Réseau : `http_check` traduit en statut, `http_json` remonte les 5xx | 10 |
| §6 Logs des exceptions de providers | 5 |
| §7 `disk_usage`, `top_processes`, `http_check`, `http_json` + champs | 9, 10 |
| §8 Structure du projet | toutes |
| §8 Dépendances | 1 |
| §9 Approche de test par couche | chaque tâche |

Pas de trou identifié.

**Placeholder scan :** aucun `TODO`/`TBD`/« gérer les cas limites » dans les steps ; tout step de code porte un bloc de code complet.

**Type consistency :** vérifié — `Record(*fields)` (varargs) partout ; `BlockOk.records` / `BlockOk.computed_at` cohérents entre Task 5, 8 ; `to_table`/`to_cards` signatures identiques entre Task 6 et leur usage Task 8 ; `_get_group` défini Task 7, réutilisé Task 8 ; `format_field` = filtre Jinja de `format_value` (Task 7 le déclare, Task 8 l'utilise dans `_field.html`) ; helpers `status`/`number` acceptent `role=` (défini Task 1, utilisé Task 9). `_processes_to_records` clé d'ordre `s["cpu"]` cohérente entre le provider et le test.

**Note d'implémentation transverse :** `Field` est `@dataclass(frozen=True)` — les providers ne mutent jamais un `Field`, ils en construisent. `GroupConfig`/`BlockConfig` sont mutés une seule fois dans le `model_validator` (résolution des defaults `title`, `default_group`) : ne pas activer `frozen`/`validate_assignment` sur ces modèles.
