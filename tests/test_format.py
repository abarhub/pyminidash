from datetime import datetime

from pyminidash.format import format_value
from pyminidash.models import bytes_, datetime_, duration, link, number, percent, status, text
from pyminidash.models import StatusLevel


def test_text_none_is_empty():
    assert format_value(text("k", "L", None)) == ""


def test_number_trims():
    assert format_value(number("k", "L", 18.20)) == "18.2"
    assert format_value(number("k", "L", 910)) == "910"


def test_bytes_humanized():
    assert format_value(bytes_("k", "L", 512)) == "512 B"
    assert format_value(bytes_("k", "L", 1536)) == "1.5 KB"
    assert format_value(bytes_("k", "L", 234881024000)) == "218.8 GB"


def test_percent():
    assert format_value(percent("k", "L", 76)) == "76 %"


def test_datetime():
    assert format_value(datetime_("k", "L", datetime(2026, 8, 29, 14, 32, 7))) == "2026-08-29 14:32:07"


def test_duration():
    assert format_value(duration("k", "L", 0.82)) == "820 ms"
    assert format_value(duration("k", "L", 45)) == "45 s"
    assert format_value(duration("k", "L", 185)) == "3 min 5 s"
    assert format_value(duration("k", "L", 7800)) == "2 h 10 min"


def test_status_and_link_return_plain_text():
    assert format_value(status("k", "L", "UP", level=StatusLevel.OK)) == "UP"
    assert format_value(link("k", "L", "voir", "https://x.test")) == "voir"
