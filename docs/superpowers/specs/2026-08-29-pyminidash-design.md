# pyminidash — Design

Date : 2026-08-29
Statut : validé en brainstorming, à relire avant plan d'implémentation

## 1. Objectif

Un mini-dashboard extensible, **local et mono-utilisateur**, servi comme
application web sur `localhost`. Il affiche des **groupes** définis dans un
fichier de configuration. Chaque groupe affiche soit des **tableaux**, soit des
**cards**, dont le contenu est produit par des fonctions Python appelées
**providers**.

### Contexte d'usage

- Tourne sur le PC de l'utilisateur, pour lui seul.
- Pas d'authentification, pas d'accès réseau externe entrant.
- Accès aux ressources locales (disque, processus) et aux API distantes.

### Hors périmètre (YAGNI)

Auto-refresh sur intervalle ; cache ou persistance des résultats ; surcharge de
paramètres depuis le front ; tri / filtres de colonnes ; authentification ;
plugins externes / découverte dynamique de providers.

## 2. Concepts

### Provider

Fonction Python enregistrée dans un registre global via un décorateur
`@provider("nom")`. Appelée avec des arguments nommés issus de la configuration.
Retourne une **liste de records**.

- Catalogue **intégré** uniquement : les providers vivent dans le code source du
  projet. Ajouter un provider = modifier le code. Pas de scan de plugins.
- Les providers sont **synchrones**. Le runner les exécute dans un thread
  (`asyncio.to_thread`) avec un timeout.
- Un même provider peut alimenter un tableau **ou** des cards ; c'est le groupe
  qui décide du mode de rendu.

### Record et champ

Un **record** = une ligne de tableau **ou** une card. C'est une liste ordonnée
de **champs**.

Un **champ** porte :

| Attribut  | Type                                                                        | Rôle |
|-----------|-----------------------------------------------------------------------------|------|
| `key`     | `str`                                                                       | identifiant stable, clé de colonne en mode table |
| `label`   | `str`                                                                       | libellé affiché |
| `value`   | `Any`                                                                       | valeur brute |
| `type`    | `text \| number \| bytes \| percent \| status \| link \| datetime \| duration` | pilote le formatage ; extensible |
| `role`    | `normal \| title \| badge`                                                  | cards uniquement ; ignoré en table |
| `summary` | `bool`                                                                      | cards uniquement ; `true` = visible card repliée |

- `status` porte en plus un **niveau** `ok \| warn \| error \| neutral` qui pilote
  la couleur, séparé du texte affiché.
- `link` porte une URL et un texte affiché.

Construction via des helpers courts, pas à la main :

```python
def disk_usage(paths: list[str]) -> list[Record]:
    rows = []
    for p in paths:
        u = shutil.disk_usage(p)
        pct = round(u.used / u.total * 100)
        rows.append(Record(
            title("mount", "Disque", p),
            status("percent", "%", pct, level=level_for(pct), summary=True),
            bytes_("free", "Libre", u.free, summary=True),
            bytes_("total", "Total", u.total),
            bytes_("used", "Utilisé", u.used),
        ))
    return rows
```

### Règles sur les records

- Records **homogènes** : mêmes `key`, dans le même ordre, pour tous les records
  d'un provider. Un provider qui renvoie des records hétérogènes → erreur de
  rendu du bloc.
- Liste vide → pas une erreur : le bloc affiche « aucune donnée ».
- L'ordre des champs du premier record définit l'ordre des colonnes en mode
  table.

## 3. Rendu

### Mode table

- Chaque bloc du groupe rend son **propre tableau**.
- Un champ = une cellule, formatée selon son `type` (`bytes` → « 218 GB »,
  `percent` → « 76 % », `status` → pastille colorée + texte, `link` → `<a>`,
  `datetime` → format lisible).
- `role` (`title` / `badge`) est ignoré : ces champs sont des colonnes normales.
- `summary` est ignoré.

### Mode cards

- Chaque bloc rend ses **N cards** (1 par record), regroupées sous une barre
  portant le titre du bloc, le nom du provider, l'heure du dernier calcul et un
  bouton ↻.
- Card : le champ `role=title` fait le titre ; le champ `role=badge` va en haut à
  droite ; les champs `summary=true` sont visibles quand la card est repliée ;
  les autres sont derrière « afficher plus (N) ».
- « Afficher plus / afficher moins » est un **repli purement côté navigateur**
  (toggle de classe CSS). Les champs cachés sont déjà présents dans le HTML du
  fragment ; aucun appel serveur.
- Après un recalcul, la card repart **repliée**.
- Grille multi-colonnes (responsive).

## 4. Configuration

Format **TOML**, lu par `tomllib` (stdlib, Python 3.13). Commentaires supportés.

### Exemple

```toml
[app]
title = "Mon dashboard"          # optionnel
default_group = "system"         # optionnel ; sinon le premier groupe

[[groups]]
id = "system"
title = "Système"
type = "table"                   # "table" | "cards"

  [[groups.blocks]]
  title = "Espace disque"
  provider = "disk_usage"
  params = { paths = ["C:\\", "D:\\"] }

  [[groups.blocks]]
  title = "Processus gourmands"
  provider = "top_processes"
  params = { limit = 10 }
  timeout = 5                     # optionnel ; override du timeout par défaut (s)

[[groups]]
id = "apis"
title = "Monitoring APIs"
type = "cards"

  [[groups.blocks]]
  title = "Endpoints"
  provider = "http_check"
  params = { urls = [
    "https://jsonplaceholder.typicode.com/posts/1",
    "https://jsonplaceholder.typicode.com/invalid",
  ] }

  [[groups.blocks]]
  title = "Utilisateurs"
  provider = "http_json"
  params = { url = "https://jsonplaceholder.typicode.com/users", rows_path = "$", columns = ["name", "email", "company.name"] }
```

### Schéma

- `[app]` : `title` (str, optionnel), `default_group` (str, optionnel — doit
  référencer un `id` existant).
- `[[groups]]` : `id` (str, **unique**, sert d'URL), `title` (str), `type`
  (`table` | `cards`), `blocks` (liste, ≥ 1).
- `[[groups.blocks]]` : `provider` (str, doit exister dans le registre), `params`
  (table, défaut `{}`), `title` (str, optionnel — défaut = nom du provider),
  `timeout` (nombre, optionnel — défaut global).
- Adressage des blocs pour le recalcul : **index automatique** dans la liste
  (`/groups/{id}/blocks/{n}`). Aucun `id` de bloc en config. Réordonner les blocs
  en config nécessite un rechargement de page pour resynchroniser un onglet
  ouvert.

### Validation au démarrage

Modèles Pydantic. En cas d'erreur : message clair sur stderr, **le serveur ne
démarre pas**, code de sortie ≠ 0. Cas couverts :

- fichier config introuvable ; TOML invalide
- `type` de groupe inconnu ; `id` de groupe en double
- `default_group` référence un `id` inexistant
- `provider` inexistant → message listant les providers disponibles
- paramètre requis manquant / paramètre inconnu → signature attendue du provider

Chemin de la config : argument CLI `--config` (défaut : `./config.toml`).

## 5. Serveur web

Approche : **FastAPI + HTMX**, fragments HTML rendus côté serveur. HTMX est
vendu dans `static/` (pas un package, pas de build).

### Endpoints

| Route                          | Rôle |
|--------------------------------|------|
| `GET /`                        | redirige vers `default_group` (ou le premier groupe) |
| `GET /groups/{id}`             | page complète : sidebar + coquille du groupe ; chaque bloc est un placeholder `hx-get=".../blocks/{n}" hx-trigger="load"` |
| `GET /groups/{id}/blocks/{n}`  | **fragment HTML** d'un bloc : exécute le provider, rend tableau ou cards. Sert au chargement initial et au ↻ |

- Groupe inconnu → 404. Index de bloc hors bornes → 404.

### Flux d'interaction

1. Ouverture de `/groups/{id}` → la page s'affiche immédiatement, chaque bloc en
   état « calcul en cours… ».
2. HTMX déclenche tous les fragments du groupe en parallèle ; chaque bloc se
   remplit dès que son provider répond.
3. **↻ sur un bloc** : `hx-get` sur le fragment du bloc, remplace son contenu ;
   repasse en « calcul… » pendant l'exécution. Granularité = **le provider**
   (rafraîchit ses N cards / son tableau d'un coup).
4. **« Tout recalculer »** : bouton en tête du groupe ; redéclenche le `hx-get`
   de **chaque bloc du groupe affiché uniquement** (petit script `app.js` ou
   `hx-trigger` custom). Ne touche pas aux autres groupes.
5. **« Afficher plus »** : pur client, aucun appel serveur.

### Rendu — templates Jinja

- `base.html` — coquille, sidebar (liste des groupes), inclusion de `static/`
- `group.html` — placeholders de blocs
- `_table.html` — reçoit `list[Record]` → `<table>`, colonnes dans l'ordre des
  champs
- `_cards.html` — reçoit `list[Record]` → grille de cards, split summary / caché
- `_field.html` — formate une valeur selon son `type`
- `_error.html` — état d'erreur d'un bloc
- `_loading.html` — état « calcul en cours »

`web/render.py` transforme `list[Record]` en contexte de template (colonnes
ordonnées pour la table ; titre / badge / summary / hidden pour les cards).

### Pas de persistance

Aucun cache, aucune base de données. Fermer / rouvrir un groupe relance les
providers. Les résultats ne vivent que dans le DOM du navigateur.

### Lancement

`pyminidash --config config.toml --port 8000 [--open]` démarre Uvicorn.
`--open` ouvre le navigateur sur la page d'accueil.

## 6. Gestion d'erreurs

### Au démarrage

Voir § 4 (validation de config). Le serveur refuse de démarrer sur une config
cassée.

### À l'exécution d'un bloc

Isolé : le reste du groupe continue de fonctionner. Le fragment rend
`_error.html` (cadre rouge, titre du bloc, détail, bouton ↻ pour réessayer) :

- provider qui lève une exception → type + message de l'exception
- dépassement du timeout → « timeout après N s »
- forme de retour invalide (pas une `list[Record]`, records hétérogènes) →
  message de rendu explicite, **pas** un crash serveur
- liste vide → **pas** une erreur : « aucune donnée »

### Réseau (providers HTTP)

C'est au provider de traduire :

- `http_check` attrape les erreurs de connexion / timeout et renvoie un record
  avec un `status` de niveau `error` (l'endpoint est « DOWN ») — le bloc n'est
  pas en erreur.
- `http_json` sur une réponse 5xx ou du JSON non conforme au `rows_path` /
  `columns` attendu → le bloc **est** en erreur.

### Logs

Les exceptions de providers sont loggées côté serveur avec traceback, en plus de
l'affichage navigateur.

## 7. Providers livrés

| Provider        | Usage         | Paramètres |
|-----------------|---------------|------------|
| `disk_usage`    | table + cards | `paths: list[str]` |
| `top_processes` | table + cards | `limit: int = 10` |
| `http_check`    | table + cards | `urls: list[str]`, `timeout: float = 5` |
| `http_json`     | table         | `url: str`, `rows_path: str`, `columns: list[str]`, `timeout: float = 5` |

- `disk_usage` : stdlib `shutil.disk_usage`. Champs : mount (title), percent
  (status/badge/summary), free (bytes/summary), total (bytes), used (bytes).
- `top_processes` : `psutil`, trié par CPU décroissant, tronqué à `limit`.
  Champs : pid, name (title), cpu_percent (number/badge/summary), memory
  (bytes/summary), username, status.
- `http_check` : `httpx`, une requête `GET` par URL. Champs : url (title/link),
  status (status/badge/summary) où le niveau dépend du code HTTP et des erreurs
  réseau, http_code (number/summary), latency_ms (number/summary), error (text,
  caché), checked_at (datetime, caché).
- `http_json` : `httpx` `GET` sur `url`, extraction d'une liste via `rows_path`
  (`$` = racine, sinon chemin pointé simple), une colonne par entrée de
  `columns` (chemin pointé, ex. `company.name`). Tous les champs en `text` par
  défaut.

`rows_path` et le chemin de `columns` : notation pointée simple (segments
séparés par `.`), pas de JSONPath complet. `$` désigne la racine.

## 8. Structure du projet

```
pyminidash/
  pyproject.toml
  config.example.toml
  pyminidash/
    __init__.py
    __main__.py            # CLI : --config, --port, --open
    config.py              # tomllib + modèles Pydantic + validation
    models.py              # Record, Field, FieldType, StatusLevel + helpers
    registry.py            # @provider, REGISTRY, ProviderDef (signature)
    runner.py              # bloc -> to_thread -> timeout -> list[Record] | BlockError
    providers/
      __init__.py          # importe system, http pour déclencher l'enregistrement
      system.py            # disk_usage, top_processes
      http.py              # http_check, http_json
    web/
      app.py               # create_app(config) -> FastAPI
      routes.py            # / , /groups/{id} , /groups/{id}/blocks/{n}
      render.py            # list[Record] -> contexte template
      templates/           # base, group, _table, _cards, _field, _error, _loading
      static/              # htmx.min.js (vendu), app.css, app.js
  tests/
    test_config.py
    test_registry.py
    test_runner.py
    test_providers.py
    test_render.py
    test_routes.py
```

### Dépendances

- Runtime : `fastapi`, `uvicorn[standard]`, `jinja2`, `httpx`, `psutil`
  (`pydantic` tiré par `fastapi`).
- Dev : `pytest`, `pytest-asyncio`, `respx` (mock `httpx`).
- `tomllib` = stdlib. HTMX vendu dans `static/`.

## 9. Approche de test (TDD)

Chaque couche testée en isolation :

- **providers** : appelés en direct → assertions sur les `Record` (`http_check` /
  `http_json` avec `respx`).
- **runner** : provider qui lève → `BlockError` ; timeout respecté ; forme de
  retour invalide → `BlockError`.
- **config** : chaque cas d'erreur de validation du § 4 ; config valide → modèle
  attendu.
- **registry** : enregistrement via décorateur ; validation des params contre la
  signature.
- **render** : `list[Record]` → colonnes dans l'ordre (table) ; split summary /
  caché et sélection title / badge (cards).
- **routes** : `TestClient` ; page de groupe rend les placeholders ; fragment
  contient les bonnes cellules ; groupe inconnu → 404 ; provider qui lève → le
  fragment contient le cadre d'erreur.

## 10. Décisions arrêtées

| Sujet | Décision |
|-------|----------|
| Public / déploiement | Local, mono-utilisateur, pas d'auth |
| Front | Application web, FastAPI + HTMX, fragments serveur, pas de build |
| Paramètres des providers | Config uniquement, pas de surcharge front |
| Catalogue de providers | Intégré uniquement, extension = modif du code |
| Un provider → N records | 1 record = 1 ligne de table **ou** 1 card |
| Provider polyvalent | Le même provider marche en table et en cards |
| Recalcul | Granularité = le provider ; bouton global limité au groupe affiché |
| Chargement d'un groupe | Calcule tout automatiquement à l'ouverture, indicateurs de chargement |
| Persistance | Aucune |
| Format de config | TOML (`tomllib`, stdlib) |
| Adressage des blocs | Index automatique |
| Dépendances système | `psutil` inclus dès le départ |
