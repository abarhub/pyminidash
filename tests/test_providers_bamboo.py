import httpx
import pytest
import respx

from pyminidash.connection import Connection
from pyminidash.errors import ProviderError
from pyminidash.models import FieldRole, FieldType, StatusLevel
from pyminidash.providers.bamboo import bamboo_plan_status

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
