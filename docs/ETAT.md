# pyminidash — état du projet (handoff)

Dernière mise à jour : 2026-08-30. Branche `main` @ `3e9559b`. 242 tests + 1 skip.

## Ce que c'est

Mini-dashboard web **local, mono-utilisateur** servi sur `localhost`. Un fichier
`config.toml` définit des **groupes** ; chaque groupe affiche des **tableaux** ou des
**cards** produits par des **providers** Python (catalogue intégré, pas de plugins
externes). Stack : FastAPI + HTMX (fragments rendus côté serveur, HTMX vendu, pas de
build), Pydantic v2, `tomllib`, `httpx`, `psutil`. Aucune persistance.

Lancement : `uv run pyminidash --config config.toml --port 8000 --open`

## Docs de référence

- Spec cœur : `docs/superpowers/specs/2026-08-29-pyminidash-design.md`
- Spec providers Atlassian : `docs/superpowers/specs/2026-08-29-pyminidash-atlassian-providers-design.md`
- Plans : `docs/superpowers/plans/2026-08-29-pyminidash.md`, `...-atlassian-plan-a.md`, `...-atlassian-plan-b.md`

## Architecture

```
pyminidash/
  __main__.py     CLI : --config, --secrets, --host, --port, --open
  config.py       modèles Pydantic + load_config() ; [connections.*] ; ConfigError bloque le démarrage
  secrets.py      load_secrets() lit secrets.toml (plat, git-ignoré) ; SecretsError
  connection.py   Connection (repr masque le token) + .client() httpx authentifié ; build_connections()
                  (token manquant/vide → connexion désactivée + WARNING, pas d'erreur fatale)
  errors.py       ProviderError (message affiché tel quel par le runner, sans préfixe de type)
  models.py       Field / Record + helpers (text, status, link, datetime_, number, bytes_, duration, title...)
  format.py       format_value(field) -> str (bytes humanisés, %, durées, dates...)
  registry.py     @provider("nom") + REGISTRY + get_provider + validate_params(injected=...)
  runner.py       run_block(block, connections) : exécute le provider dans un thread, timeout 10s,
                  injecte l'objet Connection si la signature a un param `connection`,
                  normalise en BlockOk / BlockError ; _check_records exige des records HOMOGÈNES
  web/
    app.py        create_app(config, connections) -> FastAPI ; app.state.{config,connections,templates}
    routes.py     GET / (redirect) ; GET /groups/{id} (coquille + placeholders) ;
                  GET /groups/{id}/blocks/{n} (fragment, exécute le provider)
    render.py     to_table() / to_cards()  (list[Record] -> structures de template)
    templates/    base, group, _table, _cards, _field, _block_head, _error, _loading
    static/       htmx.min.js (vendu), app.css, app.js
  providers/
    _atlassian.py get_json (traduit 401/403/404/400/3xx/réseau/TLS en exceptions à message propre),
                  paginate_v1 (Bitbucket Server 1.0), strip_html, epoch_ms_to_dt, parse_iso,
                  count_record(display=...), HARD_CAP=200, AtlassianError & sous-classes
    system.py     disk_usage, top_processes (psutil)
    http.py       http_check, http_json
    jira.py       jira_jql, jira_jql_count, jira_my_issues
    bitbucket.py  bitbucket_pr, bitbucket_pr_count, bitbucket_my_review
    bamboo.py     bamboo_plan_status, bamboo_user_builds, bamboo_plan_health, bamboo_running
```

**Règle d'or** : `bitbucket.py` / `bamboo.py` / `jira.py` / `_atlassian.py` n'importent
JAMAIS `connection.py` (cycle : config -> providers -> ... -> connection -> config). Le
paramètre `connection` des providers est **non typé** ; on n'utilise que `.name`,
`.base_url`, `.user`, `.client()`.

## Providers disponibles (15)

| Provider | Type | Params clés |
|---|---|---|
| `disk_usage` | table/cards | `paths` |
| `top_processes` | table/cards | `limit` |
| `http_check` | table/cards | `urls`, `timeout` |
| `http_json` | table | `url`, `rows_path`, `columns` |
| `jira_jql` | table/cards | connexion + `jql`, `fields` (obligatoire), `max_results` |
| `jira_jql_count` | card | connexion + `jql`, `warn_above`, `error_above` |
| `jira_my_issues` | table/cards | connexion + `fields`, `max_results` |
| `bitbucket_pr` | table/cards | connexion + `repo`\|`repos`\|`project`, `state`, `role`, `fields`, `stale_days` |
| `bitbucket_pr_count` | card | connexion + portée, `state`, `role`, seuils |
| `bitbucket_my_review` | table/cards | connexion (`user` requis) + portée, `fields` |
| `bamboo_plan_status` | table/cards | connexion + `plans`, `fields` |
| `bamboo_user_builds` | table/cards | connexion + `user` (défaut = connexion), `max_results`, `scan` |
| `bamboo_plan_health` | card | connexion + `plans` |
| `bamboo_running` | table/cards | connexion + `plans`\|`project` |
| `local_projects` | table/cards | `roots`, `ignore`, `max_depth`, `libs`, `show` — sans connexion ; poser `timeout = 60` au bloc |

## Connexions & secrets

```toml
# config.toml
[connections.jira]
base_url = "https://jira.interne.example.com"
token    = "jira"          # clé cherchée dans secrets.toml
# user   = "jdupont"       # requis par bitbucket_my_review, défaut de bamboo_user_builds
# verify = "/chemin/ca.pem" | false   # TLS auto-signé ; false => warning loggé

[[groups.blocks]]
provider   = "jira_jql"
connection = "jira"        # champ de premier niveau du bloc, PAS dans params
params     = { jql = "...", fields = ["key","summary","status"] }
```

```toml
# secrets.toml  (git-ignoré, à côté de config.toml, ou --secrets ; secrets.example.toml fourni)
jira      = "NjE2M..."
bitbucket = "..."
bamboo    = "..."
```

Le token n'apparaît jamais dans un log / message / rendu. Validation au démarrage :
CA introuvable, connexion inconnue, provider inexistant → `ConfigError`, le serveur ne
démarre pas. **Token absent/vide dans `secrets.toml` → la connexion est désactivée**
(WARNING au démarrage) et le serveur démarre quand même ; les blocs qui l'utilisent
s'affichent en erreur par card (`connexion '...' non initialisée`). Permet de lancer le
dashboard avec seulement les providers système / HTTP / `local_projects`.

## Historique (3 PR mergées dans main)

1. **PR #1** — cœur : config, 4 providers système/HTTP, app FastAPI + HTMX, recalcul par
   bloc + « tout recalculer », cards repliables.
2. **PR #2** (Plan A) — fondation auth (connexions, secrets, `Connection`, injection
   runner) + 3 providers Jira.
3. **PR #3** (Plan B) — 3 providers Bitbucket + 4 providers Bamboo + helpers `_atlassian`.

## Limites connues / dettes

- **Bitbucket `state="ALL"` et `order="OLDEST"`** (utilisé par `stale_days`) : implémentés
  d'après la doc REST Bitbucket Server, **jamais testés contre une instance réelle**.
- `bitbucket_pr` / `bitbucket_pr_count` plafonnent à **200 PR par dépôt** (l'API Bitbucket
  Server n'expose pas de total). Compteur saturé affiché `"N+"`.
- Agrégation multi-dépôts : un dépôt en échec est **ignoré avec un log WARNING** (pas de
  marqueur visible dans l'UI — incompatible avec la contrainte de records homogènes). Si
  *tous* échouent → bloc en erreur.
- `bamboo_user_builds` filtre `user` par **sous-chaîne dans le texte de la raison du build**
  (souvent le nom affiché, pas le login) — Bamboo n'a pas de meilleure API.
- `runner` : au timeout, le thread du provider est **abandonné, pas tué** (il finit dans le
  threadpool). Les providers HTTP portent leur propre timeout (8 s depuis Plan B).
- Résidus mineurs parkés : `role.upper()` lève `AttributeError` si le type TOML est faux
  (rattrapé en `BlockError`) ; le message « aucun dépôt accessible » interpole encore le
  chemin d'API pour une erreur **non-404**.
- `pyproject.toml` n'a **pas de linter** (ruff configuré) — quelques imports en milieu de
  fichier de test, imports inutilisés isolés.
- Warning de suite : `StarletteDeprecationWarning` (httpx/testclient de FastAPI) —
  volontairement non masqué (signal pour la future migration httpx2).

## Ce qui reste à faire

### Fait (PR #4) : provider « inspection de projets locaux »

Provider `local_projects` : découverte multi-racines (`roots`, `ignore`, `max_depth`),
parsing par écosystème (Maven / npm / Cargo / Go / Python), état Git parallélisé
(`ThreadPoolExecutor`), colonnes réglables via `show`. Sans connexion (accès disque local),
comme `disk_usage`. Spec : `docs/superpowers/specs/2026-08-30-pyminidash-local-projects-design.md`.

### Idées d'amélioration (non priorisées)

- Auth `basic` en plus de `bearer` (le modèle `ConnectionConfig.auth` la prévoit déjà).
- Cache / rafraîchissement auto sur intervalle (explicitement hors périmètre jusqu'ici).
- Valider Bitbucket `state=ALL` / `order=OLDEST` contre une vraie instance et ajuster.
- Nettoyer les dettes mineures ci-dessus (1 commit de cleanup).
- Configurer `ruff` dans `pyproject.toml`.

## Workflow utilisé

Chaque gros lot : **brainstorming** (skill) → **spec** dans `docs/superpowers/specs/` →
**writing-plans** → **subagent-driven-development** (worktree isolé, 1 sous-agent
implémenteur + 1 revue par tâche, puis revue globale de branche sur Opus + passe de
correctifs) → **finishing-a-development-branch** → PR.

Note env : `uv run pytest` peut se figer dans certains sandbox → `./.venv/Scripts/python.exe -m pytest`.
