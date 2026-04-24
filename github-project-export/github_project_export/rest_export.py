"""Fetch project items via REST and map rows to configured columns."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional, Sequence, Tuple

import requests

from github_projects_client import (
    fetch_items_rest as fetch_project_v2_items_rest,
    list_field_ids_by_name as list_project_v2_field_ids_by_name,
)

from github_project_export import synthetic


@dataclass(frozen=True)
class Column:
    kind: Literal["project", "synthetic"]
    header: str
    project_field_name: Optional[str] = None
    synthetic_internal: Optional[str] = None


class FieldResolutionError(ValueError):
    """Unknown field name (board + synthetic)."""


def build_columns(
    fields: Sequence[str],
    board_field_name_to_id: Dict[str, int],
) -> Tuple[List[Column], List[int]]:
    """
    Map user ``fields`` to columns. Each header must match a board field (case-insensitive)
    or a documented synthetic key. Returns REST ``field_ids`` to request (unique, any order).
    """
    lower_to_exact = {name.casefold(): name for name in board_field_name_to_id}

    columns: List[Column] = []
    rest_ids: List[int] = []
    seen_ids: set[int] = set()

    for header in fields:
        fold = header.strip().casefold()
        if fold in lower_to_exact:
            exact = lower_to_exact[fold]
            fid = board_field_name_to_id[exact]
            columns.append(Column("project", header, project_field_name=exact))
            if fid not in seen_ids:
                seen_ids.add(fid)
                rest_ids.append(fid)
            continue

        sk = synthetic.normalize_synthetic_key(header)
        if sk is not None:
            columns.append(Column("synthetic", header, synthetic_internal=sk))
            continue

        board_list = ", ".join(sorted(board_field_name_to_id))
        syn_list = ", ".join(sorted(set(synthetic.documented_synthetic_headers())))
        raise FieldResolutionError(
            f"Unknown field {header!r}. "
            f"Board fields (names from this project): {board_list}. "
            f"Synthetic columns: {syn_list}.",
        )

    return columns, rest_ids


def _logins_csv_from_user_dicts(items: Any) -> str:
    """GitHub often returns assignees as a list of user objects with ``login``."""
    if not isinstance(items, list):
        return ""
    out: List[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        login = item.get("login")
        if isinstance(login, str) and login:
            out.append(login)
    return ",".join(out)


def _reviewers_project_field_csv(value: Dict[str, Any]) -> str:
    """Project *Reviewers* field: dict with ``requested_reviewers`` / ``requested_teams``."""
    parts: List[str] = []
    for u in value.get("requested_reviewers") or []:
        if isinstance(u, dict):
            login = u.get("login")
            if isinstance(login, str) and login:
                parts.append(login)
    for t in value.get("requested_teams") or []:
        if isinstance(t, dict):
            label = t.get("slug") or t.get("name")
            if isinstance(label, str) and label:
                parts.append(label)
    return ",".join(parts)


def _format_field_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return _logins_csv_from_user_dicts(value)

    if not isinstance(value, dict):
        return str(value)

    # Pull-style reviewers payload embedded in a project field value
    if "requested_reviewers" in value or "requested_teams" in value:
        return _reviewers_project_field_csv(value)

    # Project "title" field (data_type: title) — see REST items `fields[].value`
    top_raw = value.get("raw")
    if isinstance(top_raw, str) and top_raw:
        return top_raw

    name_obj = value.get("name")
    if isinstance(name_obj, dict):
        raw = name_obj.get("raw")
        if isinstance(raw, str):
            return raw
    if isinstance(name_obj, str):
        return name_obj

    txt = value.get("text")
    if isinstance(txt, str):
        return txt

    title = value.get("title")
    if isinstance(title, str):
        return title

    return ""


def _project_cell(item: Dict[str, Any], project_field_name: str) -> str:
    for f in item.get("fields") or []:
        if not isinstance(f, dict):
            continue
        if f.get("name") == project_field_name:
            return _format_field_value(f.get("value"))
    return ""


def _item_to_row(item: Dict[str, Any], columns: Sequence[Column]) -> List[str]:
    content = item.get("content")
    if not isinstance(content, dict):
        content = None

    row: List[str] = []
    for col in columns:
        if col.kind == "project":
            assert col.project_field_name is not None
            row.append(_project_cell(item, col.project_field_name))
        else:
            assert col.synthetic_internal is not None
            row.append(synthetic.synthetic_cell_value(col.synthetic_internal, content))
    return row


def export_rows(
    session: requests.Session,
    org: str,
    project_number: int,
    query: str,
    fields: Sequence[str],
    *,
    verbose: bool = True,
) -> List[List[str]]:
    """
    Return data rows (no header) for ``fields`` order, using server-side ``query``.

    Raises:
        FieldResolutionError: unknown field name.
        requests.HTTPError: API failure.
    """
    board_map = list_project_v2_field_ids_by_name(
        session,
        org=org,
        project_number=project_number,
    )
    columns, field_ids = build_columns(fields, board_map)

    result = fetch_project_v2_items_rest(
        session,
        org=org,
        project_number=project_number,
        query=query,
        field_ids=field_ids if field_ids else None,
    )

    return [_item_to_row(it, columns) for it in result["items"]]
