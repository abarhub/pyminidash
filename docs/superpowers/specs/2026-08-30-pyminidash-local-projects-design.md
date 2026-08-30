# pyminidash — Provider « inspection de projets locaux » (`local_projects`)

Date : 2026-08-30
Statut : validé en brainstorming, à relire avant plan d'implémentation
Specs précédentes :
`docs/superpowers/specs/2026-08-29-pyminidash-design.md`,
`docs/superpowers/specs/2026-08-29-pyminidash-atlassian-providers-design.md`

## 1. Objectif

Ajouter à pyminidash **un** provider, `local_projects`, qui scanne un ou
plusieurs répertoires du disque, y découvre les projets de développement
(Maven, npm/Angular, Cargo, Go, Python) et produit pour chacun une vue haut
niveau : identité et version du projet, stack technique, état Git.

But : avoir dans le dashboard un panorama de tous les projets locaux — quelle
version, quelle techno, dernier commit, y a-t-il des modifs non commitées —
sans ouvrir chaque dépôt à la main.

### Contexte

- Accès **disque local uniquement**, aucune authentification : le provider n'a
  **pas** de paramètre `connection` (comme `disk_usage` / `top_processes`).
- Dashboard local et mono-utilisateur (cf. specs précédentes).
- Ethos du projet : stdlib d'abord, pas de build, dépendances minimales.
  **Aucune nouvelle dépendance** n'est introduite.
- Git : on invoque le binaire `git` déjà présent sur la machine du
  développeur ; pas de lib Git embarquée.

### Décisions de brainstorming

- **Un seul provider** avec un schéma de record **commun et fixe** (option A),
  pas un provider par écosystème. Les infos spécifiques à une techno sont
  fusionnées dans quelques champs composites en texte.
- **Pas de détail par sous-module.** Un dépôt multi-module = **un seul
  record** ; la liste des modules et l'info frontend sont repliées dans la
  card du projet racine.
- Affichage sélectif via le mécanisme de card à 2 niveaux (résumé / « afficher
  plus ») **plus** un paramètre `show` (liste blanche de champs).

### Hors périmètre (YAGNI)

- `git fetch` / comparaison réseau avec le remote. Le champ `sync` se limite à
  l'état local issu du dernier `fetch` (`@{upstream}`).
- Détail par sous-module / sous-projet (versions de chaque sous-pom, etc.).
- Équivalent de `libs` pour npm/Cargo/Go (`package.json` porte déjà
  Angular/Material en dur). Un `npm_libs` pourra être ajouté plus tard.
- Gradle, sbt, Make, autres build tools.
- Exécution de `setup.py` ou de `mvn` (analyse statique de fichiers seulement).
- Watch / rafraîchissement automatique.
- Vérification que les chemins `roots` existent **au démarrage** (ils peuvent
  dépendre de la machine).

## 2. Configuration

```toml
[[groups.blocks]]
provider = "local_projects"
title    = "Projets locaux"
params   = {
  roots     = ["D:/projet", "D:/work"],
  ignore    = ["archive-*", "sandbox"],
  max_depth = 5,
  libs      = ["guava", "commons-lang3", "jackson-databind"],
  # show    = ["name", "version", "branch", "dirty", "stack"],
}
```

| Param | Type | Défaut | Rôle |
|---|---|---|---|
| `roots` | `list[str]` | — (**obligatoire, ≥ 1**) | Répertoires racine à scanner. |
| `ignore` | `list[str]` | `[]` | Globs matchés sur le **nom** du répertoire (pas le chemin complet). |
| `max_depth` | `int` | `5` | Profondeur max de descente sous chaque `root` (`depth 0` = le root). |
| `libs` | `list[str]` | `["guava", "commons-lang3"]` | `artifactId` Maven à rechercher dans les dépendances → champ `libs`. |
| `show` | `list[str] \| None` | `None` | Liste blanche de champs (cf. §6). `None` → schéma complet à 2 niveaux. |

### Validation au démarrage

- Portée par le mécanisme existant `validate_params` (signature du provider) :
  `roots` manquant, param inconnu, mauvaise arité → `ConfigError`.
- **Nouveau mécanisme** (cf. §7) : validation sémantique spécifique au
  provider. Pour `local_projects` : toute clé de `show` absente de la liste des
  16 champs connus → `ConfigError` localisant le bloc fautif.
- Les valeurs de `roots` ne sont **pas** vérifiées sur disque au démarrage.

## 3. Découverte (`discovery.py`)

### API

```python
@dataclass(frozen=True)
class ProjectDir:
    path: Path            # absolu, normalisé
    name: str             # nom "provisoire" = basename ; raffiné par les parsers
    types: tuple[str, ...]  # ex. ("maven", "npm") en ordre de priorité

def find_projects(roots: list[str], ignore: list[str], max_depth: int) -> list[ProjectDir]
```

### Répertoires toujours ignorés (en dur, non configurable)

```
target  node_modules  node  .venv  .venv2  .env  .git  dist  build  .idea  .gradle
```

### Marqueurs → tokens de type

| Fichier / sous-dossier présent | Token |
|---|---|
| `pom.xml` | `maven` |
| `package.json` | `npm` |
| `Cargo.toml` | `cargo` |
| `go.mod` | `go` |
| `pyproject.toml` ou `setup.py` | `python` |
| sous-dossier `.venv` / `.venv2` / `.env` | `python` |

Ordre de priorité (pour `version` composite et affichage de `type`) :
`maven, cargo, go, npm, python`. `type` liste **tous** les tokens présents,
joints par ` + ` (ex. `maven + npm`).

### Algorithme

DFS depuis chaque `root` (`depth 0` = le root lui-même) :

1. Si le basename du dossier ∈ ignorés-en-dur **ou** matche un glob `ignore` →
   on saute entièrement (ni projet, ni descente). **Exception : le `root`
   lui-même n'est jamais sauté.**
2. On teste les marqueurs dans le dossier courant.
3. ≥ 1 marqueur → c'est un **projet**, on l'enregistre et **on ne descend
   plus**.
4. Sinon, si `depth < max_depth`, on descend dans les sous-dossiers.
5. **Dédup** sur `path` absolu normalisé : si le même dossier est atteint via
   deux `roots` qui se recouvrent, il n'apparaît qu'une fois.
6. Tri final des résultats par `name` (insensible à la casse), puis par `path`.
7. Zéro projet trouvé → le provider renvoie `[]` → bloc « aucune donnée »
   (comportement existant du runner / des templates).

### Exécution

- Un `root` inexistant ou non-répertoire → `ProviderError` listant les roots
  fautifs (échec net, pas de silence).
- Erreur d'accès (permission) sur un sous-dossier pendant le scan → sous-dossier
  ignoré, log `WARNING`, le scan continue.

## 4. Infos Git (`gitinfo.py`)

### API

```python
@dataclass(frozen=True)
class GitInfo:
    branch: str            # "(HEAD détachée)" si détaché
    dirty_count: int       # lignes de fichiers modifiés/non suivis
    ahead: int | None
    behind: int | None
    upstream: str | None   # ex. "origin/main"
    commit_hash_short: str
    commit_date: datetime  # tz-aware (committer date, %cI)
    commit_subject: str
    branches: tuple[str, ...]   # branches locales
    remotes: tuple[str, ...]    # "nom url", uniques

def git_info(path: Path) -> GitInfo | None
```

### Implémentation

- `subprocess.run([...], cwd=path, capture_output=True, text=True, check=False,
  timeout=5)`.
- `git` absent du PATH (détecté une fois, mis en cache pour le run) **ou**
  `path` hors d'un dépôt → `git_info` renvoie `None` → tous les champs Git
  vides, le record est produit quand même.

| Donnée | Commande | Extraction |
|---|---|---|
| branche + ahead/behind + fichiers modifiés | `git status --porcelain=v2 --branch` | lignes `# branch.head <nom>`, `# branch.ab +A -B`, `# branch.upstream <u>`, et lignes de fichiers (comptées) |
| dernier commit | `git log -1 --format=%h%n%cI%n%s` | hash court, date ISO (→ `datetime`), sujet |
| branches locales | `git for-each-ref --format=%(refname:short) refs/heads` | liste |
| remotes | `git remote -v` | paires `nom url` dédupliquées |

- 4 invocations `git` par projet. Budget : ~40 projets tiennent largement sous
  le timeout 10 s du runner. Si le scan est plus gros, `max_depth` / `ignore`
  sont les leviers de l'utilisateur.
- `# branch.upstream` absent → `upstream = None`, `ahead/behind = None` → champ
  `sync` vide.
- Aucune connexion réseau : `ahead/behind` reflète l'état du dernier `fetch`.

## 5. Parsers écosystèmes

Chaque parser renvoie une dataclass `frozen` dédiée ; **aucun ne lève
d'exception** : fichier illisible/malformé → info partielle + drapeau/note,
jamais de bloc en erreur.

### 5.1 `maven.py` — `parse_maven(project_dir) -> MavenInfo`

`pom.xml` via `xml.etree.ElementTree`, namespace POM géré par wildcard `{*}`.

- **Identité** : `groupId`, `artifactId`, `version`, `<name>`. `groupId` et
  `version` hérités du `<parent>` si absents du pom courant.
- **Parent** : `groupId:artifactId:version` du bloc `<parent>`.
- **Interpolation `${…}`** :
  - dict de propriétés = `<properties>` + builtins `project.version`,
    `project.groupId`, `project.artifactId` ;
  - si `<parent>` a un pom sur disque (via `<relativePath>`, défaut
    `../pom.xml`) : on le charge et on fusionne ses `<properties>` (celles de
    l'enfant priment), en remontant jusqu'à **3 niveaux** ;
  - résolution en 2 passes (propriétés imbriquées) ; `${x}` non résolu →
    laissé littéral.
- **Java** : 1er trouvé parmi `maven.compiler.release`,
  `maven.compiler.source`, `java.version` (properties) ; sinon `<release>` /
  `<source>` de la config du `maven-compiler-plugin`.
- **Spring Boot** : version du `<parent>` si artifactId
  `spring-boot-starter-parent` ; sinon version de `spring-boot-dependencies`
  en `<dependencyManagement>` ; sinon version du plugin
  `org.springframework.boot:spring-boot-maven-plugin`.
- **Modules** : `<modules><module>` → liste.
- **libs** (piloté par le param `libs`) : pour chaque `artifactId` demandé,
  recherche dans `<dependencies>` puis `<dependencyManagement>` → `nom
  version` (version interpolée ; `managed` si gérée sans version explicite,
  `—` si introuvable → non listée).
- **frontend-maven-plugin** : recherché dans `<build><plugins>` et
  `<build><pluginManagement>` (artifactId `frontend-maven-plugin`) → version ;
  `nodeVersion` / `npmVersion` lus dans sa `<configuration>` (niveau plugin ou
  dans une `<execution>`).
- **Sous-scan Angular** : depuis le dossier du projet Maven, parcours des
  sous-dossiers (mêmes ignorés-en-dur, profondeur 3) → 1er `package.json`
  contenant `@angular/core` → version Angular pour le champ `stack`.
- `pom.xml` illisible → `MavenInfo(readable=False)` ; le record se construit,
  `maven_coords = "pom illisible"`.

### 5.2 `node.py` — `parse_node(dir) -> NodeInfo`

`package.json` via `json`. `name`, `version`. `@angular/core` et
`@angular/material` cherchés dans `dependencies` puis `devDependencies` ;
préfixes `^ ~ >= <= >` retirés pour ne garder que la version. JSON invalide →
`NodeInfo(readable=False)`.

### 5.3 `cargo.py` — `parse_cargo(dir) -> CargoInfo`

`Cargo.toml` via `tomllib`. `[package]` : `name`, `version`, `edition`,
`rust-version`. Fichier `[workspace]` sans `[package]` → `name` = nom du
dossier, `members` → champ `modules`.

### 5.4 `gomod.py` — `parse_gomod(dir) -> GoInfo`

`go.mod` ligne à ligne : `module <path>` (`name` = dernier segment du path),
`go <version>`.

### 5.5 `python.py` — `parse_python(dir) -> PythonInfo`

`pyproject.toml` via `tomllib` : `[project]` (PEP 621) puis `[tool.poetry]` →
`name`, `version`. Pas de `pyproject.toml` mais `setup.py` → regex best-effort
sur `name=` / `version=` (jamais exécuté). `.venv` seul → `name` = nom du
dossier, `version` vide.

## 6. Assemblage du Record (`record.py`)

### Schéma — 16 champs, ordre fixe, **toutes les clés toujours présentes**

| # | Clé | Type de Field | Tier | Contenu |
|---|---|---|---|---|
| 1 | `name` | text, role `title` | résumé | `<name>` du pom / `name` du manifeste / nom du dossier |
| 2 | `type` | text, role `badge` | résumé | `maven + npm` |
| 3 | `version` | text | résumé | version prioritaire (maven > cargo > go > npm > python) |
| 4 | `branch` | text | résumé | branche Git courante |
| 5 | `dirty` | status | résumé | `OK "propre"` / `WARN "N modifié(s)"` |
| 6 | `last_commit` | text | résumé | date relative : « aujourd'hui », « il y a 3 h », « il y a 2 j », « il y a 5 sem » |
| 7 | `path` | text | replié | chemin absolu du projet |
| 8 | `commit_detail` | text | replié | `a1b2c3d · 2026-08-28 14:03 · "sujet du commit"` |
| 9 | `sync` | text | replié | `↑2 ↓0 vs origin/main` (vide si pas d'upstream) |
| 10 | `branches` | text | replié | branches locales, séparées par `, ` (cap 20 puis `+N`) |
| 11 | `remotes` | text | replié | `origin git@… , upstream https://…` |
| 12 | `stack` | text | replié | `Java 17 · Spring Boot 3.2.1 · Angular 17.0 · Angular Material 17.0 · Go 1.22 · Rust edition 2021` (parties non vides) |
| 13 | `maven_coords` | text | replié | `com.example:mon-appli:1.4.0 — parent org.springframework.boot:spring-boot-starter-parent:3.2.1` |
| 14 | `modules` | text | replié | `core, api, web` (modules Maven ou membres du workspace Cargo) |
| 15 | `libs` | text | replié | `guava 33.0.0, commons-lang3 3.14.0` |
| 16 | `frontend_build` | text | replié | `frontend-maven-plugin 1.15.0 · node 20.11.0 · npm 10.2.4` (parties présentes) |

- Champ vide = `Field` avec `value=""` (ou `None`). Homogénéité garantie : un
  **seul** constructeur `to_record(...)` produit toujours les 16 clés dans le
  même ordre.
- Date relative (`last_commit`) calculée en Python à partir de `commit_date`,
  par rapport à `datetime.now(tz)` ; buckets : `< 1 min` → « à l'instant »,
  minutes, heures, jours, semaines, mois, années.

### Paramètre `show`

- `None` → les 16 champs, tiers résumé/replié ci-dessus.
- Liste → le record ne contient **que** les champs listés, **dans l'ordre
  donné**, tous marqués `summary=True` (affichage à plat, sans « afficher
  plus ») ; `name` conserve le rôle `title` et `type` le rôle `badge` s'ils
  sont présents. `name` est ajouté en tête d'office s'il manque.
- Homogénéité toujours garantie (tous les records filtrés sur la même liste).
- Clé inconnue → `ConfigError` au démarrage (cf. §7).

## 7. Validation config spécifique au provider (nouveau mécanisme)

Petite extension du registre, réutilisable par les futurs providers.

```python
# registry.py
@dataclass(frozen=True)
class ProviderDef:
    name: str
    func: Callable[..., list]
    signature: inspect.Signature
    validate: Callable[[dict], None] | None = None   # nouveau

def provider(name: str, *, validate: Callable[[dict], None] | None = None): ...
```

```python
# config.py, dans _cross_checks, après validate_params(...)
if pdef.validate is not None:
    try:
        pdef.validate(block.params)
    except ValueError as exc:
        raise ValueError(f"{where}: {exc}") from None
```

`local_projects` fournit :

```python
_KNOWN_FIELDS = ("name","type","version","branch","dirty","last_commit","path",
    "commit_detail","sync","branches","remotes","stack","maven_coords",
    "modules","libs","frontend_build")

def _validate_cfg(params: dict) -> None:
    show = params.get("show")
    if show is None:
        return
    if not isinstance(show, list) or not all(isinstance(s, str) for s in show):
        raise ValueError("show doit être une liste de chaînes")
    unknown = [s for s in show if s not in _KNOWN_FIELDS]
    if unknown:
        raise ValueError(
            f"show : champ(s) inconnu(s) {unknown} ; connus : {', '.join(_KNOWN_FIELDS)}")
```

Les providers existants n'ajoutent pas de `validate` — comportement inchangé.

## 8. Rendu — masquage des champs repliés vides (`web/render.py`)

Aujourd'hui `to_cards` place tout champ non-résumé/non-titre/non-badge dans
`hidden_fields`, y compris vides → `<dd>` vide affiché. Modification :

```python
elif f.summary:
    summary.append(f)
elif format_value(f) == "" and f.url is None and f.type is not FieldType.STATUS:
    continue                     # champ replié vide → ignoré
else:
    hidden.append(f)
```

- Les champs **résumé** restent affichés même vides (rare, mais cohérent —
  colonnes stables).
- `to_table` **inchangé** : la vue tableau conserve toutes ses colonnes
  (cellules vides tolérées, c'est la vue power-user, typiquement avec `show`).
- Bénéficie à tous les providers en mode cards ; considéré comme une
  amélioration.

## 9. Structure des fichiers

```
pyminidash/providers/localproj/
  __init__.py    @provider("local_projects", validate=_validate_cfg) ; orchestration ; _KNOWN_FIELDS
  discovery.py   ProjectDir, find_projects
  gitinfo.py     GitInfo, git_info
  maven.py       MavenInfo, parse_maven
  node.py        NodeInfo, parse_node
  cargo.py       CargoInfo, parse_cargo
  gomod.py       GoInfo, parse_gomod
  python.py      PythonInfo, parse_python
  record.py      to_record  (schéma 16 champs + application de `show`), _relative_date
```

Modifications hors sous-package :

- `pyminidash/providers/__init__.py` : `from pyminidash.providers import ... localproj`.
- `pyminidash/registry.py` : champ `validate` sur `ProviderDef`, param `validate`
  du décorateur.
- `pyminidash/config.py` : appel de `pdef.validate` dans `_cross_checks`.
- `pyminidash/web/render.py` : masquage des champs repliés vides.
- `config.example.toml` : bloc d'exemple `local_projects`.
- `README.md` : ligne dans le tableau des providers.
- `docs/ETAT.md` : mise à jour (provider livré, dette « projet local » close).

## 10. Orchestration du provider

```python
@provider("local_projects", validate=_validate_cfg)
def local_projects(roots, ignore=None, max_depth=5, libs=None, show=None) -> list[Record]:
    ignore = ignore or []
    libs = libs if libs is not None else ["guava", "commons-lang3"]
    projects = find_projects(roots, ignore, max_depth)   # ProviderError si root KO
    git_available = _git_on_path()
    records = []
    for proj in projects:
        parsed = _parse_all(proj, libs)          # dict token -> info ; ne lève pas
        git = git_info(proj.path) if git_available else None
        records.append(to_record(proj, parsed, git, show))
    return records
```

- Échec de parsing d'**un** projet : capturé dans `_parse_all` / `to_record`,
  record partiel + note ; jamais de bloc en erreur pour un seul projet cassé.
- Ordre déterministe (tri de `find_projects`).

## 11. Plan de tests

`tests/test_providers_localproj.py`, fixtures poms dans
`tests/fixtures/localproj/`. Lancement :
`./.venv/Scripts/python.exe -m pytest tests/test_providers_localproj.py`.

| Cible | Cas couverts |
|---|---|
| `discovery` | marqueurs imbriqués ; globs `ignore` ; ignorés-en-dur ; coupe `max_depth` ; dédup de roots recouvrants ; multi-marqueur → `maven + npm` ; arrêt au 1er marqueur ; root inexistant → `ProviderError` |
| `maven` | GAV ; héritage `groupId`/`version` du parent ; interpolation `${}` ; merge des `<properties>` d'un parent sur disque ; 3 variantes de version Java ; Spring Boot via parent **et** via `dependencyManagement` ; `<modules>` ; matching `libs` (présent / managed / absent) ; frontend-maven-plugin + node/npm ; sous-scan Angular ; `pom.xml` malformé |
| `node` / `cargo` / `gomod` / `python` | fixture minimale : cas nominal + fichier malformé ; workspace Cargo ; `.venv` seul |
| `gitinfo` | vrais dépôts créés en `tmp_path` via `subprocess` (init, commit, branche, fichier sale, `remote add`, `branch --set-upstream-to`) → `branch`, `dirty_count`, `ahead/behind`, `upstream`, `commit_*`, `branches`, `remotes` ; dossier hors dépôt → `None` ; `@pytest.mark.skipif` si `git` absent du PATH |
| `record` | Info fabriquées → jeu **et** ordre des 16 champs ; composites `stack` / `maven_coords` / `frontend_build` / `modules` / `libs` ; buckets de `_relative_date` ; application de `show` (filtrage + ordre + `name` forcé) |
| provider (intégration) | arbre `tmp_path` avec 2–3 projets hétérogènes → records **homogènes** (mêmes clés) ; `show` restreint bien les colonnes ; tri déterministe |
| `config` | bloc avec `show` contenant une clé inconnue → `ConfigError` localisée ; `roots` manquant → `ConfigError` ; provider existant sans `validate` inchangé |
| `render` | `to_cards` retire les champs repliés vides ; garde les champs résumé vides ; `to_table` inchangé |

Cible : suite globale toujours verte (`./.venv/Scripts/python.exe -m pytest`),
warnings inchangés.

## 12. Risques / points de vigilance

- **Perf sur gros arbres** : 4 `git` + N lectures de fichiers par projet.
  Atténué par `max_depth`, `ignore`, l'arrêt au 1er marqueur, et le timeout 10 s
  du runner (qui dégrade proprement en `BlockError`).
- **Interpolation Maven incomplète** : BOM importés, profils actifs, héritage
  au-delà de 3 niveaux ou parent hors disque → certaines versions resteront en
  `${...}`. Acceptable : analyse statique best-effort, jamais d'exception.
- **`git status --porcelain=v2 --branch`** : format stable et documenté depuis
  Git 2.11 ; on parse les lignes `# branch.*` défensive­ment (champ absent →
  valeur `None`).
- **Windows** : chemins avec `/` et `\` ; `Path` normalise. `git` doit être sur
  le PATH (cas nominal du poste de dev) sinon champs Git vides.
