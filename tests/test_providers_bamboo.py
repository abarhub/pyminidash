import httpx
import pytest
import respx

from pyminidash.connection import Connection
from pyminidash.errors import ProviderError
from pyminidash.models import FieldRole, FieldType, StatusLevel
from pyminidash.providers.bamboo import (
    bamboo_plan_health, bamboo_plan_status, bamboo_running, bamboo_user_builds,
)

CONN = Connection(name="bam", base_url="https://bam.example.com", token="PAT", user="jdupont")


def _result(key="PROJ-PLAN-42", state="Successful", num=42):
    return {
        "planResultKey": {"key": key},
        "planName": "Mon Plan",
        "buildState": state,
        "buildNumber": num,
        "buildDurationInSeconds": 125,
        "buildCompletedTime": "2026-08-20T14:30:00Z",
        "buildReason": 'Manual run by <a href="x">Jean</a>',
        "successfulTestCount": 142,
        "failedTestCount": 3,
    }


def _latest(result):
    return httpx.Response(200, json=result)


def test_bamboo_plan_status_empty_plans_raises():
    with pytest.raises(ProviderError, match="plans"):
        bamboo_plan_status(CONN, plans=[])


@respx.mock
def test_bamboo_plan_status_maps_fields():
    respx.get("https://bam.example.com/rest/api/latest/result/PROJ-PLAN/latest").mock(
        return_value=_latest(_result()))
    rec = bamboo_plan_status(CONN, plans=["PROJ-PLAN"])[0]
    f = rec.fields
    assert [x.key for x in f] == ["plan", "state", "number", "duration", "finished"]
    assert f[0].type is FieldType.LINK and f[0].role is FieldRole.TITLE
    assert f[0].url == "https://bam.example.com/browse/PROJ-PLAN-42"
    assert f[1].type is FieldType.STATUS and f[1].level is StatusLevel.OK
    assert f[2].value == 42
    assert f[3].type is FieldType.DURATION
    assert f[4].type is FieldType.DATETIME


@respx.mock
def test_bamboo_plan_status_never_built_is_dash():
    respx.get("https://bam.example.com/rest/api/latest/result/PROJ-NOPE/latest").mock(
        return_value=httpx.Response(404))
    rec = bamboo_plan_status(CONN, plans=["PROJ-NOPE"])[0]
    assert rec.fields[0].value == "PROJ-NOPE"   # libellé = clé du plan
    assert rec.fields[1].value == "—" and rec.fields[1].level is StatusLevel.NEUTRAL


@respx.mock
def test_bamboo_plan_status_wrapped_results():
    respx.get("https://bam.example.com/rest/api/latest/result/PROJ-PLAN/latest").mock(
        return_value=httpx.Response(200, json={"results": {"result": [_result(state="Failed")]}}))
    rec = bamboo_plan_status(CONN, plans=["PROJ-PLAN"])[0]
    assert rec.fields[1].level is StatusLevel.ERROR


@respx.mock
def test_bamboo_plan_status_optional_fields():
    respx.get("https://bam.example.com/rest/api/latest/result/PROJ-PLAN/latest").mock(
        return_value=_latest(_result()))
    rec = bamboo_plan_status(CONN, plans=["PROJ-PLAN"], fields=["plan", "trigger", "tests"])[0]
    assert rec.fields[1].value == "Manual run by Jean"
    assert rec.fields[2].value == "142 ✓ / 3 ✗"


def _results_page(results):
    return httpx.Response(200, json={"results": {"result": results}})


@respx.mock
def test_bamboo_user_builds_filters_by_reason():
    mine = _result(key="P-A-1", num=1)
    mine["buildReason"] = 'Manual run by <a>jdupont</a>'
    other = _result(key="P-B-2", num=2)
    other["buildReason"] = "Changes by someone else"
    respx.get("https://bam.example.com/rest/api/latest/result").mock(
        return_value=_results_page([mine, other]))
    records = bamboo_user_builds(CONN)   # user par défaut = connection.user = "jdupont"
    assert len(records) == 1
    assert [x.key for x in records[0].fields] == ["plan", "state", "number", "finished", "duration"]
    assert records[0].fields[2].value == 1


def test_bamboo_user_builds_no_user_raises():
    no_user = Connection(name="bam", base_url="https://bam.example.com", token="X")
    with pytest.raises(ProviderError, match="user"):
        bamboo_user_builds(no_user)


@respx.mock
def test_bamboo_user_builds_explicit_user_and_limit():
    results = []
    for i in range(5):
        r = _result(key=f"P-X-{i}", num=i)
        r["buildReason"] = "run by alice"
        results.append(r)
    respx.get("https://bam.example.com/rest/api/latest/result").mock(
        return_value=_results_page(results))
    records = bamboo_user_builds(CONN, user="alice", max_results=3)
    assert len(records) == 3


@respx.mock
def test_bamboo_plan_health_counts():
    respx.get("https://bam.example.com/rest/api/latest/result/P-A/latest").mock(
        return_value=_latest(_result(state="Successful")))
    respx.get("https://bam.example.com/rest/api/latest/result/P-B/latest").mock(
        return_value=_latest(_result(state="Failed")))
    respx.get("https://bam.example.com/rest/api/latest/result/P-C/latest").mock(
        return_value=httpx.Response(404))
    rec = bamboo_plan_health(CONN, plans=["P-A", "P-B", "P-C"])[0]
    assert rec.fields[1].value == 1   # green
    assert rec.fields[2].value == 1   # red
    assert rec.fields[3].level is StatusLevel.ERROR


def test_bamboo_plan_health_empty_raises():
    with pytest.raises(ProviderError, match="plans"):
        bamboo_plan_health(CONN, plans=[])


@respx.mock
def test_bamboo_running_queue_and_in_progress():
    respx.get("https://bam.example.com/rest/api/latest/queue").mock(
        return_value=httpx.Response(200, json={"queuedBuilds": {"queuedBuild": [
            {"planName": "Plan Q", "planResultKey": {"key": "P-Q-9"}, "buildNumber": 9}
        ]}}))
    running = _result(key="P-A-5", num=5)
    running["lifeCycleState"] = "InProgress"
    running["buildState"] = "Unknown"
    running["progress"] = {"percentageCompletedPretty": "62%"}
    respx.get("https://bam.example.com/rest/api/latest/result/P-A/latest").mock(
        return_value=_latest(running))
    records = bamboo_running(CONN, plans=["P-A"])
    labels = {r.fields[1].value for r in records}
    assert labels == {"En file", "En cours"}
    prog = [r.fields[4].value for r in records if r.fields[1].value == "En cours"][0]
    assert prog == "62%"


@respx.mock
def test_bamboo_running_skips_finished_plans():
    done = _result(key="P-A-5")
    done["lifeCycleState"] = "Finished"
    respx.get("https://bam.example.com/rest/api/latest/queue").mock(
        return_value=httpx.Response(200, json={"queuedBuilds": {"queuedBuild": []}}))
    respx.get("https://bam.example.com/rest/api/latest/result/P-A/latest").mock(
        return_value=_latest(done))
    assert bamboo_running(CONN, plans=["P-A"]) == []


def test_bamboo_running_needs_exactly_one_target():
    with pytest.raises(ProviderError, match="exactement un"):
        bamboo_running(CONN)
    with pytest.raises(ProviderError, match="exactement un"):
        bamboo_running(CONN, plans=["P-A"], project="P")


@respx.mock
def test_bamboo_running_project_expands_plans():
    respx.get("https://bam.example.com/rest/api/latest/queue").mock(
        return_value=httpx.Response(200, json={"queuedBuilds": {"queuedBuild": []}}))
    respx.get("https://bam.example.com/rest/api/latest/project/PROJ").mock(
        return_value=httpx.Response(200, json={"plans": {"plan": [{"key": "PROJ-A"}, {"key": "PROJ-B"}]}}))
    ip = _result(key="PROJ-A-1")
    ip["lifeCycleState"] = "InProgress"
    respx.get("https://bam.example.com/rest/api/latest/result/PROJ-A/latest").mock(
        return_value=_latest(ip))
    respx.get("https://bam.example.com/rest/api/latest/result/PROJ-B/latest").mock(
        return_value=httpx.Response(404))
    records = bamboo_running(CONN, project="PROJ")
    assert len(records) == 1 and records[0].fields[0].value == "Mon Plan"
