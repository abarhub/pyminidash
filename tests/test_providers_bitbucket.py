import logging

import httpx
import pytest
import respx

from pyminidash.connection import Connection
from pyminidash.errors import ProviderError
from pyminidash.models import FieldRole, FieldType, StatusLevel
from pyminidash.providers.bitbucket import (
    _split_repo, bitbucket_my_review, bitbucket_pr, bitbucket_pr_count, resolve_repos,
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
    route = respx.get(BASE).mock(return_value=_page([_pr(1)]))
    bitbucket_pr(CONN, repo="ABC/r1", state="merged", fields=["id"])  # normalisé, ne lève pas
    assert "state=MERGED" in str(route.calls.last.request.url)
    no_user = Connection(name="bb", base_url="https://bb.example.com", token="X")
    with pytest.raises(ProviderError, match="user"):
        bitbucket_pr(no_user, repo="ABC/r1", role="REVIEWER", fields=["id"])


@respx.mock
def test_bitbucket_pr_state_all_is_sent_explicitly():
    route = respx.get(BASE).mock(return_value=_page([_pr(1)]))
    bitbucket_pr(CONN, repo="ABC/r1", state="ALL", fields=["id"])
    assert "state=ALL" in str(route.calls.last.request.url)


@respx.mock
def test_bitbucket_pr_stale_days_requests_oldest_first():
    route = respx.get(BASE).mock(return_value=_page([_pr(1)]))
    bitbucket_pr(CONN, repo="ABC/r1", fields=["id"], stale_days=7)
    assert "order=OLDEST" in str(route.calls.last.request.url)


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
    with pytest.raises(ProviderError, match="ABC/r1"):
        bitbucket_pr(CONN, repos=["ABC/r1"], fields=["id"])
    # message names the repo, never the internal REST path
    with pytest.raises(ProviderError) as exc:
        bitbucket_pr(CONN, repos=["ABC/r1"], fields=["id"])
    assert "/rest/api/" not in str(exc.value)


@respx.mock
def test_bitbucket_pr_all_repos_fail_names_every_repo():
    for slug in ("r1", "r2"):
        respx.get(f"https://bb.example.com/rest/api/1.0/projects/ABC/repos/{slug}/pull-requests").mock(
            return_value=httpx.Response(404))
    with pytest.raises(ProviderError, match="ABC/r1.*ABC/r2"):
        bitbucket_pr(CONN, repos=["ABC/r1", "ABC/r2"], fields=["id"])


@respx.mock
def test_bitbucket_pr_count_all_repos_fail_names_every_repo():
    for slug in ("r1", "r2"):
        respx.get(f"https://bb.example.com/rest/api/1.0/projects/ABC/repos/{slug}/pull-requests").mock(
            return_value=httpx.Response(404))
    with pytest.raises(ProviderError, match="ABC/r1.*ABC/r2") as exc:
        bitbucket_pr_count(CONN, repos=["ABC/r1", "ABC/r2"])
    assert "/rest/api/" not in str(exc.value)


@respx.mock
def test_bitbucket_pr_stale_days_filter():
    now_ms = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).timestamp() * 1000
    fresh = _pr(1, updated=int(now_ms))
    old = _pr(2, updated=int(now_ms - 10 * 86_400_000))
    respx.get(BASE).mock(return_value=_page([fresh, old]))
    records = bitbucket_pr(CONN, repo="ABC/r1", fields=["id"], stale_days=7)
    assert [r.fields[0].value for r in records] == ["#2"]


@respx.mock
def test_bitbucket_pr_build_column():
    respx.get(BASE).mock(return_value=_page([_pr(1)]))
    respx.get("https://bb.example.com/rest/build-status/1.0/commits/abc123").mock(
        return_value=httpx.Response(200, json={"values": [{"state": "FAILED"}]})
    )
    rec = bitbucket_pr(CONN, repo="ABC/r1", fields=["id", "build"])[0]
    assert rec.fields[1].key == "build"
    assert rec.fields[1].value == "FAILED"
    assert rec.fields[1].level is StatusLevel.ERROR


@respx.mock
def test_bitbucket_pr_build_column_missing_is_dash():
    pr = _pr(1)
    pr["fromRef"].pop("latestCommit")
    respx.get(BASE).mock(return_value=_page([pr]))
    rec = bitbucket_pr(CONN, repo="ABC/r1", fields=["build"])[0]
    assert rec.fields[0].value == "—"
    assert rec.fields[0].level is StatusLevel.NEUTRAL


@respx.mock
def test_bitbucket_pr_mergeable_column():
    respx.get(BASE).mock(return_value=_page([_pr(1)]))
    respx.get("https://bb.example.com/rest/api/1.0/projects/ABC/repos/r1/pull-requests/1/merge").mock(
        return_value=httpx.Response(200, json={"canMerge": False, "conflicted": True})
    )
    rec = bitbucket_pr(CONN, repo="ABC/r1", fields=["id", "mergeable"])[0]
    assert rec.fields[1].key == "mergeable"
    assert rec.fields[1].value == "conflit"
    assert rec.fields[1].level is StatusLevel.ERROR


@respx.mock
def test_bitbucket_pr_mergeable_api_error_is_question_mark():
    respx.get(BASE).mock(return_value=_page([_pr(1)]))
    respx.get("https://bb.example.com/rest/api/1.0/projects/ABC/repos/r1/pull-requests/1/merge").mock(
        return_value=httpx.Response(500)
    )
    rec = bitbucket_pr(CONN, repo="ABC/r1", fields=["mergeable"])[0]
    assert rec.fields[0].value == "?"
    assert rec.fields[0].level is StatusLevel.NEUTRAL


@respx.mock
def test_records_are_homogeneous():
    full = _pr(1)
    stub = {"id": 2, "updatedDate": 100}
    respx.get(BASE).mock(return_value=_page([full, stub]))
    respx.get(url__regex=r".*/pull-requests/\d+/merge$").mock(
        return_value=httpx.Response(500))
    respx.get(url__regex=r".*/rest/build-status/1\.0/commits/.*").mock(
        return_value=httpx.Response(200, json={"values": [{"state": "SUCCESSFUL"}]}))
    records = bitbucket_pr(
        CONN, repo="ABC/r1",
        fields=["id", "title", "author", "build", "mergeable"],
    )
    assert len(records) == 2
    assert len({r.keys() for r in records}) == 1


@respx.mock
def test_bitbucket_pr_count_sums_repos():
    respx.get("https://bb.example.com/rest/api/1.0/projects/ABC/repos/r1/pull-requests").mock(
        return_value=_page([_pr(1), _pr(2)]))
    respx.get("https://bb.example.com/rest/api/1.0/projects/ABC/repos/r2/pull-requests").mock(
        return_value=_page([_pr(3)]))
    rec = bitbucket_pr_count(CONN, repos=["ABC/r1", "ABC/r2"], warn_above=2, error_above=5)[0]
    assert rec.fields[0].value == "3"
    assert rec.fields[0].level is StatusLevel.WARN


@respx.mock
def test_bitbucket_pr_count_saturates_with_plus():
    full = [_pr(i) for i in range(200)]
    respx.get(BASE).mock(return_value=_page(full, last=False, nxt=200))
    rec = bitbucket_pr_count(CONN, repo="ABC/r1")[0]
    assert rec.fields[0].value == "200+"


@respx.mock
def test_bitbucket_my_review_uses_reviewer_role():
    route = respx.get(BASE).mock(return_value=_page([_pr(1)]))
    records = bitbucket_my_review(CONN, repo="ABC/r1")
    assert [x.key for x in records[0].fields] == ["id", "title", "author", "reviewers", "updated"]
    url = str(route.calls.last.request.url)
    assert "role.1=REVIEWER" in url and "username.1=jdupont" in url
