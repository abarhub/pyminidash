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

## Connexions et secrets

Les providers Jira / Bitbucket / Bamboo passent par des **connexions**
déclarées dans `config.toml` :

    [connections.jira]
    base_url = "https://jira.interne.example.com"
    token    = "jira"          # clé dans secrets.toml
    # user   = "jdupont"       # requis par les providers "mes ..." / "moi"
    # verify = "/chemin/vers/ca-interne.pem"   # ou false pour ignorer le TLS
    #   (déconseillé : le token circule sans vérification du certificat)

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

Les colonnes optionnelles `build` / `mergeable` de `bitbucket_pr` déclenchent
un appel d'API supplémentaire par PR.

### Limites connues

- `bitbucket_pr` / `bitbucket_pr_count` plafonnent à 200 PR par dépôt ; un
  compteur saturé s'affiche `"N+"` ; quand `stale_days` est passé, les PR les
  plus anciennes sont demandées en premier (le tableau reste trié du plus
  récent au plus ancien).
- un dépôt en échec dans une agrégation (`repos` / `project`) est ignoré avec
  un log `WARNING` et le bloc s'affiche quand même ; si tous les dépôts
  échouent, le bloc passe en erreur.
- `bamboo_user_builds` filtre `user` par sous-chaîne dans le *texte* de la
  raison du build (souvent le nom affiché, pas le login) — ajuster `user` si le
  bloc est vide.
- les blocs Bitbucket / Bamboo à large portée peuvent demander un `timeout`
  explicite supérieur à 10 s.

## Providers intégrés

| Provider | Usage | Paramètres |
|---|---|---|
| `disk_usage` | table / cards | `paths: list[str]` |
| `top_processes` | table / cards | `limit: int = 10` |
| `http_check` | table / cards | `urls: list[str]`, `timeout: float = 5` |
| `http_json` | table | `url: str`, `rows_path: str`, `columns: list[str]`, `timeout: float = 5` |
| `jira_jql` | table | connexion + `jql: str`, `fields: list[str]`, `max_results: int = 50` |
| `jira_jql_count` | table | connexion + `jql: str`, `warn_above: int = None`, `error_above: int = None` |
| `jira_my_issues` | table | connexion + `fields: list[str] = None`, `max_results: int = 50` |
| `bitbucket_pr` | table | connexion + `repo` \| `repos` \| `project`, `state`, `role`, `fields`, `stale_days`, `max_results` |
| `bitbucket_pr_count` | table | connexion + `repo` \| `repos` \| `project`, `state`, `role`, `warn_above`, `error_above` |
| `bitbucket_my_review` | table | connexion + `repo` \| `repos` \| `project`, `fields`, `max_results` (exige `user`) |
| `bamboo_plan_status` | table | connexion + `plans`, `fields` |
| `bamboo_user_builds` | table | connexion + `user` (défaut = `connection.user`), `max_results`, `scan` |
| `bamboo_plan_health` | table | connexion + `plans` |
| `bamboo_running` | table | connexion + `plans` \| `project` |
| `local_projects` | table \ cards | `roots: list[str]`, `ignore: list[str] = []`, `max_depth: int = 5`, `libs: list[str] = ["guava","commons-lang3"]`, `show: list[str] = None` — poser `timeout = 60` au bloc |

Ajouter un provider : écrire une fonction décorée `@provider("nom")` dans
`pyminidash/providers/` renvoyant une `list[Record]`, et l'importer depuis
`pyminidash/providers/__init__.py`.

Un provider qui fait de l'I/O bloquante doit imposer son propre timeout : le
`timeout` du bloc borne seulement l'`await`, pas le thread worker (qui continue de
tourner jusqu'au bout même après un délai dépassé).

## Développement

```bash
uv run pytest
```

Design : `docs/superpowers/specs/2026-08-29-pyminidash-design.md`
