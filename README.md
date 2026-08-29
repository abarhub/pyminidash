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
