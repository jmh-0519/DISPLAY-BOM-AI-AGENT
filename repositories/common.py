from __future__ import annotations

from datetime import date, datetime


RELATION_COLUMNS = (
    "parent_item_code",
    "parent_item_name",
    "parent_item_type",
    "child_item_code",
    "child_item_name",
    "child_item_type",
    "location_code",
    "sequence_no",
    "quantity",
    "valid_from",
    "valid_to",
    "status",
)

TREE_COLUMNS = RELATION_COLUMNS + (
    "level",
    "bom_path",
    "required_quantity",
)


def iso_date(value: str | date | None) -> str:
    if value is None:
        return date.today().isoformat()
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return date.fromisoformat(value).isoformat()


def relation_sort_key(row: dict) -> tuple:
    return (
        int(row["sequence_no"]),
        str(row["child_item_code"]),
        str(row["location_code"]),
    )
