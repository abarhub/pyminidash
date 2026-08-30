"""Analyse statique d'un pom.xml : coordonnées, Java, Spring Boot, modules,
libs demandées, frontend-maven-plugin, et sous-scan Angular."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from pyminidash.providers.localproj.discovery import ALWAYS_IGNORE
from pyminidash.providers.localproj.node import parse_node

_PROP_RE = re.compile(r"\$\{([^}]+)\}")
_SUBSCAN_DEPTH = 3


@dataclass(frozen=True)
class MavenInfo:
    readable: bool
    name: str | None
    group_id: str | None
    artifact_id: str | None
    version: str | None
    parent_gav: str | None
    java_version: str | None
    spring_boot_version: str | None
    modules: tuple[str, ...]
    libs: tuple[tuple[str, str], ...]
    frontend_plugin_version: str | None
    frontend_node_version: str | None
    frontend_npm_version: str | None
    angular_version: str | None
    angular_material_version: str | None


_UNREADABLE = MavenInfo(False, None, None, None, None, None, None, None,
                        (), (), None, None, None, None, None)


def _txt(el: ET.Element | None, tag: str) -> str | None:
    if el is None:
        return None
    child = el.find(f"{{*}}{tag}")
    return child.text.strip() if child is not None and child.text else None


def _load_properties(pom_path: Path, root: ET.Element, depth: int = 3) -> dict[str, str]:
    """Propriétés du pom + celles des parents sur disque (enfant prioritaire)."""
    props: dict[str, str] = {}
    parent_el = root.find("{*}parent")
    if depth > 0 and parent_el is not None:
        rel = _txt(parent_el, "relativePath") or "../pom.xml"
        parent_path = (pom_path.parent / rel).resolve()
        if parent_path.is_file():
            try:
                proot = ET.parse(parent_path).getroot()
                props.update(_load_properties(parent_path, proot, depth - 1))
            except (OSError, ET.ParseError):
                pass
    local = root.find("{*}properties")
    if local is not None:
        for child in local:
            tag = child.tag.split("}")[-1]
            if child.text:
                props[tag] = child.text.strip()
    return props


def _interpolate(value: str | None, props: dict[str, str]) -> str | None:
    if value is None:
        return None
    for _ in range(2):  # propriétés imbriquées
        if "${" not in value:
            break
        value = _PROP_RE.sub(lambda m: props.get(m.group(1), m.group(0)), value)
    return value


def _all_deps(root: ET.Element) -> list[ET.Element]:
    # Ancré au niveau projet : <dependencies> + <dependencyManagement>/<dependencies>
    # uniquement. Exclut plugin/pluginManagement/profiles (faux positifs de version).
    return (root.findall("{*}dependencies/{*}dependency")
            + root.findall("{*}dependencyManagement/{*}dependencies/{*}dependency"))


def _plugins(root: ET.Element) -> list[ET.Element]:
    return root.findall(".//{*}plugin")


def _java_version(root: ET.Element, props: dict[str, str]) -> str | None:
    for key in ("maven.compiler.release", "maven.compiler.source", "java.version"):
        if key in props:
            return props[key]
    for plugin in _plugins(root):
        if _txt(plugin, "artifactId") == "maven-compiler-plugin":
            cfg = plugin.find("{*}configuration")
            return _txt(cfg, "release") or _txt(cfg, "source")
    return None


def _spring_boot(root: ET.Element, parent_el: ET.Element | None) -> str | None:
    if parent_el is not None and _txt(parent_el, "artifactId") == "spring-boot-starter-parent":
        return _txt(parent_el, "version")
    for dep in _all_deps(root):
        if _txt(dep, "artifactId") == "spring-boot-dependencies":
            return _txt(dep, "version")
    for plugin in _plugins(root):
        if _txt(plugin, "artifactId") == "spring-boot-maven-plugin":
            return _txt(plugin, "version")
    return None


def _frontend(root: ET.Element) -> tuple[str | None, str | None, str | None]:
    for plugin in _plugins(root):
        if _txt(plugin, "artifactId") != "frontend-maven-plugin":
            continue
        version = _txt(plugin, "version")
        node = npm = None
        # Parcours de toute config (namespacée ou non) sous le plugin.
        for cfg in plugin.iter():
            if cfg.tag.split("}")[-1] == "configuration":
                node = node or _txt(cfg, "nodeVersion")
                npm = npm or _txt(cfg, "npmVersion")
        return version, node, npm
    return None, None, None


def _angular_subscan(project_dir: Path) -> tuple[str | None, str | None]:
    def rec(d: Path, depth: int) -> tuple[str | None, str | None] | None:
        pkg = d / "package.json"
        if pkg.is_file():
            info = parse_node(d)
            if info.angular_version or info.angular_material_version:
                return info.angular_version, info.angular_material_version
        if depth <= 0:
            return None
        try:
            for entry in d.iterdir():
                if entry.is_dir() and entry.name not in ALWAYS_IGNORE:
                    hit = rec(entry, depth - 1)
                    if hit:
                        return hit
        except OSError:
            return None
        return None

    return rec(project_dir, _SUBSCAN_DEPTH) or (None, None)


def parse_maven(project_dir: Path, libs: list[str]) -> MavenInfo:
    pom = project_dir / "pom.xml"
    try:
        root = ET.parse(pom).getroot()
    except (OSError, ET.ParseError):
        return _UNREADABLE

    parent_el = root.find("{*}parent")
    props = _load_properties(pom, root)
    props.setdefault("project.version",
                     _txt(root, "version") or _txt(parent_el, "version") or "")
    props.setdefault("project.groupId",
                     _txt(root, "groupId") or _txt(parent_el, "groupId") or "")
    props.setdefault("project.artifactId", _txt(root, "artifactId") or "")

    group_id = _txt(root, "groupId") or _txt(parent_el, "groupId")
    version = _txt(root, "version") or _txt(parent_el, "version")
    parent_gav = None
    if parent_el is not None:
        parent_gav = ":".join(x or "?" for x in (
            _txt(parent_el, "groupId"), _txt(parent_el, "artifactId"),
            _txt(parent_el, "version")))

    # Dédup par artifactId : une version concrète interpolée prime sur "managed".
    found_libs_map: dict[str, str] = {}
    for dep in _all_deps(root):
        aid = _txt(dep, "artifactId")
        if aid not in libs:
            continue
        ver = _interpolate(_txt(dep, "version"), props) or "managed"
        if aid not in found_libs_map or (
            found_libs_map[aid] == "managed" and ver != "managed"
        ):
            found_libs_map[aid] = ver
    found_libs = [(a, found_libs_map[a]) for a in found_libs_map]

    fe_version, fe_node, fe_npm = _frontend(root)
    ang, ang_mat = _angular_subscan(project_dir)

    return MavenInfo(
        readable=True,
        name=_txt(root, "name"),
        group_id=group_id,
        artifact_id=_txt(root, "artifactId"),
        version=_interpolate(version, props),
        parent_gav=parent_gav,
        java_version=_interpolate(_java_version(root, props), props),
        spring_boot_version=_interpolate(_spring_boot(root, parent_el), props),
        modules=tuple(
            m.text.strip() for m in root.findall("{*}modules/{*}module")
            if m.text and m.text.strip()
        ),
        libs=tuple(found_libs),
        frontend_plugin_version=fe_version,
        frontend_node_version=fe_node,
        frontend_npm_version=fe_npm,
        angular_version=ang,
        angular_material_version=ang_mat,
    )
