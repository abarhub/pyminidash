from pyminidash.models import Record, StatusLevel, bytes_, status, text, title
from pyminidash.web.render import to_cards, to_table


def _disk_records():
    return [
        Record(
            title("mount", "Disque", "C:\\"),
            status("pct", "%", "76 %", level=StatusLevel.WARN, summary=True),
            bytes_("free", "Libre", 218 * 1024**3, summary=True),
            bytes_("total", "Total", 930 * 1024**3),
        ),
        Record(
            title("mount", "Disque", "D:\\"),
            status("pct", "%", "91 %", level=StatusLevel.ERROR, summary=True),
            bytes_("free", "Libre", 210 * 1024**3, summary=True),
            bytes_("total", "Total", 1800 * 1024**3),
        ),
    ]


def test_to_table_column_order_follows_first_record():
    view = to_table(_disk_records())
    assert [c.key for c in view.columns] == ["mount", "pct", "free", "total"]
    assert [c.label for c in view.columns] == ["Disque", "%", "Libre", "Total"]
    assert len(view.rows) == 2
    assert view.rows[0][0].value == "C:\\"


def test_to_cards_extracts_title_badge_and_splits_summary():
    cards = to_cards(_disk_records())
    assert cards[0].title == "C:\\"
    assert cards[0].badge.key == "pct"
    assert [f.key for f in cards[0].summary_fields] == ["free"]
    assert [f.key for f in cards[0].hidden_fields] == ["total"]


def test_to_cards_without_title_or_badge():
    recs = [Record(text("a", "A", "1", summary=True), text("b", "B", "2"))]
    card = to_cards(recs)[0]
    assert card.title is None
    assert card.badge is None
    assert [f.key for f in card.summary_fields] == ["a"]
    assert [f.key for f in card.hidden_fields] == ["b"]
