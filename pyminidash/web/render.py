"""Transforme une list[Record] en structures prêtes pour les templates."""
from __future__ import annotations

from dataclasses import dataclass

from pyminidash.format import format_value
from pyminidash.models import Field, FieldRole, Record


@dataclass(frozen=True)
class Column:
    key: str
    label: str


@dataclass(frozen=True)
class TableView:
    columns: list[Column]
    rows: list[list[Field]]


@dataclass(frozen=True)
class CardView:
    title: str | None
    badge: Field | None
    summary_fields: list[Field]
    hidden_fields: list[Field]


def to_table(records: list[Record]) -> TableView:
    columns = [Column(f.key, f.label) for f in records[0].fields]
    rows = [list(r.fields) for r in records]
    return TableView(columns=columns, rows=rows)


def to_cards(records: list[Record]) -> list[CardView]:
    cards: list[CardView] = []
    for record in records:
        title_text: str | None = None
        badge: Field | None = None
        summary: list[Field] = []
        hidden: list[Field] = []
        for f in record.fields:
            if f.role is FieldRole.TITLE and title_text is None:
                title_text = format_value(f)
            elif f.role is FieldRole.BADGE and badge is None:
                badge = f
            elif f.summary:
                summary.append(f)
            else:
                hidden.append(f)
        cards.append(CardView(title_text, badge, summary, hidden))
    return cards
