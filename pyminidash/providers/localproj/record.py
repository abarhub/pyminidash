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
