# pyminidash — Plan A : fondation auth + providers Jira

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter à pyminidash le sous-système de connexions authentifiées (secrets, objet `Connection`, injection dans le runner) et les trois providers Jira, livrant Jira on-premise de bout en bout.

**Architecture:** `secrets.toml` (plat, git-ignoré) fournit les PAT ; `[connections.*]` dans `config.toml` déclare des connexions réutilisables ; `build_connections()` résout `ConnectionConfig` + secrets → objets `Connection` gelés au démarrage ; le runner injecte le `Connection` résolu dans tout provider dont la signature a un paramètre `connection` ; les providers Jira appellent l'API via un helper `get_json` qui traduit les erreurs HTTP en exceptions `ProviderError` à message propre.

**Tech Stack:** Python 3.13, `uv`, FastAPI, Pydantic v2, `httpx`, `tomllib` (stdlib). Tests : `pytest`, `pytest-asyncio`, `respx`. Aucune nouvelle dépendance.

**Spec:** `docs/superpowers/specs/2026-08-29-pyminidash-atlassian-providers-design.md` (ce plan couvre §2, §3, §4, la partie de §5 utilisée par Jira, §6, §9, §11 partiel, §12 partiel ; §7 Bitbucket et §8 Bamboo sont dans le Plan B).

## Global Constraints

- Python `>=3.13`. `python` seul n'est PAS sur le PATH — toujours `uv run` (`uv run pytest`, `uv run python`).
- Plateforme de dev : Windows 11 ; tests cross-platform (`tmp_path`, pas de chemin en dur ; garder les checks POSIX-only derrière `os.name == "posix"`).
- Auth : PAT uniquement, en-tête `Authorization: Bearer <token>`. Le modèle `ConnectionConfig.auth` accepte `Literal["bearer"]` et rien d'autre pour l'instant.
- **Divulgation** : le contenu d'un token n'apparaît JAMAIS dans un log, un message d'exception, une réponse HTTP ou un rendu. Les messages référencent la *clé de secret* (`"jira"`) ou le *nom de connexion*, jamais la valeur. L'en-tête `Authorization` n'est jamais loggé.
- `secrets.toml` : table TOML plate `clé = "valeur"`, git-ignoré. Emplacement par défaut : `config_path.parent / "secrets.toml"` ; surchargé par `--secrets`.
- Un provider **exige** une connexion ssi sa signature a un paramètre `connection` **sans valeur par défaut**. Le runner injecte `connection=<Connection résolu>` ssi la signature a un paramètre `connection` **et** `block.connection is not None`.
- Rétrocompatibilité : `http_check`, `http_json`, `disk_usage`, `top_processes` n'ont pas de paramètre `connection` → comportement inchangé. `Config.connections` défaut `{}` ; `BlockConfig.connection` défaut `None` → les configs existantes restent valides.
- Erreurs au démarrage → `ConfigError`, le serveur ne démarre pas (stderr + `SystemExit(2)`). Erreurs à l'exécution d'un bloc → `BlockError` rendu via `_error.html`.
- Langue de l'UI et des messages : français.
- TDD strict : test qui échoue → implémentation minimale → test qui passe → commit. Suite complète verte avant chaque commit. Sortie de test propre (le seul warning admis est le `StarletteDeprecationWarning` préexistant de `fastapi/testclient.py`).
- Providers Jira : appels réels interdits en test — tout est mocké avec `respx`.

---

## File Structure

| Fichier | Responsabilité | Tâche |
|---|---|---|
| `pyminidash/errors.py` | *(créé)* `ProviderError` — base des exceptions de provider à message propre | 1 |
| `pyminidash/secrets.py` | *(créé)* `load_secrets`, `SecretsError` | 1 |
| `pyminidash/config.py` | *(modifié)* `ConnectionConfig`, `Config.connections`, `BlockConfig.connection`, validation des connexions dans `_cross_checks` | 2 |
| `pyminidash/registry.py` | *(modifié)* `validate_params` gagne `injected` | 2 |
| `pyminidash/connection.py` | *(créé)* `Connection` (dataclass gelée), `build_connections` | 3 |
| `pyminidash/runner.py` | *(modifié)* `run_block(block, connections=None)` + injection + `except ProviderError` | 4 |
| `pyminidash/providers/_atlassian.py` | *(créé)* `get_json`, taxonomie d'erreurs (`AuthError`/`ConnError`/`NotFoundError`/`ApiError`), `count_record` | 5 |
| `pyminidash/providers/jira.py` | *(créé)* `jira_jql` + mapping des champs + `_search` ; puis `jira_jql_count`, `jira_my_issues` | 6, 7 |
| `pyminidash/providers/__init__.py` | *(modifié)* importe `jira` | 6 |
| `pyminidash/web/app.py` | *(modifié)* `create_app(config, connections=None)`, `app.state.connections` | 8 |
| `pyminidash/web/routes.py` | *(modifié)* `run_block(block, request.app.state.connections)` | 8 |
| `pyminidash/__main__.py` | *(modifié)* `--secrets`, `load_secrets`, `build_connections`, câblage | 8 |
| `secrets.example.toml` | *(créé)* modèle (clés vides), committé | 8 |
| `.gitignore` | *(modifié)* `secrets.toml` | 8 |
| `config.example.toml` | *(modifié)* `[connections.*]` + groupe « Mon activité » (bloc Jira) | 9 |
| `README.md` | *(modifié)* section « Connexions et secrets » | 9 |
| `tests/test_secrets.py` | tests `load_secrets` | 1 |
| `tests/test_config_connections.py` | tests validation connexions | 2 |
| `tests/test_connection.py` | tests `Connection` / `build_connections` | 3 |
| `tests/test_runner_injection.py` | tests injection | 4 |
| `tests/test_atlassian_helpers.py` | tests `get_json` / `count_record` | 5 |
| `tests/test_providers_jira.py` | tests des 3 providers Jira | 6, 7 |
| `tests/test_integration_atlassian.py` | test bout-en-bout Jira via route | 9 |

---

## Task 1: `errors.py` + `secrets.py`

**Files:**
- Create: `pyminidash/errors.py`, `pyminidash/secrets.py`
- Create: `tests/test_secrets.py`

**Interfaces:**
- Consumes: rien (nouveaux modules feuilles).
- Produces:
  - `pyminidash/errors.py` : `class ProviderError(Exception)` — exception dont le `str()` est un message utilisateur déjà propre (le runner l'affichera sans préfixer le type). Rien d'autre.
  - `pyminidash/secrets.py` :
    - `class SecretsError(Exception)` — fichier secrets mal formé.
    - `load_secrets(path: str | Path) -> dict[str, str]` :
      - fichier absent → `{}` (pas d'erreur).
      - `tomllib.TOMLDecodeError` → `SecretsError(f"secrets TOML invalide dans {p} : {exc}")`.
      - une valeur non-`str` → `SecretsError(f"secrets : la clé '{key}' n'est pas une chaîne (obtenu {type})")`.
      - sinon `dict[str, str]`.
      - sur `os.name == "posix"` uniquement : si `path.stat().st_mode & 0o077`, `logging.getLogger("pyminidash.secrets").warning(...)` (non bloquant).

- [ ] **Step 1: Écrire `pyminidash/errors.py`**

```python
"""Exceptions transverses."""
from __future__ import annotations


class ProviderError(Exception):
    """Erreur d'un provider dont le message est déjà destiné à l'utilisateur.

    Le runner affiche `str(exc)` tel quel, sans le préfixe `TypeName:` qu'il
    applique aux exceptions inattendues.
    """
```

- [ ] **Step 2: Écrire le test qui échoue** — `tests/test_secrets.py`

```python
import sys

import pytest

from pyminidash.secrets import SecretsError, load_secrets


def test_missing_file_returns_empty(tmp_path):
    assert load_secrets(tmp_path / "absent.toml") == {}


def test_reads_flat_table(tmp_path):
    p = tmp_path / "secrets.toml"
    p.write_text('jira = "abc"\nbitbucket = "def"\n', encoding="utf-8")
    assert load_secrets(p) == {"jira": "abc", "bitbucket": "def"}


def test_invalid_toml_raises(tmp_path):
    p = tmp_path / "secrets.toml"
    p.write_text("this is = = broken", encoding="utf-8")
    with pytest.raises(SecretsError, match="TOML"):
        load_secrets(p)


def test_non_string_value_raises(tmp_path):
    p = tmp_path / "secrets.toml"
    p.write_text('jira = 123\n', encoding="utf-8")
    with pytest.raises(SecretsError, match="jira"):
        load_secrets(p)


def test_nested_table_value_raises(tmp_path):
    p = tmp_path / "secrets.toml"
    p.write_text('[jira]\ntoken = "x"\n', encoding="utf-8")
    with pytest.raises(SecretsError, match="jira"):
        load_secrets(p)


@pytest.mark.skipif(sys.platform == "win32", reason="permissions POSIX")
def test_world_readable_warns(tmp_path, caplog):
    import logging
    p = tmp_path / "secrets.toml"
    p.write_text('jira = "abc"\n', encoding="utf-8")
    p.chmod(0o644)
    with caplog.at_level(logging.WARNING, logger="pyminidash.secrets"):
        load_secrets(p)
    assert any("chmod" in r.message or "lisible" in r.message for r in caplog.records)
```

- [ ] **Step 3: Lancer, vérifier l'échec**

Run: `uv run pytest tests/test_secrets.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pyminidash.secrets'`

- [ ] **Step 4: Écrire `pyminidash/secrets.py`**

```python
"""Chargement du fichier de secrets (PAT), séparé de la configuration."""
from __future__ import annotations

import logging
import os
import stat
import tomllib
from pathlib import Path

log = logging.getLogger("pyminidash.secrets")


class SecretsError(Exception):
    """Fichier de secrets absent d'un format attendu ou mal formé."""


def load_secrets(path: str | Path) -> dict[str, str]:
    p = Path(path)
    if not p.is_file():
        return {}
    try:
        data = tomllib.loads(p.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise SecretsError(f"secrets TOML invalide dans {p} : {exc}") from None

    out: dict[str, str] = {}
    for key, value in data.items():
        if not isinstance(value, str):
            raise SecretsError(
                f"secrets : la clé '{key}' n'est pas une chaîne "
                f"(obtenu {type(value).__name__})"
            )
        out[key] = value

    if os.name == "posix":
        mode = p.stat().st_mode
        if mode & 0o077:
            log.warning(
                "secrets : %s est lisible par d'autres utilisateurs (mode %o) ; "
                "chmod 600 recommandé",
                p, stat.S_IMODE(mode),
            )
    return out
```

- [ ] **Step 5: Lancer, vérifier le succès**

Run: `uv run pytest tests/test_secrets.py -v`
Expected: PASS (6 tests ; le test POSIX est *skipped* sur Windows)

- [ ] **Step 6: Suite complète**

Run: `uv run pytest -q`
Expected: 66 (existants) + 6 nouveaux, tous verts (1 test skipped sur Windows).

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "Ajoute errors.ProviderError et secrets.load_secrets"
```

---

## Task 2: `config.py` — connexions + validation

**Files:**
- Modify: `pyminidash/config.py`
- Modify: `pyminidash/registry.py`
- Create: `tests/test_config_connections.py`

**Interfaces:**
- Consumes: `pyminidash.registry.get_provider` (existant).
- Produces:
  - `pyminidash/registry.py` : `validate_params(pdef, params, *, injected: frozenset[str] = frozenset()) -> None`
    - si une clé de `injected` est présente dans `params` → `ValueError(f"{pdef.name}: le paramètre '{k}' est injecté, à ne pas mettre dans params")`.
    - sinon `signature.bind(**{**{n: None for n in injected if n in signature.parameters}, **params})` ; `TypeError` → `ValueError` (message inchangé).
  - `pyminidash/config.py` :
    - `class ConnectionConfig(BaseModel)` : `base_url: str`, `token: str`, `user: str | None = None`, `verify: bool | str = True`, `auth: Literal["bearer"] = "bearer"`.
      - `base_url` : `field_validator` → schéma `http`/`https` + hôte non vide sinon `ValueError` ; retourne `v.rstrip("/")`.
      - `token` : `field_validator` → non vide après `strip()` sinon `ValueError`.
    - `Config.connections: dict[str, ConnectionConfig] = PField(default_factory=dict)`.
    - `BlockConfig.connection: str | None = None`.
    - `_cross_checks` : pour chaque bloc, après résolution du provider :
      - `wants = "connection" in pdef.signature.parameters`
      - `requires = wants and pdef.signature.parameters["connection"].default is inspect.Parameter.empty`
      - `block.connection is not None and not wants` → `ValueError(f"{where} : le provider '{block.provider}' n'utilise pas de connexion")`
      - `requires and block.connection is None` → `ValueError(f"{where} : le provider '{block.provider}' exige connection = \"...\"")`
      - `block.connection is not None and block.connection not in self.connections` → `ValueError(f"{where} : connexion inconnue '{block.connection}' ; disponibles : {', '.join(sorted(self.connections)) or '(aucune)'}")`
      - `validate_params(pdef, block.params, injected=frozenset({"connection"}) if wants else frozenset())`

- [ ] **Step 1: Écrire le test qui échoue** — `tests/test_config_connections.py`

```python
import textwrap

import pytest

from pyminidash.config import ConfigError, load_config
from pyminidash.models import Record, text, title
from pyminidash.registry import provider


@pytest.fixture
def conn_providers():
    @provider("needs_conn")
    def needs_conn(connection, q: str):
        return [Record(title("k", "K", q))]

    @provider("opt_conn")
    def opt_conn(connection=None, q: str = "x"):
        return [Record(title("k", "K", q))]

    return ["needs_conn", "opt_conn"]


def _write(tmp_path, body):
    p = tmp_path / "config.toml"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


def test_valid_connection_and_block(tmp_path, conn_providers):
    p = _write(tmp_path, """
        [connections.jira]
        base_url = "https://jira.example.com/"
        token = "jira"

        [[groups]]
        id = "g"
        title = "G"
        type = "table"
          [[groups.blocks]]
          provider = "needs_conn"
          connection = "jira"
          params = { q = "hi" }
    """)
    cfg = load_config(p)
    assert cfg.connections["jira"].base_url == "https://jira.example.com"  # slash retiré
    assert cfg.groups[0].blocks[0].connection == "jira"


def test_bad_base_url(tmp_path, conn_providers):
    p = _write(tmp_path, """
        [connections.jira]
        base_url = "pas-une-url"
        token = "jira"
        [[groups]]
        id = "g"
        title = "G"
        type = "table"
          [[groups.blocks]]
          provider = "opt_conn"
    """)
    with pytest.raises(ConfigError, match="base_url"):
        load_config(p)


def test_provider_requires_connection(tmp_path, conn_providers):
    p = _write(tmp_path, """
        [[groups]]
        id = "g"
        title = "G"
        type = "table"
          [[groups.blocks]]
          provider = "needs_conn"
          params = { q = "hi" }
    """)
    with pytest.raises(ConfigError, match="exige connection"):
        load_config(p)


def test_unknown_connection(tmp_path, conn_providers):
    p = _write(tmp_path, """
        [[groups]]
        id = "g"
        title = "G"
        type = "table"
          [[groups.blocks]]
          provider = "needs_conn"
          connection = "nope"
          params = { q = "hi" }
    """)
    with pytest.raises(ConfigError, match="connexion inconnue 'nope'"):
        load_config(p)


def test_connection_on_provider_that_refuses_it(tmp_path, conn_providers):
    p = _write(tmp_path, """
        [connections.jira]
        base_url = "https://jira.example.com"
        token = "jira"
        [[groups]]
        id = "g"
        title = "G"
        type = "table"
          [[groups.blocks]]
          provider = "disk_usage"
          connection = "jira"
          params = { paths = ["."] }
    """)
    with pytest.raises(ConfigError, match="n'utilise pas de connexion"):
        load_config(p)


def test_connection_in_params_is_rejected(tmp_path, conn_providers):
    p = _write(tmp_path, """
        [connections.jira]
        base_url = "https://jira.example.com"
        token = "jira"
        [[groups]]
        id = "g"
        title = "G"
        type = "table"
          [[groups.blocks]]
          provider = "needs_conn"
          connection = "jira"
          params = { connection = "jira", q = "hi" }
    """)
    with pytest.raises(ConfigError, match="injecté"):
        load_config(p)


def test_optional_connection_block_without_connection_ok(tmp_path, conn_providers):
    p = _write(tmp_path, """
        [[groups]]
        id = "g"
        title = "G"
        type = "table"
          [[groups.blocks]]
          provider = "opt_conn"
    """)
    load_config(p)  # ne lève pas
```

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `uv run pytest tests/test_config_connections.py -v`
Expected: FAIL — `connections` absent du modèle / `connection` non reconnu / validations absentes.

- [ ] **Step 3: Modifier `pyminidash/registry.py`**

Remplacer `validate_params` :

```python
def validate_params(pdef: ProviderDef, params: dict, *,
                    injected: frozenset[str] = frozenset()) -> None:
    clash = injected & params.keys()
    if clash:
        k = sorted(clash)[0]
        raise ValueError(
            f"{pdef.name}: le paramètre '{k}' est injecté, à ne pas mettre dans params"
        )
    probe = {n: None for n in injected if n in pdef.signature.parameters}
    probe.update(params)
    try:
        pdef.signature.bind(**probe)
    except TypeError as exc:
        raise ValueError(
            f"{pdef.name}: {exc} ; signature attendue: {pdef.signature}"
        ) from None
```

- [ ] **Step 4: Modifier `pyminidash/config.py`**

Ajouter les imports :
```python
import inspect
from urllib.parse import urlsplit
from pydantic import field_validator
```

Ajouter le modèle (avant `BlockConfig`) :
```python
class ConnectionConfig(BaseModel):
    base_url: str
    token: str
    user: str | None = None
    verify: bool | str = True
    auth: Literal["bearer"] = "bearer"

    @field_validator("base_url")
    @classmethod
    def _check_base_url(cls, v: str) -> str:
        parsed = urlsplit(v)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError(f"base_url invalide : {v!r} (attendu http(s)://hôte)")
        return v.rstrip("/")

    @field_validator("token")
    @classmethod
    def _check_token(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("token vide")
        return v
```

`BlockConfig` : ajouter `connection: str | None = None`.

`Config` : ajouter `connections: dict[str, ConnectionConfig] = PField(default_factory=dict)`.

Dans `_cross_checks`, remplacer le corps de la boucle `for i, block in enumerate(group.blocks):` par :
```python
                if block.title is None:
                    block.title = block.provider
                where = f"groupe '{group.id}' bloc {i}"
                try:
                    pdef = get_provider(block.provider)
                except ValueError as exc:
                    raise ValueError(f"{where}: {exc}") from None

                params = pdef.signature.parameters
                wants = "connection" in params
                requires = (
                    wants
                    and params["connection"].default is inspect.Parameter.empty
                )
                if block.connection is not None and not wants:
                    raise ValueError(
                        f"{where} : le provider '{block.provider}' n'utilise pas de connexion"
                    )
                if requires and block.connection is None:
                    raise ValueError(
                        f"{where} : le provider '{block.provider}' exige connection = \"...\""
                    )
                if block.connection is not None and block.connection not in self.connections:
                    avail = ", ".join(sorted(self.connections)) or "(aucune)"
                    raise ValueError(
                        f"{where} : connexion inconnue '{block.connection}' ; disponibles : {avail}"
                    )
                try:
                    validate_params(
                        pdef, block.params,
                        injected=frozenset({"connection"}) if wants else frozenset(),
                    )
                except ValueError as exc:
                    raise ValueError(f"{where}: {exc}") from None
```

- [ ] **Step 5: Lancer, vérifier le succès**

Run: `uv run pytest tests/test_config_connections.py -v`
Expected: PASS (7 tests)

- [ ] **Step 6: Non-régression**

Run: `uv run pytest tests/test_config.py tests/test_registry.py -q`
Expected: tous verts (les configs sans `[connections]` restent valides ; `validate_params` sans `injected` se comporte comme avant).

- [ ] **Step 7: Suite complète + commit**

```bash
uv run pytest -q
git add -A
git commit -m "Ajoute les connexions à la config et leur validation"
```

---

## Task 3: `connection.py` — `Connection` + `build_connections`

**Files:**
- Create: `pyminidash/connection.py`
- Create: `tests/test_connection.py`

**Interfaces:**
- Consumes: `pyminidash.config.Config`, `pyminidash.config.ConnectionConfig`, `pyminidash.config.ConfigError`.
- Produces:
  - `@dataclass(frozen=True, repr=False) class Connection` : `name: str`, `base_url: str`, `token: str`, `verify: bool | str = True`, `user: str | None = None`.
    - `__repr__` → `f"Connection(name={self.name!r}, base_url={self.base_url!r}, token=***, verify={self.verify!r}, user={self.user!r})"`.
    - `client(self, timeout: float = 15.0) -> httpx.Client` : `httpx.Client(base_url=..., headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}, verify=..., timeout=..., follow_redirects=False)`.
  - `build_connections(config: Config, secrets: dict[str, str]) -> dict[str, Connection]` :
    - `cc.token not in secrets` → `ConfigError(f"connexion '{name}' : clé de token '{cc.token}' absente de secrets.toml")`
    - `isinstance(cc.verify, str) and not Path(cc.verify).is_file()` → `ConfigError(f"connexion '{name}' : fichier CA '{cc.verify}' introuvable")`
    - sinon `Connection(name=name, base_url=cc.base_url, token=secrets[cc.token], verify=cc.verify, user=cc.user)`.

- [ ] **Step 1: Écrire le test qui échoue** — `tests/test_connection.py`

```python
import httpx
import pytest

from pyminidash.config import Config, ConfigError
from pyminidash.connection import Connection, build_connections


def _config(**conn):
    return Config.model_validate({
        "connections": {"jira": {"base_url": "https://jira.example.com", "token": "jira", **conn}},
        "groups": [{"id": "g", "title": "G", "type": "table",
                    "blocks": [{"provider": "disk_usage", "params": {"paths": ["."]}}]}],
    })


def test_build_resolves_token():
    conns = build_connections(_config(), {"jira": "SECRET-PAT"})
    assert conns["jira"].token == "SECRET-PAT"
    assert conns["jira"].base_url == "https://jira.example.com"


def test_missing_token_raises():
    with pytest.raises(ConfigError, match="clé de token 'jira'"):
        build_connections(_config(), {})


def test_missing_ca_file_raises(tmp_path):
    with pytest.raises(ConfigError, match="CA"):
        build_connections(_config(verify=str(tmp_path / "absent.pem")), {"jira": "x"})


def test_existing_ca_file_ok(tmp_path):
    ca = tmp_path / "ca.pem"
    ca.write_text("-----BEGIN CERTIFICATE-----\n", encoding="utf-8")
    conns = build_connections(_config(verify=str(ca)), {"jira": "x"})
    assert conns["jira"].verify == str(ca)


def test_repr_hides_token():
    c = Connection(name="jira", base_url="https://x", token="SUPER-SECRET")
    assert "SUPER-SECRET" not in repr(c)
    assert "token=***" in repr(c)


def test_client_sets_bearer_header_and_base_url():
    c = Connection(name="jira", base_url="https://jira.example.com", token="PAT123")
    with c.client() as client:
        assert client.headers["authorization"] == "Bearer PAT123"
        assert client.headers["accept"] == "application/json"
        assert str(client.base_url) == "https://jira.example.com"


def test_client_passes_verify_false():
    c = Connection(name="jira", base_url="https://x", token="t", verify=False)
    with c.client() as client:  # ne lève pas
        assert isinstance(client, httpx.Client)
```

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `uv run pytest tests/test_connection.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pyminidash.connection'`

- [ ] **Step 3: Écrire `pyminidash/connection.py`**

```python
"""Connexions authentifiées vers des services externes (Jira, Bitbucket, Bamboo)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import httpx

from pyminidash.config import Config, ConfigError


@dataclass(frozen=True, repr=False)
class Connection:
    name: str
    base_url: str
    token: str
    verify: bool | str = True
    user: str | None = None

    def __repr__(self) -> str:
        return (
            f"Connection(name={self.name!r}, base_url={self.base_url!r}, "
            f"token=***, verify={self.verify!r}, user={self.user!r})"
        )

    def client(self, timeout: float = 15.0) -> httpx.Client:
        return httpx.Client(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
            },
            verify=self.verify,
            timeout=timeout,
            follow_redirects=False,
        )


def build_connections(config: Config, secrets: dict[str, str]) -> dict[str, Connection]:
    out: dict[str, Connection] = {}
    for name, cc in config.connections.items():
        if cc.token not in secrets:
            raise ConfigError(
                f"connexion '{name}' : clé de token '{cc.token}' absente de secrets.toml"
            )
        if isinstance(cc.verify, str) and not Path(cc.verify).is_file():
            raise ConfigError(
                f"connexion '{name}' : fichier CA '{cc.verify}' introuvable"
            )
        out[name] = Connection(
            name=name,
            base_url=cc.base_url,
            token=secrets[cc.token],
            verify=cc.verify,
            user=cc.user,
        )
    return out
```

- [ ] **Step 4: Lancer, vérifier le succès**

Run: `uv run pytest tests/test_connection.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Suite complète + commit**

```bash
uv run pytest -q
git add -A
git commit -m "Ajoute l'objet Connection et build_connections"
```

---

## Task 4: `runner.py` — injection de la connexion

**Files:**
- Modify: `pyminidash/runner.py`
- Create: `tests/test_runner_injection.py`

**Interfaces:**
- Consumes: `pyminidash.connection.Connection` (type seulement), `pyminidash.errors.ProviderError`.
- Produces:
  - `run_block(block: BlockConfig, connections: dict | None = None) -> BlockResult`
    - construit `kwargs = dict(block.params)` ;
    - si `"connection" in pdef.signature.parameters` **et** `block.connection is not None` → `kwargs["connection"] = (connections or {})[block.connection]` ;
    - appelle `asyncio.to_thread(pdef.func, **kwargs)` (le reste inchangé) ;
    - nouveau `except ProviderError as exc:` **avant** le `except Exception` générique → `log.warning("bloc '%s' : %s", block.provider, exc)` puis `return BlockError("exception", str(exc))` (pas de préfixe de type).

- [ ] **Step 1: Écrire le test qui échoue** — `tests/test_runner_injection.py`

```python
import pytest

from pyminidash.config import BlockConfig
from pyminidash.connection import Connection
from pyminidash.errors import ProviderError
from pyminidash.models import Record, title
from pyminidash.registry import provider
from pyminidash.runner import BlockError, BlockOk, run_block


async def test_connection_is_injected():
    seen = {}

    @provider("inj")
    def inj(connection, q: str):
        seen["conn"] = connection
        return [Record(title("k", "K", q))]

    conn = Connection(name="jira", base_url="https://x", token="t")
    res = await run_block(
        BlockConfig(provider="inj", connection="jira", params={"q": "hi"}),
        {"jira": conn},
    )
    assert isinstance(res, BlockOk)
    assert seen["conn"] is conn


async def test_no_connection_param_means_no_injection():
    @provider("plain")
    def plain(n: int = 1):
        return [Record(title("k", "K", str(n)))]

    res = await run_block(BlockConfig(provider="plain", params={"n": 3}))
    assert isinstance(res, BlockOk)
    assert res.records[0].fields[0].value == "3"


async def test_provider_error_message_has_no_type_prefix():
    @provider("boom")
    def boom(connection):
        raise ProviderError("authentification refusée pour la connexion 'jira'")

    conn = Connection(name="jira", base_url="https://x", token="t")
    res = await run_block(
        BlockConfig(provider="boom", connection="jira"), {"jira": conn}
    )
    assert isinstance(res, BlockError)
    assert res.message == "authentification refusée pour la connexion 'jira'"
    assert "ProviderError" not in res.message


async def test_unexpected_exception_still_prefixed():
    @provider("crash")
    def crash(connection):
        raise RuntimeError("bug")

    conn = Connection(name="jira", base_url="https://x", token="t")
    res = await run_block(BlockConfig(provider="crash", connection="jira"), {"jira": conn})
    assert isinstance(res, BlockError)
    assert res.message == "RuntimeError: bug"
```

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `uv run pytest tests/test_runner_injection.py -v`
Expected: FAIL — `run_block()` n'accepte pas de 2e argument / `connection` non injecté.

- [ ] **Step 3: Modifier `pyminidash/runner.py`**

Ajouter l'import : `from pyminidash.errors import ProviderError`.

Remplacer la signature et le corps de `run_block` :

```python
async def run_block(block: BlockConfig, connections: dict | None = None) -> BlockResult:
    pdef = get_provider(block.provider)
    timeout = block.timeout or DEFAULT_TIMEOUT

    kwargs = dict(block.params)
    if "connection" in pdef.signature.parameters and block.connection is not None:
        kwargs["connection"] = (connections or {})[block.connection]

    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(pdef.func, **kwargs), timeout
        )
    except (asyncio.TimeoutError, TimeoutError):
        # asyncio.wait_for annule le *future*, pas le thread : le worker est
        # abandonné, pas interrompu — le provider continue jusqu'au bout dans le
        # threadpool par défaut. Les providers intégrés sont auto-bornés (httpx
        # porte son propre timeout, les appels psutil sont finis) ; tout nouveau
        # provider faisant de l'I/O bloquante DOIT imposer son propre timeout.
        log.warning("bloc '%s' : délai dépassé (%gs)", block.provider, timeout)
        return BlockError("timeout", f"délai dépassé ({timeout:g} s)")
    except ProviderError as exc:
        log.warning("bloc '%s' : %s", block.provider, exc)
        return BlockError("exception", str(exc))
    except Exception as exc:  # noqa: BLE001 — on veut tout attraper
        log.exception("bloc '%s' : exception du provider", block.provider)
        return BlockError("exception", f"{type(exc).__name__}: {exc}")

    problem = _check_records(result)
    if problem:
        log.error("bloc '%s' : %s", block.provider, problem)
        return BlockError("invalid_result", problem)
    return BlockOk(records=result, computed_at=datetime.now())
```

- [ ] **Step 4: Lancer, vérifier le succès**

Run: `uv run pytest tests/test_runner_injection.py tests/test_runner.py -v`
Expected: PASS (4 nouveaux + les existants de `test_runner.py`).

- [ ] **Step 5: Suite complète + commit**

```bash
uv run pytest -q
git add -A
git commit -m "Le runner injecte la connexion et respecte ProviderError"
```

---

## Task 5: `providers/_atlassian.py` — `get_json` + erreurs + `count_record`

**Files:**
- Create: `pyminidash/providers/_atlassian.py`
- Create: `tests/test_atlassian_helpers.py`

**Interfaces:**
- Consumes: `pyminidash.errors.ProviderError`, `pyminidash.models` (`Record`, `StatusLevel`, `status`).
- **Ne PAS importer `pyminidash.connection`** (ni dans `_atlassian.py` ni dans `jira.py`) : `connection.py` importe `config.py`, qui importe `pyminidash.providers` → cycle. Le paramètre `connection` des fonctions reste **non typé** (ou typé en commentaire). On n'utilise que `connection.name`, `connection.base_url`, `connection.client(...)`.
- Produces (dans `_atlassian.py`) :
  - `class AtlassianError(ProviderError)` ; `class AuthError(AtlassianError)` ; `class ConnError(AtlassianError)` ; `class NotFoundError(AtlassianError)` ; `class ApiError(AtlassianError)`.
  - `get_json(connection, path: str, *, params: dict | None = None, timeout: float = 15.0) -> Any` :
    - `httpx.ConnectError` dont une cause est `ssl.SSLError` → `ConnError(f"certificat TLS rejeté pour '{connection.name}' — vérifiez verify")`.
    - autre `httpx.ConnectError` → `ConnError(f"connexion impossible à '{connection.name}' ({connection.base_url})")`.
    - `httpx.TimeoutException` → `ConnError(f"délai dépassé en contactant '{connection.name}'")`.
    - `resp.status_code in (401, 403)` → `AuthError(f"authentification refusée pour la connexion '{connection.name}' — vérifiez le token")`.
    - `404` → `NotFoundError(f"ressource introuvable ({path})")`.
    - `400` → `ApiError(<message d'API si disponible sinon générique>)`.
    - autre `>= 400` → `ApiError(f"erreur HTTP {code} sur {path}")`.
    - JSON non parseable → `ApiError(f"réponse non-JSON de '{connection.name}'")`.
    - sinon `resp.json()`.
  - `count_record(label: str, count: int, *, warn_above: int | None = None, error_above: int | None = None) -> Record` :
    - niveau : `count > error_above` → `ERROR` ; sinon `count > warn_above` → `WARN` ; sinon `OK` (seuils `None` ignorés).
    - `Record(status("count", label, str(count), level=<niveau>, summary=True))` (un seul champ, `role=BADGE` via le défaut de `status()`).
    - *(Écart assumé vs spec §5 qui disait `number` : `number` ne porte pas de couleur ; `status` permet les seuils colorés. Comportement observable : un compteur coloré.)*

- [ ] **Step 1: Écrire le test qui échoue** — `tests/test_atlassian_helpers.py`

```python
import httpx
import pytest
import respx

from pyminidash.connection import Connection
from pyminidash.models import FieldType, StatusLevel
from pyminidash.providers._atlassian import (
    ApiError, AuthError, ConnError, NotFoundError, count_record, get_json,
)

CONN = Connection(name="jira", base_url="https://jira.example.com", token="PAT")


@respx.mock
def test_get_json_ok():
    respx.get("https://jira.example.com/x").mock(
        return_value=httpx.Response(200, json={"a": 1})
    )
    assert get_json(CONN, "/x") == {"a": 1}


@respx.mock
def test_get_json_401_is_auth_error_without_token():
    respx.get("https://jira.example.com/x").mock(return_value=httpx.Response(401))
    with pytest.raises(AuthError) as exc:
        get_json(CONN, "/x")
    assert "jira" in str(exc.value)
    assert "PAT" not in str(exc.value)


@respx.mock
def test_get_json_404():
    respx.get("https://jira.example.com/x").mock(return_value=httpx.Response(404))
    with pytest.raises(NotFoundError):
        get_json(CONN, "/x")


@respx.mock
def test_get_json_400_uses_api_message():
    respx.get("https://jira.example.com/x").mock(return_value=httpx.Response(
        400, json={"errorMessages": ["JQL invalide : champ 'foo' inconnu"]}
    ))
    with pytest.raises(ApiError, match="JQL invalide"):
        get_json(CONN, "/x")


@respx.mock
def test_get_json_connect_error():
    respx.get("https://jira.example.com/x").mock(
        side_effect=httpx.ConnectError("refused")
    )
    with pytest.raises(ConnError):
        get_json(CONN, "/x")


@respx.mock
def test_get_json_ssl_error_mentions_tls():
    import ssl
    err = httpx.ConnectError("tls")
    err.__cause__ = ssl.SSLError("bad cert")
    respx.get("https://jira.example.com/x").mock(side_effect=err)
    with pytest.raises(ConnError, match="TLS"):
        get_json(CONN, "/x")


def test_count_record_thresholds():
    r_ok = count_record("Total", 3, warn_above=5, error_above=10)
    assert r_ok.fields[0].type is FieldType.STATUS
    assert r_ok.fields[0].level is StatusLevel.OK
    assert r_ok.fields[0].value == "3"
    assert count_record("T", 7, warn_above=5, error_above=10).fields[0].level is StatusLevel.WARN
    assert count_record("T", 12, warn_above=5, error_above=10).fields[0].level is StatusLevel.ERROR
    assert count_record("T", 99).fields[0].level is StatusLevel.OK  # pas de seuil
```

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `uv run pytest tests/test_atlassian_helpers.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pyminidash.providers._atlassian'`

- [ ] **Step 3: Écrire `pyminidash/providers/_atlassian.py`**

```python
"""Helpers partagés par les providers Atlassian (Jira/Bitbucket/Bamboo)."""
from __future__ import annotations

import ssl
from typing import Any

import httpx

from pyminidash.errors import ProviderError
from pyminidash.models import Record, StatusLevel, status


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
             timeout: float = 15.0) -> Any:
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
    if code >= 400:
        raise ApiError(f"erreur HTTP {code} sur {path}")

    try:
        return resp.json()
    except ValueError:
        raise ApiError(f"réponse non-JSON de '{connection.name}'") from None


def count_record(label: str, count: int, *, warn_above: int | None = None,
                 error_above: int | None = None) -> Record:
    level = StatusLevel.OK
    if error_above is not None and count > error_above:
        level = StatusLevel.ERROR
    elif warn_above is not None and count > warn_above:
        level = StatusLevel.WARN
    return Record(status("count", label, str(count), level=level, summary=True))
```

- [ ] **Step 4: Lancer, vérifier le succès**

Run: `uv run pytest tests/test_atlassian_helpers.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Suite complète + commit**

```bash
uv run pytest -q
git add -A
git commit -m "Ajoute les helpers Atlassian (get_json, taxonomie d'erreurs, count_record)"
```

---

## Task 6: `providers/jira.py` — `jira_jql` + mapping des champs

**Files:**
- Create: `pyminidash/providers/jira.py`
- Modify: `pyminidash/providers/__init__.py`
- Create: `tests/test_providers_jira.py`

**Interfaces:**
- Consumes: `_atlassian.get_json`, `_atlassian.count_record`, `pyminidash.registry.provider`, `pyminidash.models` (helpers + `Field`, `FieldRole`, `StatusLevel`).
- **Ne PAS importer `pyminidash.connection`** (cycle via `config` → `providers`). Le paramètre `connection` reste non typé ; on n'accède qu'à `.base_url`.
- Produces:
  - `_status_level(name: str) -> StatusLevel` : nom (lower/strip) ∈ {done, closed, resolved, terminé, fermé} → `OK` ; ∈ {blocked, impediment, bloqué} → `ERROR` ; sinon `NEUTRAL`.
  - `_parse_dt(v)` : `""`/`None` → `None` ; ISO 8601 (avec `Z`) → `datetime` ; sinon la chaîne brute.
  - `_issue_field(name: str, issue: dict, base_url: str) -> Field` : mapping du §6 de la spec (`key` → `link` + `role=TITLE` vers `{base_url}/browse/{KEY}` ; `status` → `status` + `summary` + niveau heuristique ; `assignee`/`reporter` → `displayName` ou « Non assigné » ; `created`/`updated` → `datetime_` ; `labels`/`components`/`fixVersions` joints ; `customfield_*` / inconnu → `text` stringifié).
  - `_search(connection, jql: str, fields: list[str], max_results: int) -> list[Record]` : pagination `startAt`/`maxResults` (page 100, plafond dur 200), un `Record` par issue avec les champs dans l'ordre de `fields`.
  - `@provider("jira_jql") def jira_jql(connection, jql: str, fields: list[str], max_results: int = 50) -> list[Record]`.
  - `providers/__init__.py` importe `jira`.

- [ ] **Step 1: Écrire le test qui échoue** — `tests/test_providers_jira.py`

```python
import httpx
import pytest
import respx

from pyminidash.connection import Connection
from pyminidash.models import FieldRole, FieldType, StatusLevel
from pyminidash.providers._atlassian import ApiError
from pyminidash.providers.jira import _parse_dt, _status_level, jira_jql

CONN = Connection(name="jira", base_url="https://jira.example.com", token="PAT")

_ISSUE = {
    "key": "ABC-1",
    "fields": {
        "summary": "Corriger le bug",
        "status": {"name": "In Progress"},
        "assignee": {"displayName": "Léa Martin"},
        "priority": {"name": "High"},
        "updated": "2026-08-20T14:30:00.000+0200",
    },
}


def _search_response(issues, total=None):
    return httpx.Response(200, json={
        "issues": issues,
        "total": total if total is not None else len(issues),
        "startAt": 0,
        "maxResults": 100,
    })


def test_status_level_heuristic():
    assert _status_level("Done") is StatusLevel.OK
    assert _status_level(" Terminé ") is StatusLevel.OK
    assert _status_level("Blocked") is StatusLevel.ERROR
    assert _status_level("In Progress") is StatusLevel.NEUTRAL


def test_parse_dt():
    assert _parse_dt("") is None
    dt = _parse_dt("2026-08-20T14:30:00.000+0200")
    assert dt.year == 2026 and dt.hour == 14


@respx.mock
def test_jira_jql_maps_fields_in_order():
    respx.get("https://jira.example.com/rest/api/2/search").mock(
        return_value=_search_response([_ISSUE])
    )
    records = jira_jql(CONN, "project = ABC", ["key", "summary", "status", "assignee", "updated"])
    assert len(records) == 1
    f = records[0].fields
    assert [x.key for x in f] == ["key", "summary", "status", "assignee", "updated"]
    assert f[0].type is FieldType.LINK
    assert f[0].role is FieldRole.TITLE
    assert f[0].url == "https://jira.example.com/browse/ABC-1"
    assert f[2].type is FieldType.STATUS and f[2].level is StatusLevel.NEUTRAL
    assert f[3].value == "Léa Martin"
    assert f[4].type is FieldType.DATETIME


@respx.mock
def test_jira_jql_unassigned_and_missing_fields():
    issue = {"key": "ABC-2", "fields": {"summary": "x", "status": {"name": "To Do"}}}
    respx.get("https://jira.example.com/rest/api/2/search").mock(
        return_value=_search_response([issue])
    )
    records = jira_jql(CONN, "q", ["assignee", "labels"])
    assert records[0].fields[0].value == "Non assigné"
    assert records[0].fields[1].value == ""


@respx.mock
def test_jira_jql_paginates_to_max_results():
    route = respx.get("https://jira.example.com/rest/api/2/search")
    route.side_effect = [
        _search_response([_ISSUE, _ISSUE], total=3),
        _search_response([_ISSUE], total=3),
    ]
    records = jira_jql(CONN, "q", ["key"], max_results=3)
    assert len(records) == 3
    assert route.call_count == 2


@respx.mock
def test_jira_jql_bad_jql_raises_api_error():
    respx.get("https://jira.example.com/rest/api/2/search").mock(
        return_value=httpx.Response(400, json={"errorMessages": ["Le champ 'foo' n'existe pas"]})
    )
    with pytest.raises(ApiError, match="foo"):
        jira_jql(CONN, "foo = bar", ["key"])


@respx.mock
def test_jira_jql_customfield():
    issue = {"key": "ABC-9", "fields": {"customfield_10001": 8}}
    respx.get("https://jira.example.com/rest/api/2/search").mock(
        return_value=_search_response([issue])
    )
    records = jira_jql(CONN, "q", ["customfield_10001"])
    assert records[0].fields[0].value == "8"
```

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `uv run pytest tests/test_providers_jira.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pyminidash.providers.jira'`

- [ ] **Step 3: Écrire `pyminidash/providers/jira.py`**

```python
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
```

- [ ] **Step 4: Modifier `pyminidash/providers/__init__.py`**

```python
"""Import des modules de providers intégrés → enregistrement au chargement."""
from pyminidash.providers import http, jira, system  # noqa: F401
```

- [ ] **Step 5: Lancer, vérifier le succès**

Run: `uv run pytest tests/test_providers_jira.py -v`
Expected: PASS (8 tests)

- [ ] **Step 6: Suite complète + commit**

```bash
uv run pytest -q
git add -A
git commit -m "Ajoute le provider jira_jql et le mapping des champs Jira"
```

---

## Task 7: `providers/jira.py` — `jira_jql_count` + `jira_my_issues`

**Files:**
- Modify: `pyminidash/providers/jira.py`
- Modify: `tests/test_providers_jira.py`

**Interfaces:**
- Consumes: `_search` (Task 6), `count_record` (Task 5), `get_json`.
- Produces:
  - `@provider("jira_jql_count") def jira_jql_count(connection, jql: str, warn_above: int | None = None, error_above: int | None = None) -> list[Record]` : `GET /rest/api/2/search` avec `maxResults=0`, lit `total`, renvoie `[count_record("Total", total, warn_above=..., error_above=...)]`.
  - `@provider("jira_my_issues") def jira_my_issues(connection, fields: list[str] | None = None, max_results: int = 50) -> list[Record]` : JQL figé `assignee = currentUser() AND resolution = Unresolved ORDER BY updated DESC` ; `fields` défaut `["key", "summary", "status", "priority", "updated"]` (via sentinelle `None`) ; délègue à `_search`.

- [ ] **Step 1: Ajouter les tests qui échouent** — à la fin de `tests/test_providers_jira.py`

```python
from pyminidash.providers.jira import jira_jql_count, jira_my_issues


@respx.mock
def test_jira_jql_count_reads_total_with_thresholds():
    route = respx.get("https://jira.example.com/rest/api/2/search").mock(
        return_value=httpx.Response(200, json={"total": 12, "issues": []})
    )
    records = jira_jql_count(CONN, "project = ABC", warn_above=5, error_above=10)
    assert len(records) == 1
    assert records[0].fields[0].value == "12"
    assert records[0].fields[0].level is StatusLevel.ERROR
    # maxResults=0 demandé
    sent = route.calls.last.request.url
    assert "maxResults=0" in str(sent)


@respx.mock
def test_jira_my_issues_uses_fixed_jql_and_default_fields():
    route = respx.get("https://jira.example.com/rest/api/2/search").mock(
        return_value=_search_response([_ISSUE])
    )
    records = jira_my_issues(CONN)
    assert [x.key for x in records[0].fields] == ["key", "summary", "status", "priority", "updated"]
    url = str(route.calls.last.request.url)
    assert "currentUser" in url
    assert "Unresolved" in url


@respx.mock
def test_jira_my_issues_field_override():
    respx.get("https://jira.example.com/rest/api/2/search").mock(
        return_value=_search_response([_ISSUE])
    )
    records = jira_my_issues(CONN, fields=["key", "summary"])
    assert [x.key for x in records[0].fields] == ["key", "summary"]
```

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `uv run pytest tests/test_providers_jira.py -k "count or my_issues" -v`
Expected: FAIL — `ImportError: cannot import name 'jira_jql_count'`

- [ ] **Step 3: Ajouter à `pyminidash/providers/jira.py`**

```python
_MY_ISSUES_JQL = (
    "assignee = currentUser() AND resolution = Unresolved ORDER BY updated DESC"
)
_MY_ISSUES_FIELDS = ["key", "summary", "status", "priority", "updated"]


@provider("jira_jql_count")
def jira_jql_count(connection, jql: str, warn_above: int | None = None,
                   error_above: int | None = None) -> list[Record]:
    page = get_json(connection, "/rest/api/2/search",
                    params={"jql": jql, "maxResults": 0})
    total = int(page.get("total", 0))
    return [count_record("Total", total, warn_above=warn_above,
                         error_above=error_above)]


@provider("jira_my_issues")
def jira_my_issues(connection, fields: list[str] | None = None,
                   max_results: int = 50) -> list[Record]:
    return _search(connection, _MY_ISSUES_JQL,
                   fields or _MY_ISSUES_FIELDS, max_results)
```

- [ ] **Step 4: Lancer, vérifier le succès**

Run: `uv run pytest tests/test_providers_jira.py -v`
Expected: PASS (11 tests)

- [ ] **Step 5: Suite complète + commit**

```bash
uv run pytest -q
git add -A
git commit -m "Ajoute jira_jql_count et jira_my_issues"
```

---

## Task 8: Câblage — `__main__`, `app`, `routes`, `.gitignore`, `secrets.example.toml`

**Files:**
- Modify: `pyminidash/web/app.py`, `pyminidash/web/routes.py`, `pyminidash/__main__.py`
- Create: `secrets.example.toml`
- Modify: `.gitignore`
- Modify: `tests/test_main.py`

**Interfaces:**
- Consumes: `pyminidash.secrets.load_secrets`, `pyminidash.connection.build_connections`, `pyminidash.config.ConfigError`.
- Produces:
  - `create_app(config: Config, connections: dict | None = None) -> FastAPI` : `app.state.connections = connections or {}`.
  - `routes.block_fragment` : `result = await run_block(block, request.app.state.connections)`.
  - `__main__.build_parser` : `--secrets` (type `Path`, défaut `None`).
  - `__main__.main` : après `load_config`, calcule `secrets_path = args.secrets or args.config.parent / "secrets.toml"` ; `secrets = load_secrets(secrets_path)` ; `connections = build_connections(config, secrets)` — tout `ConfigError` (et `SecretsError`) → stderr + `SystemExit(2)` ; `create_app(config, connections)`.
  - `secrets.example.toml` : `jira = ""` / `bitbucket = ""` / `bamboo = ""` avec un commentaire « Copier en secrets.toml ».
  - `.gitignore` : ligne `secrets.toml`.

- [ ] **Step 1: Ajouter les tests qui échouent** — dans `tests/test_main.py`

```python
def test_parser_has_secrets_option():
    args = build_parser().parse_args(["--secrets", "/tmp/s.toml"])
    assert str(args.secrets).endswith("s.toml")
    assert build_parser().parse_args([]).secrets is None


def test_main_exits_2_on_missing_token(tmp_path, capsys):
    cfg = tmp_path / "c.toml"
    cfg.write_text(
        '[connections.jira]\nbase_url = "https://jira.example.com"\ntoken = "jira"\n'
        '[[groups]]\nid = "g"\ntitle = "G"\ntype = "table"\n'
        '  [[groups.blocks]]\n  provider = "jira_my_issues"\n  connection = "jira"\n',
        encoding="utf-8",
    )
    # pas de secrets.toml à côté → token 'jira' absent
    with pytest.raises(SystemExit) as exc:
        main(["--config", str(cfg)])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "jira" in err and "PAT" not in err
```

Et adapter `test_main_starts_server` pour vérifier que `create_app` reçoit bien des connexions : ajouter, dans la config écrite par ce test, aucune connexion (inchangé) — il doit toujours passer. Ajouter un test dédié :

```python
def test_main_builds_connections(tmp_path, monkeypatch):
    captured = {}
    monkeypatch.setattr("pyminidash.__main__.uvicorn.run", lambda *a, **k: None)
    monkeypatch.setattr(
        "pyminidash.__main__.create_app",
        lambda config, connections: captured.setdefault("conns", connections) or object(),
    )
    (tmp_path / "secrets.toml").write_text('jira = "PAT"\n', encoding="utf-8")
    cfg = tmp_path / "c.toml"
    cfg.write_text(
        '[connections.jira]\nbase_url = "https://jira.example.com"\ntoken = "jira"\n'
        '[[groups]]\nid = "g"\ntitle = "G"\ntype = "table"\n'
        '  [[groups.blocks]]\n  provider = "jira_my_issues"\n  connection = "jira"\n',
        encoding="utf-8",
    )
    main(["--config", str(cfg)])
    assert captured["conns"]["jira"].token == "PAT"
```

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `uv run pytest tests/test_main.py -v`
Expected: FAIL — `--secrets` inconnu / `create_app` n'accepte pas `connections`.

- [ ] **Step 3: Modifier `pyminidash/web/app.py`**

`create_app` :
```python
def create_app(config: Config, connections: dict | None = None) -> FastAPI:
    app = FastAPI(title=config.app.title)
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    templates.env.filters["format_field"] = format_value

    app.state.config = config
    app.state.connections = connections or {}
    app.state.templates = templates

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.include_router(routes.router)
    return app
```

- [ ] **Step 4: Modifier `pyminidash/web/routes.py`**

Dans `block_fragment`, remplacer `result = await run_block(block)` par :
```python
    result = await run_block(block, request.app.state.connections)
```

- [ ] **Step 5: Modifier `pyminidash/__main__.py`**

```python
from pyminidash.config import ConfigError, load_config
from pyminidash.connection import build_connections
from pyminidash.secrets import SecretsError, load_secrets
from pyminidash.web.app import create_app
```

`build_parser` : ajouter
```python
    parser.add_argument("--secrets", type=Path, default=None,
                        help="fichier de secrets (défaut : secrets.toml à côté de --config)")
```

`main` :
```python
def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(args.config)
        secrets_path = args.secrets or args.config.parent / "secrets.toml"
        secrets = load_secrets(secrets_path)
        connections = build_connections(config, secrets)
    except (ConfigError, SecretsError) as exc:
        print(f"Erreur de configuration : {exc}", file=sys.stderr)
        raise SystemExit(2)

    app = create_app(config, connections)

    if args.open:
        url = f"http://{args.host}:{args.port}/"
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    uvicorn.run(app, host=args.host, port=args.port)
```

- [ ] **Step 6: Créer `secrets.example.toml`**

```toml
# Copier ce fichier en secrets.toml (git-ignoré) et renseigner les PAT.
# Chaque clé correspond à un `token = "..."` d'une connexion dans config.toml.
jira      = ""
bitbucket = ""
bamboo    = ""
```

- [ ] **Step 7: Modifier `.gitignore`**

Ajouter sous la section « Brainstorming visual companion » ou en tête :
```
# Secrets locaux
secrets.toml
```

- [ ] **Step 8: Lancer, vérifier le succès**

Run: `uv run pytest tests/test_main.py -v`
Expected: PASS (tous, anciens + nouveaux)

- [ ] **Step 9: Suite complète + commit**

```bash
uv run pytest -q
git add -A
git commit -m "Câble les connexions : --secrets, build_connections, app.state.connections"
```

---

## Task 9: Intégration + config d'exemple + doc

**Files:**
- Create: `tests/test_integration_atlassian.py`
- Modify: `config.example.toml`, `README.md`
- Modify: `tests/test_example_config.py` (si besoin)

**Interfaces:**
- Consumes: tout ce qui précède.
- Produces: un test bout-en-bout (bloc `jira_jql` monté via `Config` + `build_connections` + `TestClient`, `respx` actif → fragment `_table.html` rendu) ; `config.example.toml` avec `[connections.*]` et un groupe « Mon activité » contenant un bloc `jira_my_issues` ; section README « Connexions et secrets ».

- [ ] **Step 1: Écrire le test qui échoue** — `tests/test_integration_atlassian.py`

```python
import httpx
import respx
from fastapi.testclient import TestClient

from pyminidash.config import Config
from pyminidash.connection import build_connections
from pyminidash.web.app import create_app

_ISSUE = {
    "key": "ABC-1",
    "fields": {"summary": "Bug critique", "status": {"name": "To Do"}},
}


def _client():
    config = Config.model_validate({
        "connections": {"jira": {"base_url": "https://jira.example.com", "token": "jira"}},
        "groups": [{
            "id": "jira", "title": "Jira", "type": "table",
            "blocks": [{
                "provider": "jira_jql", "connection": "jira", "title": "Ouvertes",
                "params": {"jql": "project = ABC", "fields": ["key", "summary", "status"]},
            }],
        }],
    })
    connections = build_connections(config, {"jira": "PAT"})
    return TestClient(create_app(config, connections))


@respx.mock
def test_jira_block_renders_table_fragment():
    respx.get("https://jira.example.com/rest/api/2/search").mock(
        return_value=httpx.Response(200, json={"issues": [_ISSUE], "total": 1})
    )
    html = _client().get("/groups/jira/blocks/0").text
    assert "<th>Clé</th>" in html
    assert "ABC-1" in html
    assert "https://jira.example.com/browse/ABC-1" in html
    assert "Bug critique" in html


@respx.mock
def test_jira_block_auth_error_renders_error_frame():
    respx.get("https://jira.example.com/rest/api/2/search").mock(
        return_value=httpx.Response(401)
    )
    html = _client().get("/groups/jira/blocks/0").text
    assert "Erreur" in html
    assert "authentification refusée" in html
    assert "PAT" not in html
```

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `uv run pytest tests/test_integration_atlassian.py -v`
Expected: FAIL (au minimum le rendu ne contient pas encore les bonnes chaînes / selon l'état — mais avec les tâches 1-8 faites, ça peut déjà passer ; si c'est le cas, noter que le test verrouille le comportement et passer à l'étape suivante).

- [ ] **Step 3: (si le test échoue) corriger**

Le pipeline est déjà en place après les tâches 1-8 ; ce test ne devrait rien nécessiter de neuf. S'il échoue, c'est un vrai défaut d'intégration — investiguer (`run_block` reçoit-il `connections` ? le fragment `_table.html` rend-il un champ `link` ?).

- [ ] **Step 4: Étendre `config.example.toml`**

Ajouter, après la section `[app]` et avant le premier `[[groups]]` :

```toml
[connections.jira]
base_url = "https://jira.interne.example.com"
token    = "jira"
# verify = "/etc/pki/ca-trust/interne.pem"   # si CA interne

[connections.bitbucket]
base_url = "https://bitbucket.interne.example.com"
token    = "bitbucket"
user     = "jdupont"

[connections.bamboo]
base_url = "https://bamboo.interne.example.com"
token    = "bamboo"
user     = "jdupont"
```

Ajouter un groupe (les blocs Bitbucket/Bamboo viendront au Plan B) :

```toml
[[groups]]
id = "mon-activite"
title = "Mon activité"
type = "table"

  [[groups.blocks]]
  title      = "Mes issues Jira"
  provider   = "jira_my_issues"
  connection = "jira"
```

- [ ] **Step 5: Vérifier `test_example_config.py`**

Run: `uv run pytest tests/test_example_config.py -v`
Expected: PASS. `load_config` ne touche pas aux secrets → l'ajout de `[connections.*]` ne casse rien ; `jira_my_issues` est enregistré. Si `test_example_config_is_valid` assertait un nombre de groupes exact, l'ajuster (`>= 2` reste vrai).

- [ ] **Step 6: Étendre `README.md`**

Ajouter après la section « Utilisation » :

```markdown
## Connexions et secrets

Les providers Jira / Bitbucket / Bamboo passent par des **connexions**
déclarées dans `config.toml` :

    [connections.jira]
    base_url = "https://jira.interne.example.com"
    token    = "jira"          # clé dans secrets.toml
    # user   = "jdupont"       # requis par les providers "mes ..." / "moi"
    # verify = "/chemin/vers/ca-interne.pem"   # ou false pour ignorer le TLS

Les **PAT** (Personal Access Tokens) vivent dans un fichier `secrets.toml`
séparé, **git-ignoré**, à côté de `config.toml` (ou indiqué par `--secrets`) :

    cp secrets.example.toml secrets.toml
    # puis renseigner : jira = "...", bitbucket = "...", bamboo = "..."

Un bloc référence sa connexion par le champ `connection` :

    [[groups.blocks]]
    provider   = "jira_jql"
    connection = "jira"
    params     = { jql = "project = ABC AND resolution = Unresolved", fields = ["key", "summary", "status"] }

Le token n'apparaît jamais dans les logs ni dans l'interface.
```

Mettre à jour le tableau des providers avec `jira_jql`, `jira_jql_count`, `jira_my_issues`.

- [ ] **Step 7: Suite complète + smoke**

Run: `uv run pytest -q`
Expected: tout vert.

Smoke (optionnel, sans réseau réel — juste vérifier le démarrage échoue proprement sans secrets) :
```bash
uv run pyminidash --config config.example.toml --port 8790
```
Attendu : `Erreur de configuration : connexion 'jira' : clé de token 'jira' absente de secrets.toml` sur stderr, code de sortie 2 (pas de `secrets.toml`).

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "Ajoute le test d'intégration Jira, la config d'exemple et la doc connexions"
```

---

## Self-Review

**Spec coverage :**

| Spec | Tâche |
|---|---|
| §2 `secrets.toml` plat, git-ignoré, `--secrets`, `load_secrets`, non-divulgation | 1, 8 |
| §2 warning permissions POSIX | 1 |
| §3 `[connections.*]`, `ConnectionConfig`, `base_url`/`verify`/`auth`, champ `connection` | 2 |
| §3 objet `Connection` (repr masqué), `client()`, `build_connections` | 3 |
| §3 cycle de vie (`create_app(config, connections)`, client par appel) | 3, 8 |
| §4 injection runner par nom de paramètre | 4 |
| §4 validation : requis/absent, inconnu, posé à tort, `connection` dans params | 2 |
| §4 `connection.user` manquant → erreur claire | *(providers `my_*` : Plan B pour BB/Bamboo ; Jira `my_issues` n'en a pas besoin — noté)* |
| §5 `get_json` + taxonomie d'erreurs (401/403/404/400/TLS/réseau) | 5 |
| §5 `count_record` + seuils | 5 |
| §6 `jira_jql` + mapping complet des champs + pagination + plafond 200 | 6 |
| §6 `jira_jql_count`, `jira_my_issues` (JQL figé, champs par défaut) | 7 |
| §6 erreurs Jira (400 → message API) | 5, 6 |
| §9 erreurs au démarrage → `ConfigError` / exécution → `BlockError` sans token | 2, 3, 4, 5, 8, 9 |
| §10 structure (fichiers) | toutes |
| §11 `config.example.toml`, `secrets.example.toml` | 8, 9 |
| §12 tests par couche, `respx`, intégration | chaque tâche + 9 |
| §13 découpage : ce plan = fondation + Jira | — |

Hors périmètre de ce plan (→ Plan B) : §7 Bitbucket, §8 Bamboo, `_atlassian.paginate`/`resolve_repos`/`strip_html`, groupe « Mon activité » complet.

**Placeholder scan :** aucun `TODO`/`TBD` ; chaque étape de code porte un bloc complet ; l'étape 3 de la tâche 9 est conditionnelle mais explicite (« si échec, investiguer tel point »).

**Type consistency :** `run_block(block, connections=None)` cohérent entre tâches 4 et 8 ; `validate_params(pdef, params, *, injected=frozenset())` cohérent entre tâches 2 (registry) et 2 (config, appelant) ; `get_json(connection, path, *, params, timeout)` cohérent entre tâches 5, 6, 7 ; `count_record(label, count, *, warn_above, error_above)` cohérent tâches 5, 7 ; `Connection(name, base_url, token, verify=True, user=None)` cohérent tâches 3, 4, 5, 6, 9 ; `_search(connection, jql, fields, max_results)` cohérent tâches 6, 7 ; `ProviderError` (tâche 1) → base de `AtlassianError` (tâche 5), attrapé par le runner (tâche 4).

**Écart assumé documenté :** `count_record` utilise un champ `status` (coloré) là où la spec §5 disait `number` — `number` ne peut pas porter de couleur ; le comportement observable (un compteur coloré selon les seuils) est conforme à l'intention. Noté dans l'interface de la tâche 5.
