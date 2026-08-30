"""Provider `local_projects` : inspection de projets locaux (disque + Git)."""
from __future__ import annotations

import logging
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

log = logging.getLogger("pyminidash.localproj")


def _validate_cfg(params: dict) -> None:
    show = params.get("show")
    if show is not None:
        if not isinstance(show, list) or not all(isinstance(s, str) for s in show):
            raise ValueError("show doit être une liste de chaînes")
        unknown = [s for s in show if s not in KNOWN_FIELDS]
        if unknown:
            raise ValueError(
                f"show : champ(s) inconnu(s) {unknown} ; "
                f"connus : {', '.join(KNOWN_FIELDS)}"
            )
        dupes = sorted({s for s in show if show.count(s) > 1})
        if dupes:
            raise ValueError(f"show : clé(s) en double {dupes}")

    # `roots` peut être absent ici : validate_params (bind de signature) a déjà
    # traité le cas « argument requis manquant ». On ne valide que si présent.
    if "roots" in params:
        roots = params["roots"]
        if (not isinstance(roots, list) or not roots
                or not all(isinstance(r, str) for r in roots)):
            raise ValueError("roots doit être une liste non vide de chaînes")


def _parse_all(project: ProjectDir, libs: list[str]) -> ParsedProject:
    t = project.types

    def _safe(name: str, fn):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - un parser ne doit jamais tuer le bloc
            log.warning("parser %s a échoué pour %s : %s", name, project.path, exc)
            return None

    return ParsedProject(
        maven=_safe("maven", lambda: parse_maven(project.path, libs)) if "maven" in t else None,
        node=_safe("node", lambda: parse_node(project.path)) if "npm" in t else None,
        cargo=_safe("cargo", lambda: parse_cargo(project.path)) if "cargo" in t else None,
        go=_safe("go", lambda: parse_gomod(project.path)) if "go" in t else None,
        python=_safe("python", lambda: parse_python(project.path)) if "python" in t else None,
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

    records = [to_record(pr, pa, g, show)
               for pr, pa, g in zip(projects, parsed, gits)]
    # Tri sur le `name` RENDU (manifeste/pom), toujours présent même sous `show`.
    # `find_projects` garde son propre tri comme départage stable.
    records.sort(key=lambda r: next(
        f.value for f in r.fields if f.key == "name").lower())
    return records
