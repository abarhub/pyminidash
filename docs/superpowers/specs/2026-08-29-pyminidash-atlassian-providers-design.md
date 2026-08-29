# pyminidash — Providers Atlassian (Jira / Bitbucket / Bamboo) + authentification

Date : 2026-08-29
Statut : validé en brainstorming, à relire avant plan d'implémentation
Spec précédente : `docs/superpowers/specs/2026-08-29-pyminidash-design.md`

## 1. Objectif

Ajouter à pyminidash des providers pour trois outils Atlassian **on-premise**
(Server / Data Center) :

- **Jira** — requêtes JQL, compteurs, raccourci « mes issues ».
- **Bitbucket** — pull requests, compteurs, raccourci « PR à relire ».
- **Bamboo** — dernier build d'un plan, builds d'un utilisateur, santé d'une
  liste de plans, builds en cours.

Et le sous-système d'authentification que ces providers nécessitent : des
**connexions** réutilisables déclarées en configuration, des **tokens** (PAT)
stockés hors du fichier de config, et un **client HTTP authentifié** injecté
dans les providers.

### Contexte

- Instances on-premise, authentification par **Personal Access Token (PAT)**,
  en-tête `Authorization: Bearer <token>`.
- Certificats TLS **auto-signés / CA interne** : l'option `verify` est
  configurable par connexion.
- Dashboard toujours local et mono-utilisateur (cf. spec précédente).

### Hors périmètre (YAGNI)

Auth `basic` (le modèle la prévoit mais elle n'est pas implémentée) ; OAuth /
SSO ; rafraîchissement de token ; cache des réponses d'API ; pool de clients
HTTP persistant ; découverte automatique des plans/dépôts au-delà de ce qui est
décrit ; webhooks / mode temps réel.

## 2. Secrets

### Fichier `secrets.toml`

Table plate `clé = "valeur"`, **git-ignoré**, jamais versionné. Emplacement par
défaut : à côté de `config.toml` (`config_path.parent / "secrets.toml"`) ;
surchargé par l'option CLI `--secrets`.

```toml
# secrets.toml — NE PAS versionner
jira      = "NjE2MToxxxxxxxxxxxxxxxx"
bitbucket = "NjE2MToyyyyyyyyyyyyyyyy"
bamboo    = "NjE2MTozzzzzzzzzzzzzzzz"
```

### `pyminidash/secrets.py`

- `SecretsError(Exception)`.
- `load_secrets(path: Path) -> dict[str, str]` :
  - fichier absent → renvoie `{}` (ce n'est une erreur que si une connexion
    référence un token — contrôlé lors de `build_connections`) ;
  - TOML invalide → `SecretsError` ;
  - nesting (une valeur non-`str`) → `SecretsError` nommant la clé fautive ;
  - sur systèmes POSIX, si `stat().st_mode & 0o077` (lisible/inscriptible par
    d'autres) → `logging.getLogger("pyminidash.secrets").warning(...)` non
    bloquant ; ignoré sur Windows.

### Règle de non-divulgation

Le contenu d'un token n'apparaît **jamais** dans un log, un message
d'exception, une réponse HTTP ou le rendu HTML. Tous les messages font
référence à la **clé** (`"jira"`) ou au **nom de connexion**, jamais à la
valeur. L'en-tête `Authorization` n'est jamais loggé.

## 3. Connexions

### Configuration

Nouvelle section `[connections.<nom>]` et nouveau champ `connection` de premier
niveau sur un bloc.

```toml
[connections.jira]
base_url = "https://jira.interne.example.com"
token    = "jira"           # clé dans secrets.toml
# user   = "jdupont"        # optionnel ; requis par les providers "my_*" / "me"
# verify = true             # défaut ; chemin vers un CA bundle, ou false
# auth   = "bearer"         # défaut ; seule valeur acceptée pour l'instant

[connections.bitbucket]
base_url = "https://bitbucket.interne.example.com"
token    = "bitbucket"
user     = "jdupont"

[connections.bamboo]
base_url = "https://bamboo.interne.example.com"
token    = "bamboo"
user     = "jdupont"

[[groups.blocks]]
provider   = "jira_jql"
connection = "jira"         # champ de premier niveau, pas dans params
params     = { jql = "project = ABC AND resolution = Unresolved", fields = ["key", "summary", "status"] }
```

### Modèles Pydantic (`config.py`)

- `ConnectionConfig(BaseModel)` :
  - `base_url: str` — validé : schéma `http`/`https`, hôte non vide, **sans `/`
    final** (normalisé en le retirant).
  - `token: str` — clé de secret, non vide.
  - `user: str | None = None`.
  - `verify: bool | str = True` — `True`/`False`, ou un chemin.
  - `auth: Literal["bearer"] = "bearer"`.
- `Config` : `connections: dict[str, ConnectionConfig] = PField(default_factory=dict)`.
- `BlockConfig` : `connection: str | None = None`.

### Objet `Connection` (`pyminidash/connection.py`)

Dataclass **gelée** :

- `name: str`
- `base_url: str`
- `token: str` — champ exclu du `repr` (`field(repr=False)`) ; `__repr__`
  personnalisé affichant `token=***`.
- `verify: bool | str`
- `user: str | None`

Méthode :

- `client(timeout: float = 15.0) -> httpx.Client` :
  ```python
  httpx.Client(
      base_url=self.base_url,
      headers={"Authorization": f"Bearer {self.token}", "Accept": "application/json"},
      verify=self.verify,
      timeout=timeout,
      follow_redirects=False,
  )
  ```

### `build_connections(config: Config, secrets: dict[str, str]) -> dict[str, Connection]`

Vit dans `connection.py`. Pour chaque `(nom, ConnectionConfig)` :

- `token` absent de `secrets` → `ConfigError`
  (`connexion 'jira' : clé de token 'jira' absente de secrets.toml`).
- `verify` est une `str` et le chemin n'existe pas → `ConfigError`.
- sinon construit le `Connection`.

Appelé une fois au démarrage. En cas d'échec, le serveur ne démarre pas
(code de sortie ≠ 0, message sur stderr — même traitement que `ConfigError`
dans `__main__`).

### Cycle de vie

- `__main__` : `config = load_config(...)` → `secrets = load_secrets(...)` →
  `connections = build_connections(config, secrets)` → `create_app(config, connections)`.
- `create_app(config: Config, connections: dict[str, Connection] | None = None) -> FastAPI` :
  pose `app.state.connections` (défaut `{}`).
- Un `httpx.Client` est créé et fermé **par appel de provider**
  (`with connection.client() as c:`). Pas de client partagé persistant — les
  providers tournent déjà chacun dans un thread via le runner.

## 4. Injection dans le runner et validation

### Injection (`runner.py`)

`run_block(block: BlockConfig, connections: dict[str, Connection] | None = None) -> BlockResult` :

- Inspecte `signature(pdef.func)`. Si elle contient un paramètre nommé
  `connection`, l'appel devient
  `pdef.func(connection=connections[block.connection], **block.params)`.
- Sinon, appel inchangé : `pdef.func(**block.params)`.
- Les providers existants (`http_check`, `http_json`, `disk_usage`,
  `top_processes`) n'ont pas ce paramètre → aucun changement de comportement.
- `connections` par défaut `{}` ; la route passe `request.app.state.connections`.

### Validation au chargement (`config.py`, dans `_cross_checks`)

Un provider **exige une connexion** ssi sa signature a un paramètre `connection`
**sans valeur par défaut**.

Pour chaque bloc :

- exige une connexion **et** `block.connection is None` → `ConfigError`
  (`bloc N : le provider 'jira_jql' exige connection = "..."`).
- `block.connection` défini mais absent de `[connections]` → `ConfigError`
  listant les connexions disponibles.
- `block.connection` défini sur un provider **sans** paramètre `connection`
  → `ConfigError` (faute de frappe probable).
- `validate_params` : le paramètre `connection` est **exclu** du contrôle
  `signature.bind()` (il est injecté, il n'est pas dans `params`). Le reste des
  `params` est validé comme aujourd'hui.

### Utilisateur courant (`connection.user`)

Les providers qui ont besoin de l'utilisateur courant (`bitbucket_my_review`,
`bitbucket_pr` avec `role` non-`None`, `bamboo_user_builds` sans `user`) le
lisent dans `connection.user`. S'il est `None` : le provider lève une erreur
claire à l'exécution (`connection 'bitbucket' : renseignez user pour
bitbucket_my_review`), rendue en erreur de bloc.

## 5. Helpers partagés — `pyminidash/providers/_atlassian.py`

- `get_json(connection, path, *, params=None, timeout=15.0) -> Any` : ouvre un
  client, `GET`, lève des exceptions **traduites** :
  - `401` / `403` → `AuthError(f"authentification refusée pour la connexion '{connection.name}' — vérifiez le token")`
  - erreur TLS (`httpx.ConnectError` dont la cause est une `ssl.SSLError`) →
    `ConnError(f"certificat TLS rejeté pour '{connection.name}' — vérifiez verify")`
  - `httpx.ConnectError` / `httpx.TimeoutException` → `ConnError(<message réseau clair>)`
  - `404` → `NotFoundError` (l'appelant ajoute le nom de la ressource)
  - `400` → `ApiError` portant le message d'erreur renvoyé par l'API
  - `2xx` → `resp.json()`
  - Ces exceptions dérivent d'une base `AtlassianError(Exception)`. Le runner les
    attrape comme n'importe quelle exception de provider → `BlockError`.
- `paginate(connection, path, params, *, key, start_param, limit_param, hard_cap) -> Iterator[dict]` :
  gère les deux styles de pagination (Bitbucket/Bamboo : `start`/`limit`/`isLastPage`
  ou `nextPageStart` ; Jira : `startAt`/`maxResults`/`total`). Deux petites
  fonctions dédiées plutôt qu'une seule sur-paramétrée si c'est plus clair —
  décision d'implémentation.
- `strip_html(s: str) -> str` : nettoie les fragments HTML de Bamboo
  (`buildReason`).
- `dig(obj, path)` : accès pointé simple (réutilise / factorise celui de
  `providers/http.py`).
- `field_record(...)` : helpers de construction de `Record` partagés par les
  trois modules pour le mapping « nom de champ → `Field` typé ».
- `resolve_repos(connection, *, repo, repos, project) -> list[tuple[str, str]]` :
  exactement une des trois formes ; `project` → `GET /rest/api/1.0/projects/{key}/repos`
  paginé.
- `count_record(title, count, *, warn_above, error_above) -> Record` : record
  compteur commun (Jira/Bitbucket) — `title` + `count` (`number`, `role=badge`,
  `summary`) ; `count > error_above` → statut rouge, `> warn_above` → orange.

Un module en échec ne doit pas empêcher `providers/__init__.py` de charger les
autres — mais comme ce sont des imports statiques, une erreur d'import est un
bug à corriger, pas un cas géré.

## 6. Providers Jira — `pyminidash/providers/jira.py`

API : Jira Server/DC REST v2, `GET /rest/api/2/search` (`jql`, `fields`,
`maxResults`, `startAt`).

### Mapping des champs

`fields` est une liste de noms de champs Jira. Mapping intégré :

| Nom | Rendu |
|---|---|
| `key` | `Field` `role=title`, `type=link`, `url = f"{base_url}/browse/{key}"` |
| `summary` | `text` |
| `status` | `status` ; niveau **heuristique** : nom ∈ {Done, Closed, Resolved, Terminé, Fermé} → `OK` ; ∈ {Blocked, Impediment, Bloqué} → `ERROR` ; sinon `NEUTRAL` |
| `assignee`, `reporter` | `text` = `displayName` ; « Non assigné » si `null` |
| `priority` | `text` = `priority.name` |
| `issuetype`, `resolution` | `text` = `.name` |
| `labels` | `text` = `", ".join(labels)` |
| `components`, `fixVersions` | `text` = `", ".join(x.name)` |
| `created`, `updated` | `datetime` (parse ISO 8601) |
| `parent` | `text` = `parent.key` |
| `customfield_XXXXX` | `text` = `str(value)` (`", ".join` si liste) |
| autre | tenté sous `fields.<nom>`, `text` = `str(value)` ; `""` si absent |

Ordre des colonnes = ordre de `fields`. En mode card, le champ `key` (s'il est
présent) porte `role=title`.

### `jira_jql(connection, jql, fields, max_results=50)`

- `fields` **obligatoire** (pas de défaut).
- Envoie `fields` à l'API en incluant toujours les champs nécessaires au
  mapping (ex. `status`, `assignee`). `key` est hors `fields` API (toujours
  présent dans la réponse).
- Pagination jusqu'à `min(max_results, 200)` (plafond dur 200).
- Un record par issue.

### `jira_jql_count(connection, jql, warn_above=None, error_above=None)`

- `GET /rest/api/2/search?jql=...&maxResults=0`, lit `total`.
- Renvoie **un** record via `count_record("Total", total, warn_above=..., error_above=...)`.
- Le provider ne connaît pas le titre du bloc (cohérent avec le reste du
  système) ; c'est le `title` du bloc, dans la barre de la card, qui nomme le
  compteur.

### `jira_my_issues(connection, fields=["key", "summary", "status", "priority", "updated"], max_results=50)`

- JQL figé :
  `assignee = currentUser() AND resolution = Unresolved ORDER BY updated DESC`.
- `currentUser()` est résolu côté serveur Jira à partir du token → pas besoin de
  `connection.user`.
- Sinon identique à `jira_jql` (`fields` a un défaut mais reste surchargeable).

### Erreurs Jira

`400` → message d'erreur JQL renvoyé par Jira (`errorMessages[0]`). `401/403` →
message d'auth standard. Réseau/TLS → messages standard de `_atlassian`.

## 7. Providers Bitbucket — `pyminidash/providers/bitbucket.py`

API : Bitbucket Server REST 1.0.

### Résolution de portée

`repo = "ABC/monrepo"` **ou** `repos = ["ABC/r1", "ABC/r2"]` **ou**
`project = "ABC"`. Exactement une des trois (sinon `ConfigError` via la
validation des params — géré par `resolve_repos` qui lève, attrapé côté
provider et re-levé en message clair, ou contrôlé en amont ; décision
d'implémentation, le comportement observable est : message clair).

### `bitbucket_pr(connection, repo=None, repos=None, project=None, state="OPEN", role=None, fields=[...], stale_days=None, max_results=50)`

- `state` ∈ `OPEN` (défaut), `MERGED`, `DECLINED`, `ALL`.
- `role` ∈ `None`, `"REVIEWER"`, `"AUTHOR"` — si non-`None`, ajoute
  `role.1=<role>&username.1=<connection.user>` ; exige `connection.user`.
- `GET /rest/api/1.0/projects/{proj}/repos/{slug}/pull-requests` paginé
  (`start`/`limit`, `isLastPage`/`nextPageStart`), agrégé sur tous les dépôts
  résolus, trié par `updatedDate` desc, tronqué à `min(max_results, 200)`.
- `stale_days` : filtre client — ne garde que les PR dont `updatedDate` est plus
  vieux que `now - stale_days`.
- `fields` défaut : `["id", "title", "author", "reviewers", "branches", "updated"]`.

Mapping :

| Nom | Rendu |
|---|---|
| `id` | `role=title`, `type=link`, `url = links.self[0].href` ; libellé `#<id>` |
| `title` | `text` |
| `author` | `text` = `author.user.displayName` |
| `reviewers` | `status` : tous `approved` → `OK` (« 3/3 ✓ ») ; ≥1 `status == "NEEDS_WORK"` → `WARN` (« needs work ») ; sinon `NEUTRAL` (« 1/3 ✓ ») |
| `branches` | `text` = `f"{fromRef.displayId} → {toRef.displayId}"` |
| `state` | `status` : `OPEN` → `NEUTRAL`, `MERGED` → `OK`, `DECLINED` → `ERROR` |
| `updated`, `created` | `datetime` (epoch ms → datetime) |
| `comments` | `number` = `properties.commentCount` |
| `tasks` | `number` = `properties.openTaskCount` |
| `build` | **1 appel** `GET /rest/build-status/1.0/commits/{fromRef.latestCommit}` → `status` : `SUCCESSFUL` → `OK`, `FAILED` → `ERROR`, `INPROGRESS` → `NEUTRAL`, aucun → « — » |
| `mergeable` | **1 appel** `GET .../pull-requests/{id}/merge` → `status` : `canMerge` → `OK` (« mergeable »), `conflicted` → `ERROR` (« conflit »), sinon `NEUTRAL` |

### `bitbucket_pr_count(connection, repo/repos/project, state="OPEN", role=None, warn_above=None, error_above=None)`

- Compte les PR correspondantes (somme sur les dépôts ; lit `size`/pagination).
- Renvoie **un** record via `count_record`.

### `bitbucket_my_review(connection, repo/repos/project, fields=["id", "title", "author", "reviewers", "updated"], max_results=50)`

- Raccourci : `role="REVIEWER"`, `state="OPEN"`. Exige `connection.user`.

### Erreurs Bitbucket

`404` (projet ou dépôt) → message avec le `KEY/slug`. Dans une agrégation
multi-dépôts, un dépôt en échec produit **un record marqueur d'erreur**
(`title` = `KEY/slug`, `status` `ERROR` = le message court) et n'interrompt pas
les autres. `401/403`, réseau, TLS → messages standard.

## 8. Providers Bamboo — `pyminidash/providers/bamboo.py`

API : Bamboo REST `/rest/api/latest/`. Le PAT en `Authorization: Bearer`
fonctionne sur Bamboo récent.

### `bamboo_plan_status(connection, plans, fields=[...])`

- `plans: list[str]` (clés `PROJ-PLAN`), **non vide** (sinon `ConfigError`).
- `GET /rest/api/latest/result/{planKey}/latest?expand=results.result` par plan.
- `fields` défaut :
  `["plan", "state", "number", "duration", "finished"]`. Optionnels :
  `trigger`, `tests`.

Mapping :

| Nom | Rendu |
|---|---|
| `plan` | `role=title`, `type=link`, `url = f"{base_url}/browse/{planResultKey}"` ; libellé `planName` |
| `state` | `status` : `Successful` → `OK`, `Failed` → `ERROR`, `InProgress`/`Unknown` → `NEUTRAL` |
| `number` | `number` = `buildNumber` |
| `duration` | `duration` = `buildDurationInSeconds` |
| `finished` | `datetime` = `buildCompletedTime` |
| `trigger` | `text` = `strip_html(buildReason)` |
| `tests` | `text` = `f"{successfulTestCount} ✓ / {failedTestCount} ✗"` |

- Plan jamais construit / `404` → record avec `state` `NEUTRAL` « — », les
  autres plans passent.

### `bamboo_user_builds(connection, user=None, max_results=25, scan=100)`

- `user` défaut `connection.user` ; si les deux `None` → erreur claire à
  l'exécution.
- `GET /rest/api/latest/result?expand=results.result&max-results={min(scan, 100)}`.
- Filtrage client : `strip_html(buildReason)` contient `user` (insensible à la
  casse). Garde les `max_results` premiers (déjà triés par l'API, plus récents
  d'abord).
- Champs (fixes) : `plan`, `state`, `number`, `finished`, `duration`.

### `bamboo_plan_health(connection, plans)`

- `plans` non vide. Un `GET .../result/{planKey}/latest` par plan (réutilise la
  logique de `bamboo_plan_status`).
- Renvoie **un** record :
  - `green` : `number` = nb de plans `Successful`
  - `red` : `number` = nb de plans `Failed`
  - `status` : `role=badge`, `summary` — `ERROR` si `red > 0`, sinon `OK`
  - `title` : `text` « Santé des plans »

### `bamboo_running(connection, plans=None, project=None)`

- `plans` (liste) **ou** `project` (clé) — exactement un.
- En file : `GET /rest/api/latest/queue?expand=queuedBuilds`.
- En cours : par plan (`plans`) ou par plan du projet (`project` →
  `GET /rest/api/latest/project/{key}?expand=plans`), lire
  `/result/{planKey}/latest` et retenir `lifeCycleState == "InProgress"`.
- Un record par build en cours ou en file. Champs : `plan`, `state`
  (`status` `NEUTRAL` : « En cours » / « En file »), `number`, `started`
  (`datetime`), `progress` (`text` = `progress.percentageCompletedPretty` si
  présent).
- `plans` vide → `ConfigError`.

### Erreurs Bamboo

`401/403`, réseau, TLS → messages standard. `404` sur un plan → traité comme
« pas de build » (marqueur, pas d'échec de bloc).

## 9. Gestion d'erreurs — récapitulatif

### Au démarrage → `ConfigError`, le serveur ne démarre pas

- `[connections.X]` : `base_url` absent/malformé ; `token` vide ; clé de token
  absente de `secrets.toml` ; `verify` = chemin inexistant.
- `secrets.toml` absent alors qu'une connexion référence un token.
- bloc : `connection` requis mais absent ; `connection` inconnu ; `connection`
  posé sur un provider qui n'en veut pas ; param invalide (inchangé).

### À l'exécution d'un bloc → `BlockError` via `_error.html`, jamais le token

- `401/403` → « authentification refusée pour la connexion 'X' — vérifiez le token ».
- Erreur TLS → « certificat TLS rejeté pour 'X' — vérifiez verify ».
- Hôte injoignable / timeout → message réseau clair.
- `404` ressource → nom de la ressource dans le message.
- `400` JQL → message renvoyé par l'API.
- `user` requis mais absent (param + `connection.user`) → message clair.
- Sous-appel en échec dans une agrégation (un dépôt, un plan) → élément marqué
  en erreur, les autres passent.

### Logs

`WARNING` pour les erreurs d'API attendues (401, 404) ; `ERROR` + traceback
pour l'inattendu. Jamais le token, jamais l'en-tête `Authorization`.

## 10. Structure du projet

```
pyminidash/
  secrets.py                 # load_secrets, SecretsError
  connection.py              # Connection, build_connections
  config.py                  # + ConnectionConfig, BlockConfig.connection, validation connexions
  runner.py                  # + injection de connection
  web/app.py                 # create_app(config, connections)
  web/routes.py              # run_block(block, app.state.connections)
  __main__.py                # + --secrets, load_secrets, build_connections, wiring
  providers/
    __init__.py              # + import jira, bitbucket, bamboo
    _atlassian.py            # get_json, pagination, strip_html, dig, resolve_repos,
                             #   count_record, AtlassianError & sous-classes, field helpers
    jira.py                  # jira_jql, jira_jql_count, jira_my_issues
    bitbucket.py             # bitbucket_pr, bitbucket_pr_count, bitbucket_my_review
    bamboo.py                # bamboo_plan_status, bamboo_user_builds, bamboo_plan_health, bamboo_running
config.example.toml          # + [connections.*] + groupe "Mon activité"
secrets.example.toml         # modèle (clés vides), committé
.gitignore                   # + secrets.toml
README.md                    # + section « Connexions et secrets »
tests/
  test_secrets.py
  test_connection.py
  test_config_connections.py
  test_runner_injection.py
  test_providers_jira.py
  test_providers_bitbucket.py
  test_providers_bamboo.py
  test_integration_atlassian.py
  fixtures/
    jira_search.json
    jira_search_count.json
    bitbucket_prs.json
    bitbucket_build_status.json
    bitbucket_merge.json
    bamboo_result_latest.json
    bamboo_results.json
    bamboo_queue.json
```

### Dépendances

Aucune nouvelle : `httpx` (déjà là), `respx` (déjà en dev). `tomllib` stdlib.

## 11. Config d'exemple

`config.example.toml` gagne :

```toml
[connections.jira]
base_url = "https://jira.interne.example.com"
token    = "jira"
verify   = "/etc/pki/ca-trust/interne.pem"

[connections.bitbucket]
base_url = "https://bitbucket.interne.example.com"
token    = "bitbucket"
user     = "jdupont"

[connections.bamboo]
base_url = "https://bamboo.interne.example.com"
token    = "bamboo"
user     = "jdupont"

[[groups]]
id = "mon-activite"
title = "Mon activité"
type = "table"

  [[groups.blocks]]
  title      = "Mes issues"
  provider   = "jira_my_issues"
  connection = "jira"

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

`secrets.example.toml` :

```toml
# Copier en secrets.toml (git-ignoré) et renseigner les PAT.
jira      = ""
bitbucket = ""
bamboo    = ""
```

## 12. Approche de test (TDD)

Chaque couche isolée, **aucun appel réseau réel** :

- **`secrets`** : fichier absent → `{}` ; présent → dict ; valeur non-string →
  `SecretsError` ; permissions larges → warning (skip Windows).
- **`connection`** : `build_connections` résout ; token manquant / CA inexistant
  → `ConfigError` ; `repr(Connection)` ne contient pas le token ; `client()`
  pose `Authorization: Bearer …` et le bon `verify`.
- **`config`** : tous les cas `ConfigError` du §9 « au démarrage ».
- **`runner`** : provider avec paramètre `connection` → instance injectée ;
  provider sans → appel inchangé.
- **providers Jira / Bitbucket / Bamboo** (`respx` + `fixtures/`) : `Record`
  produits (colonnes dans l'ordre de `fields`, types, niveaux de statut, liens,
  epoch ms → datetime pour Bitbucket) ; pagination ; filtrage client
  (`stale_days`, `bamboo_user_builds`) ; compteurs + seuils ; agrégation
  multi-dépôts avec un élément en échec ; `401` → message sans token ; `user`
  manquant → message clair ; `strip_html`.
- **intégration** : un bloc `jira_jql` monté via `Config` + `build_connections`
  (secrets de test) + `TestClient`, `respx` actif, assertion sur le fragment
  `_table.html` rendu.

## 13. Décisions arrêtées

| Sujet | Décision |
|---|---|
| Auth | PAT / `Authorization: Bearer` partout ; `basic` prévu dans le modèle, non implémenté |
| Stockage des tokens | `secrets.toml` plat, git-ignoré, à côté de `config.toml` ; `--secrets` pour surcharger |
| Divulgation | token jamais loggé / affiché / dans un message ; référence par clé ou nom de connexion |
| Connexion | section `[connections.*]` ; `connection` = champ de premier niveau du bloc |
| TLS | `verify` par connexion : `true` / chemin CA / `false` |
| Injection | le runner injecte `Connection` si la signature du provider a un paramètre `connection` |
| Client HTTP | créé/fermé par appel de provider, pas de pool persistant |
| Utilisateur courant | `connection.user` optionnel ; providers `my_*` / `me` échouent clairement s'il manque |
| Jira | `jira_jql` (`fields` obligatoire), `jira_jql_count` (+ seuils), `jira_my_issues` (JQL figé, `fields` par défaut) |
| Bitbucket | `bitbucket_pr` (dépôt/liste/projet, `state`, `role`, `stale_days`, colonnes `build`/`mergeable` optionnelles), `bitbucket_pr_count`, `bitbucket_my_review` |
| Bamboo | `bamboo_plan_status`, `bamboo_user_builds` (`user` défaut = connexion), `bamboo_plan_health`, `bamboo_running` |
| Compteurs | record unique `title` + `count` ; seuils `warn_above` / `error_above` → couleur |
| Erreur d'un sous-appel | dans une agrégation : marqueur d'erreur, les autres passent |
| Dépendances | aucune nouvelle |
| Découpage implémentation | à décider en writing-plans (possiblement 2 plans : fondation auth + Jira, puis Bitbucket + Bamboo) |
