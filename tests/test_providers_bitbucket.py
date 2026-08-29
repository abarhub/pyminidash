import logging

import httpx
import pytest
import respx

from pyminidash.connection import Connection
from pyminidash.errors import ProviderError
from pyminidash.models import FieldRole, FieldType, StatusLevel
from pyminidash.providers.bitbucket import (
    _split_repo, bitbucket_pr, resolve_repos,
)

CONN = Connection(name="bb", base_url="https://bb.example.com", token="PAT", user="jdupont")
BASE = "https://bb.example.com/rest/api/1.0/projects/ABC/repos/r1/pull-requests"


def _pr(pid=1, updated=1_724_500_000_000, reviewers=None, state="OPEN"):
    return {
        "id": pid,
        "title": f"PR {pid}",
        "state": state,
        "author": {"user": {"displayName": "Léa"}},
        "reviewers": reviewers if reviewers is not None else [{"approved": True}],
        "fromRef": {"displayId": "feature/x", "latestCommit": "abc123"},
        "toRef": {"displayId": "main"},
        "updatedDate": updated,
        "properties": {"commentCount": 3, "openTaskCount": 1},
        "links": {"self": [{"href": f"https://bb.example.com/pr/{pid}"}]},
    }


def _page(values, last=True, nxt=None):
    body = {"values": values, "isLastPage": last, "size": len(values)}
    if nxt is not None:
        body["nextPageStart"] = nxt
    return httpx.Response(200, json=body)


def test_split_repo():
    assert _split_repo("ABC/mon-repo") == ("ABC", "mon-repo")
    with pytest.raises(ProviderError, match="PROJET/slug"):
        _split_repo("mon-repo")


def test_resolve_repos_exactly_one():
    with pytest.raises(ProviderError, match="exactement un"):
        resolve_repos(CONN)
    with pytest.raises(ProviderError, match="exactement un"):
        resolve_repos(CONN, repo="ABC/r1", project="ABC")
    assert resolve_repos(CONN, repo="ABC/r1") == [("ABC", "r1")]
    assert resolve_repos(CONN, repos=["ABC/r1", "ABC/r2"]) == [("ABC", "r1"), ("ABC", "r2")]


@respx.mock
def test_resolve_repos_project_paginates():
    respx.get("https://bb.example.com/rest/api/1.0/projects/ABC/repos").mock(
        return_value=httpx.Response(200, json={"values": [{"slug": "r1"}, {"slug": "r2"}], "isLastPage": True})
    )
    assert resolve_repos(CONN, project="ABC") == [("ABC", "r1"), ("ABC", "r2")]


@respx.mock
def test_bitbucket_pr_maps_fields_in_order():
    respx.get(BASE).mock(return_value=_page([_pr(1)]))
    records = bitbucket_pr(CONN, repo="ABC/r1", fields=["id", "title", "author", "reviewers", "branches", "updated"])
    assert len(records) == 1
    f = records[0].fields
    assert [x.key for x in f] == ["id", "title", "author", "reviewers", "branches", "updated"]
    assert f[0].type is FieldType.LINK and f[0].role is FieldRole.TITLE and f[0].value == "#1"
    assert f[0].url == "https://bb.example.com/pr/1"
    assert f[2].value == "Léa"
    assert f[3].type is FieldType.STATUS and f[3].level is StatusLevel.OK  # 1/1 approuvé
    assert f[4].value == "feature/x → main"
    assert f[5].type is FieldType.DATETIME


@respx.mock
def test_bitbucket_pr_reviewers_needs_work():
    prs = [_pr(1, reviewers=[{"approved": False, "status": "NEEDS_WORK"}, {"approved": True}])]
    respx.get(BASE).mock(return_value=_page(prs))
    rec = bitbucket_pr(CONN, repo="ABC/r1", fields=["reviewers"])[0]
    assert rec.fields[0].level is StatusLevel.WARN


@respx.mock
def test_bitbucket_pr_state_filter_and_role_requires_user():
    respx.get(BASE).mock(return_value=_page([_pr(1)]))
    bitbucket_pr(CONN, repo="ABC/r1", state="merged", fields=["id"])  # normalisé, ne lève pas
    no_user = Connection(name="bb", base_url="https://bb.example.com", token="X")
    with pytest.raises(ProviderError, match="user"):
        bitbucket_pr(no_user, repo="ABC/r1", role="REVIEWER", fields=["id"])


@respx.mock
def test_bitbucket_pr_bad_state():
    with pytest.raises(ProviderError, match="state"):
        bitbucket_pr(CONN, repo="ABC/r1", state="WEIRD", fields=["id"])


@respx.mock
def test_bitbucket_pr_aggregates_and_sorts_desc():
    respx.get("https://bb.example.com/rest/api/1.0/projects/ABC/repos/r1/pull-requests").mock(
        return_value=_page([_pr(1, updated=100)]))
    respx.get("https://bb.example.com/rest/api/1.0/projects/ABC/repos/r2/pull-requests").mock(
        return_value=_page([_pr(2, updated=200)]))
    records = bitbucket_pr(CONN, repos=["ABC/r1", "ABC/r2"], fields=["id"])
    assert [r.fields[0].value for r in records] == ["#2", "#1"]  # tri updated desc


@respx.mock
def test_bitbucket_pr_one_repo_fails_others_pass(caplog):
    respx.get("https://bb.example.com/rest/api/1.0/projects/ABC/repos/r1/pull-requests").mock(
        return_value=_page([_pr(1)]))
    respx.get("https://bb.example.com/rest/api/1.0/projects/ABC/repos/r2/pull-requests").mock(
        return_value=httpx.Response(404))
    with caplog.at_level(logging.WARNING, logger="pyminidash.providers.bitbucket"):
        records = bitbucket_pr(CONN, repos=["ABC/r1", "ABC/r2"], fields=["id"])
    assert [r.fields[0].value for r in records] == ["#1"]
    assert any("r2" in r.message for r in caplog.records)


@respx.mock
def test_bitbucket_pr_all_repos_fail_raises():
    respx.get("https://bb.example.com/rest/api/1.0/projects/ABC/repos/r1/pull-requests").mock(
        return_value=httpx.Response(404))
    with pytest.raises(ProviderError):
        bitbucket_pr(CONN, repos=["ABC/r1"], fields=["id"])


@respx.mock
def test_bitbucket_pr_stale_days_filter():
    now_ms = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).timestamp() * 1000
    fresh = _pr(1, updated=int(now_ms))
    old = _pr(2, updated=int(now_ms - 10 * 86_400_000))
    respx.get(BASE).mock(return_value=_page([fresh, old]))
    records = bitbucket_pr(CONN, repo="ABC/r1", fields=["id"], stale_days=7)
    assert [r.fields[0].value for r in records] == ["#2"]
