from pyminidash.models import FieldRole, FieldType, StatusLevel
from pyminidash.providers.system import (
    _level_for_percent, _processes_to_records, disk_usage, top_processes,
)


def test_level_for_percent_thresholds():
    assert _level_for_percent(10) is StatusLevel.OK
    assert _level_for_percent(80) is StatusLevel.WARN
    assert _level_for_percent(95) is StatusLevel.ERROR


def test_level_for_percent_boundaries():
    assert _level_for_percent(75) is StatusLevel.WARN
    assert _level_for_percent(74) is StatusLevel.OK
    assert _level_for_percent(90) is StatusLevel.ERROR
    assert _level_for_percent(89) is StatusLevel.WARN


def test_disk_usage_on_tmp_path(tmp_path):
    records = disk_usage([str(tmp_path)])
    assert len(records) == 1
    assert records[0].keys() == ("mount", "percent", "free", "total", "used")
    mount, percent, *_ = records[0].fields
    assert mount.role is FieldRole.TITLE
    assert percent.type is FieldType.STATUS
    assert percent.role is FieldRole.BADGE
    assert percent.summary is True


def test_processes_to_records_sorts_and_truncates():
    samples = [
        {"pid": 1, "name": "a", "username": "u", "status": "running", "cpu": 5.0, "memory": 100},
        {"pid": 2, "name": "b", "username": "u", "status": "running", "cpu": 40.0, "memory": 200},
        {"pid": 3, "name": "c", "username": "u", "status": "running", "cpu": 12.0, "memory": 300},
    ]
    records = _processes_to_records(samples, limit=2)
    assert len(records) == 2
    assert [r.fields[0].value for r in records] == ["b", "c"]  # tri CPU desc
    assert records[0].keys() == ("name", "cpu", "memory", "pid", "username", "status")


def test_top_processes_smoke():
    records = top_processes(limit=3)
    assert 0 < len(records) <= 3
    keys = records[0].keys()
    assert all(r.keys() == keys for r in records)
