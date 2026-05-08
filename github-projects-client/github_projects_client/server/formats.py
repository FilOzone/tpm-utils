"""Compact columnar format helper for REST API responses."""

from __future__ import annotations

from typing import Any


def build_display_items(items: list[dict]) -> list[dict]:
    """Strip internal fields from items for output.

    Empty strings are preserved so callers can distinguish "field has no value"
    from "field was not requested."
    """
    return [{k: v for k, v in item.items() if not k.startswith("_")} for item in items]


def format_compact(
    display_items: list[dict],
    has_more: bool,
    next_cursor: str | None,
) -> dict[str, Any]:
    """Return columnar dict: column names once, then rows as arrays.

    Much more token-efficient than full JSON for large result sets
    because field names appear once instead of once-per-item.
    """
    columns: list[str] = []
    seen: set[str] = set()
    for item in display_items:
        for key in item:
            if key not in seen:
                columns.append(key)
                seen.add(key)

    rows = [[item.get(col, "") for col in columns] for item in display_items]

    payload: dict[str, Any] = {
        "columns": columns,
        "rows": rows,
        "total_in_page": len(display_items),
    }
    if has_more:
        payload["has_more"] = True
        payload["next_cursor"] = next_cursor
    return payload
