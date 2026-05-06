"""View URL resolution for GitHub Projects v2."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

import requests

from .api import graphql_query, list_field_ids_by_name


PROJECT_VIEW_QUERY = """
query($org: String!, $number: Int!) {
  organization(login: $org) {
    projectV2(number: $number) {
      views(first: 100) {
        nodes {
          number
          name
          filter
          fields(first: 100) {
            nodes {
              ... on ProjectV2FieldCommon {
                name
                dataType
              }
              ... on ProjectV2SingleSelectField {
                name
                dataType
              }
              ... on ProjectV2IterationField {
                name
                dataType
              }
            }
          }
          groupByFields(first: 10) {
            nodes {
              ... on ProjectV2FieldCommon {
                name
                dataType
              }
              ... on ProjectV2SingleSelectField {
                name
                dataType
              }
              ... on ProjectV2IterationField {
                name
                dataType
              }
            }
          }
          verticalGroupByFields(first: 10) {
            nodes {
              ... on ProjectV2FieldCommon {
                name
                dataType
              }
              ... on ProjectV2SingleSelectField {
                name
                dataType
              }
              ... on ProjectV2IterationField {
                name
                dataType
              }
            }
          }
        }
      }
    }
  }
}
"""


def resolve_view_url(
    session: requests.Session,
    *,
    view_url: str,
) -> Dict[str, Any]:
    """
    Resolve effective list query from a project board view URL.

    - Uses `filterQuery` URL parameter when present (override).
    - Otherwise uses the saved view filter from GitHub GraphQL.
    - `sliceBy[...]` URL params are currently ignored.
    - If `visibleFields` is present, that order is used exactly.
    - Otherwise returns the view's default field order from GraphQL metadata.
    """
    parsed = urlparse(view_url.strip())
    path_parts = [p for p in parsed.path.split("/") if p]
    if len(path_parts) < 6:
        raise ValueError(f"Unrecognized project view URL path: {parsed.path}")
    if (
        path_parts[0] != "orgs"
        or path_parts[2] != "projects"
        or path_parts[4] != "views"
    ):
        raise ValueError(f"Unsupported project view URL format: {view_url}")

    org = path_parts[1]
    project_number = int(path_parts[3])
    view_number = int(path_parts[5])

    query_params = parse_qs(parsed.query)
    override_filter = (query_params.get("filterQuery") or [None])[0]
    slice_value = (query_params.get("sliceBy[value]") or [None])[0]
    visible_fields_raw = (query_params.get("visibleFields") or [None])[0]

    data = graphql_query(
        session,
        PROJECT_VIEW_QUERY,
        {"org": org, "number": project_number},
    )
    views = (data.get("organization") or {}).get("projectV2", {}).get("views", {}).get(
        "nodes"
    ) or []

    view = None
    for candidate in views:
        if candidate and candidate.get("number") == view_number:
            view = candidate
            break
    if not view:
        raise ValueError(
            f"View #{view_number} not found in {org} project #{project_number}"
        )

    base_filter = (
        override_filter if override_filter is not None else (view.get("filter") or "")
    ).strip()
    view_field_nodes = (view.get("fields") or {}).get("nodes") or []
    view_fields = [
        node.get("name") for node in view_field_nodes if node and node.get("name")
    ]
    visible_fields: Optional[List[str]] = None
    if visible_fields_raw:
        try:
            parsed_visible = json.loads(visible_fields_raw)
            if isinstance(parsed_visible, list):
                id_to_name = {
                    fid: name
                    for name, fid in list_field_ids_by_name(
                        session,
                        org=org,
                        project_number=project_number,
                    ).items()
                }
                resolved_visible: List[str] = []
                for value in parsed_visible:
                    if isinstance(value, str) and value.strip():
                        resolved_visible.append(value.strip())
                    elif isinstance(value, int):
                        mapped = id_to_name.get(value)
                        if mapped:
                            resolved_visible.append(mapped)
                visible_fields = list(dict.fromkeys(resolved_visible))
        except (json.JSONDecodeError, TypeError, ValueError):
            visible_fields = None
    group_nodes = (view.get("groupByFields") or {}).get("nodes") or []
    primary_group_name = (
        group_nodes[0].get("name") if group_nodes and group_nodes[0] else None
    )
    effective_filter = base_filter

    return {
        "org": org,
        "project_number": project_number,
        "view_number": view_number,
        "view_name": view.get("name"),
        "base_filter": base_filter,
        "effective_filter": effective_filter,
        "view_fields": visible_fields if visible_fields else view_fields,
        "view_default_fields": view_fields,
        "visible_fields_override": visible_fields,
        "override_filter": override_filter,
        "slice_value": slice_value,
        "group_field": primary_group_name,
        "slice_group_field": None,
        "slice_filter": None,
    }
