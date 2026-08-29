import httpx
import pytest
import respx

from pyminidash.connection import Connection
from pyminidash.models import FieldRole, FieldType, StatusLevel
from pyminidash.providers._atlassian import ApiError
from pyminidash.providers.jira import _parse_dt, _status_level, jira_jql

CONN = Connection(name="jira", base_url="https://jira.example.com", token="PAT")

_ISSUE = {
    "key": "ABC-1",
    "fields": {
        "summary": "Corriger le bug",
        "status": {"name": "In Progress"},
        "assignee": {"displayName": "Léa Martin"},
        "priority": {"name": "High"},
        "updated": "2026-08-20T14:30:00.000+0200",
    },
}


def _search_response(issues, total=None):
    return httpx.Response(200, json={
        "issues": issues,
        "total": total if total is not None else len(issues),
        "startAt": 0,
        "maxResults": 100,
    })


def test_status_level_heuristic():
    assert _status_level("Done") is StatusLevel.OK
    assert _status_level(" Terminé ") is StatusLevel.OK
    assert _status_level("Blocked") is StatusLevel.ERROR
    assert _status_level("In Progress") is StatusLevel.NEUTRAL


def test_parse_dt():
    assert _parse_dt("") is None
    dt = _parse_dt("2026-08-20T14:30:00.000+0200")
    assert dt.year == 2026 and dt.hour == 14


@respx.mock
def test_jira_jql_maps_fields_in_order():
    respx.get("https://jira.example.com/rest/api/2/search").mock(
        return_value=_search_response([_ISSUE])
    )
    records = jira_jql(CONN, "project = ABC", ["key", "summary", "status", "assignee", "updated"])
    assert len(records) == 1
    f = records[0].fields
    assert [x.key for x in f] == ["key", "summary", "status", "assignee", "updated"]
    assert f[0].type is FieldType.LINK
    assert f[0].role is FieldRole.TITLE
    assert f[0].url == "https://jira.example.com/browse/ABC-1"
    assert f[2].type is FieldType.STATUS and f[2].level is StatusLevel.NEUTRAL
    assert f[3].value == "Léa Martin"
    assert f[4].type is FieldType.DATETIME


@respx.mock
def test_jira_jql_unassigned_and_missing_fields():
    issue = {"key": "ABC-2", "fields": {"summary": "x", "status": {"name": "To Do"}}}
    respx.get("https://jira.example.com/rest/api/2/search").mock(
        return_value=_search_response([issue])
    )
    records = jira_jql(CONN, "q", ["assignee", "labels"])
    assert records[0].fields[0].value == "Non assigné"
    assert records[0].fields[1].value == ""


@respx.mock
def test_jira_jql_paginates_to_max_results():
    route = respx.get("https://jira.example.com/rest/api/2/search")
    route.side_effect = [
        _search_response([_ISSUE, _ISSUE], total=3),
        _search_response([_ISSUE], total=3),
    ]
    records = jira_jql(CONN, "q", ["key"], max_results=3)
    assert len(records) == 3
    assert route.call_count == 2


@respx.mock
def test_jira_jql_omits_fields_param_when_only_key():
    route = respx.get("https://jira.example.com/rest/api/2/search").mock(
        return_value=_search_response([_ISSUE])
    )
    jira_jql(CONN, "q", ["key"])
    assert "fields=" not in str(route.calls.last.request.url)


@respx.mock
def test_jira_jql_sends_fields_param_when_non_key_requested():
    route = respx.get("https://jira.example.com/rest/api/2/search").mock(
        return_value=_search_response([_ISSUE])
    )
    jira_jql(CONN, "q", ["key", "summary"])
    assert "fields=summary" in str(route.calls.last.request.url)


@respx.mock
def test_jira_jql_handles_null_total():
    respx.get("https://jira.example.com/rest/api/2/search").mock(
        return_value=httpx.Response(200, json={"issues": [_ISSUE], "total": None})
    )
    records = jira_jql(CONN, "q", ["key"], max_results=3)
    assert len(records) == 1


@respx.mock
def test_jira_jql_count_handles_null_total():
    respx.get("https://jira.example.com/rest/api/2/search").mock(
        return_value=httpx.Response(200, json={"total": None, "issues": []})
    )
    records = jira_jql_count(CONN, "q")
    assert records[0].fields[0].value == "0"


@respx.mock
def test_jira_jql_bad_jql_raises_api_error():
    respx.get("https://jira.example.com/rest/api/2/search").mock(
        return_value=httpx.Response(400, json={"errorMessages": ["Le champ 'foo' n'existe pas"]})
    )
    with pytest.raises(ApiError, match="foo"):
        jira_jql(CONN, "foo = bar", ["key"])


@respx.mock
def test_jira_jql_customfield():
    issue = {"key": "ABC-9", "fields": {"customfield_10001": 8}}
    respx.get("https://jira.example.com/rest/api/2/search").mock(
        return_value=_search_response([issue])
    )
    records = jira_jql(CONN, "q", ["customfield_10001"])
    assert records[0].fields[0].value == "8"


from pyminidash.providers.jira import jira_jql_count, jira_my_issues


@respx.mock
def test_jira_jql_count_reads_total_with_thresholds():
    route = respx.get("https://jira.example.com/rest/api/2/search").mock(
        return_value=httpx.Response(200, json={"total": 12, "issues": []})
    )
    records = jira_jql_count(CONN, "project = ABC", warn_above=5, error_above=10)
    assert len(records) == 1
    assert records[0].fields[0].value == "12"
    assert records[0].fields[0].level is StatusLevel.ERROR
    # maxResults=0 demandé
    sent = route.calls.last.request.url
    assert "maxResults=0" in str(sent)


@respx.mock
def test_jira_my_issues_uses_fixed_jql_and_default_fields():
    route = respx.get("https://jira.example.com/rest/api/2/search").mock(
        return_value=_search_response([_ISSUE])
    )
    records = jira_my_issues(CONN)
    assert [x.key for x in records[0].fields] == ["key", "summary", "status", "priority", "updated"]
    url = str(route.calls.last.request.url)
    assert "currentUser" in url
    assert "Unresolved" in url


@respx.mock
def test_jira_my_issues_field_override():
    respx.get("https://jira.example.com/rest/api/2/search").mock(
        return_value=_search_response([_ISSUE])
    )
    records = jira_my_issues(CONN, fields=["key", "summary"])
    assert [x.key for x in records[0].fields] == ["key", "summary"]
