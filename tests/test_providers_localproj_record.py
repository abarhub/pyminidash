from datetime import datetime, timedelta, timezone
from pathlib import Path

from pyminidash.models import FieldRole
from pyminidash.providers.localproj.discovery import ProjectDir
from pyminidash.providers.localproj.gitinfo import GitInfo
from pyminidash.providers.localproj.maven import MavenInfo
from pyminidash.providers.localproj.node import NodeInfo
from pyminidash.providers.localproj.record import (
    KNOWN_FIELDS, ParsedProject, relative_date, to_record,
)

_EMPTY = ParsedProject(None, None, None, None, None)


def _proj(types=("maven",)):
    return ProjectDir(Path("/x/app"), "app", types)


def _maven(**kw):
    base = dict(readable=True, name="Mon Appli", group_id="com.ex",
                artifact_id="app", version="1.4.0", parent_gav=None,
                java_version="17", spring_boot_version="3.2.1", modules=("core",),
                libs=(("guava", "33.0.0"),), frontend_plugin_version=None,
                frontend_node_version=None, frontend_npm_version=None,
                angular_version=None, angular_material_version=None)
    base.update(kw)
    return MavenInfo(**base)


def _git(**kw):
    base = dict(branch="main", dirty_count=0, ahead=2, behind=0,
                upstream="origin/main", commit_hash_short="a1b2c3d",
                commit_date=datetime(2026, 8, 28, 14, 3, tzinfo=timezone.utc),
                commit_subject="Fix null check", branches=("main", "dev"),
                remotes=("origin git@x:me/app.git",))
    base.update(kw)
    return GitInfo(**base)


def test_full_schema_keys_and_order():
    rec = to_record(_proj(), ParsedProject(_maven(), None, None, None, None),
                    _git(), None)
    assert rec.keys() == KNOWN_FIELDS


def test_homogeneous_across_types():
    a = to_record(_proj(("maven",)), ParsedProject(_maven(), None, None, None, None),
                  _git(), None)
    b = to_record(ProjectDir(Path("/x/g"), "g", ("go",)), _EMPTY, None, None)
    assert a.keys() == b.keys()


def test_title_and_badge_roles():
    rec = to_record(_proj(("maven", "npm")),
                    ParsedProject(_maven(), None, None, None, None), _git(), None)
    by = {f.key: f for f in rec.fields}
    assert by["name"].role is FieldRole.TITLE
    assert by["name"].value == "Mon Appli"
    assert by["type"].role is FieldRole.BADGE
    assert by["type"].value == "maven + npm"


def test_composites():
    rec = to_record(_proj(), ParsedProject(_maven(), None, None, None, None),
                    _git(), None)
    by = {f.key: f for f in rec.fields}
    assert by["stack"].value == "Java 17 · Spring Boot 3.2.1"
    assert by["maven_coords"].value == "com.ex:app:1.4.0"
    assert by["modules"].value == "core"
    assert by["libs"].value == "guava 33.0.0"
    assert by["sync"].value == "↑2 ↓0 vs origin/main"
    assert by["commit_detail"].value.startswith("a1b2c3d · 2026-08-28 14:03")


def test_dirty_levels():
    from pyminidash.models import StatusLevel
    clean = {f.key: f for f in to_record(_proj(), _EMPTY, _git(dirty_count=0), None).fields}
    dirty = {f.key: f for f in to_record(_proj(), _EMPTY, _git(dirty_count=3), None).fields}
    none = {f.key: f for f in to_record(_proj(), _EMPTY, None, None).fields}
    assert clean["dirty"].value == "propre" and clean["dirty"].level is StatusLevel.OK
    assert dirty["dirty"].value == "3 modifiés" and dirty["dirty"].level is StatusLevel.WARN
    assert none["dirty"].value == "" and none["dirty"].level is StatusLevel.NEUTRAL


def test_show_filters_and_orders():
    rec = to_record(_proj(), ParsedProject(_maven(), None, None, None, None),
                    _git(), ["version", "stack"])
    assert rec.keys() == ("name", "version", "stack")   # name forcé en tête


def test_show_keeps_name_if_listed():
    rec = to_record(_proj(), _EMPTY, None, ["branch", "name"])
    assert rec.keys() == ("branch", "name")


def test_relative_date_buckets():
    now = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)
    assert relative_date(now - timedelta(seconds=30), now) == "à l'instant"
    assert relative_date(now - timedelta(minutes=5), now) == "il y a 5 min"
    assert relative_date(now - timedelta(hours=3), now) == "il y a 3 h"
    assert relative_date(now - timedelta(days=2), now) == "il y a 2 j"
    assert relative_date(now - timedelta(days=20), now) == "il y a 2 sem"
    assert relative_date(now - timedelta(days=90), now) == "il y a 3 mois"
    assert relative_date(now - timedelta(days=800), now) == "il y a 2 ans"
    assert relative_date(now + timedelta(days=1), now) == "à l'instant"  # skew
