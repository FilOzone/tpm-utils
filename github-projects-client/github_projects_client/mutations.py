"""Mutation tools for GitHub Projects v2 — set field values by name."""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional

import requests

from .api import GitHubRateLimitError, graphql_query
from .fields import list_field_options
from .items import get_item


UPDATE_FIELD_MUTATION = """
mutation($input: UpdateProjectV2ItemFieldValueInput!) {
    updateProjectV2ItemFieldValue(input: $input) {
        projectV2Item {
            id
        }
    }
}
"""

CLEAR_FIELD_MUTATION = """
mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!) {
    clearProjectV2ItemFieldValue(input: {
        projectId: $projectId,
        itemId: $itemId,
        fieldId: $fieldId
    }) {
        projectV2Item {
            id
        }
    }
}
"""

# ---------------------------------------------------------------------------
# Batch size for aliased GraphQL mutations
# ---------------------------------------------------------------------------
_BATCH_SIZE = 25

# GitHub asks clients to wait at least a second between mutation requests to
# stay clear of its secondary rate limit.
_SECONDS_BETWEEN_BATCHES = 1.0

FIELD_VALUE_BY_NAME_QUERY = """
query($ids: [ID!]!, $field: String!) {
    nodes(ids: $ids) {
        ... on ProjectV2Item {
            id
            fieldValueByName(name: $field) {
                ... on ProjectV2ItemFieldSingleSelectValue { name }
                ... on ProjectV2ItemFieldTextValue { text }
                ... on ProjectV2ItemFieldNumberValue { number }
                ... on ProjectV2ItemFieldDateValue { date }
                ... on ProjectV2ItemFieldIterationValue { title }
            }
        }
    }
}
"""


def _fetch_old_values_by_node_id(
    session: requests.Session,
    *,
    node_ids: List[str],
    field_name: str,
) -> Dict[str, str]:
    """Fetch current field values for project item node IDs in one query per 100.

    Best-effort: any lookup failure leaves the affected IDs out of the result,
    so callers fall back to an empty old_value rather than failing the mutation.
    """
    old_values: Dict[str, str] = {}
    for start in range(0, len(node_ids), 100):
        chunk = node_ids[start : start + 100]
        try:
            data = graphql_query(
                session,
                FIELD_VALUE_BY_NAME_QUERY,
                {"ids": chunk, "field": field_name},
            )
        except Exception:
            continue
        for node in data.get("nodes") or []:
            if not isinstance(node, dict) or "id" not in node:
                continue
            value = node.get("fieldValueByName") or {}
            for key in ("name", "text", "title", "date", "number"):
                if value.get(key) is not None:
                    old_values[node["id"]] = str(value[key])
                    break
            else:
                old_values[node["id"]] = ""
    return old_values


def _resolve_field_and_value(
    session: requests.Session,
    *,
    org: str,
    project_number: int,
    field_name: str,
    value: str,
) -> Dict[str, Any]:
    """Resolve field info and map the value once for use across a batch.

    Returns a dict with project_id, field_id, mutation_value, or an error.
    """
    field_data = list_field_options(
        session,
        org=org,
        project_number=project_number,
        field_name=field_name,
    )
    project_id = field_data["project_id"]
    fields = field_data.get("fields", {})

    if not fields:
        return {"success": False, "error": f"Field not found: {field_name}"}

    canonical_name, field_info = next(iter(fields.items()))
    field_id = field_info["id"]
    field_type = field_info.get("type", "unknown")

    mutation_value: Dict[str, Any] = {}

    if field_type == "single_select":
        option_id = None
        for opt in field_info.get("options", []):
            if opt["name"].lower() == value.lower():
                option_id = opt["id"]
                break
        if option_id is None:
            available = [opt["name"] for opt in field_info.get("options", [])]
            return {
                "success": False,
                "error": f"Option '{value}' not found for field '{field_name}'. Available: {available}",
            }
        mutation_value = {"singleSelectOptionId": option_id}

    elif field_type == "iteration":
        iteration_id = None
        for it in field_info.get("iterations", []) + field_info.get(
            "completed_iterations", []
        ):
            if it["title"].lower() == value.lower():
                iteration_id = it["id"]
                break
        if iteration_id is None:
            available = [it["title"] for it in field_info.get("iterations", [])]
            return {
                "success": False,
                "error": f"Iteration '{value}' not found for field '{field_name}'. Active iterations: {available}",
            }
        mutation_value = {"iterationId": iteration_id}

    elif field_type in ("TEXT",):
        mutation_value = {"text": value}

    elif field_type in ("NUMBER",):
        try:
            mutation_value = {"number": float(value)}
        except ValueError:
            return {
                "success": False,
                "error": f"'{value}' is not a valid number for field '{field_name}'",
            }

    elif field_type in ("DATE",):
        mutation_value = {"date": value}

    else:
        return {
            "success": False,
            "error": f"Unsupported field type: {field_type} for field '{field_name}'",
        }

    return {
        "success": True,
        "project_id": project_id,
        "field_id": field_id,
        "canonical_name": canonical_name,
        "mutation_value": mutation_value,
    }


def _resolve_field_only(
    session: requests.Session,
    *,
    org: str,
    project_number: int,
    field_name: str,
) -> Dict[str, Any]:
    """Resolve just the field info (project_id, field_id) without mapping a value.

    Used for clear operations where no value mapping is needed.
    """
    field_data = list_field_options(
        session,
        org=org,
        project_number=project_number,
        field_name=field_name,
    )
    project_id = field_data["project_id"]
    fields = field_data.get("fields", {})

    if not fields:
        return {"success": False, "error": f"Field not found: {field_name}"}

    canonical_name, field_info = next(iter(fields.items()))
    field_id = field_info["id"]

    return {
        "success": True,
        "project_id": project_id,
        "field_id": field_id,
        "canonical_name": canonical_name,
    }


def _rate_limited_results(
    items: List[Dict[str, Any]], exc: GitHubRateLimitError
) -> List[Dict[str, Any]]:
    return [
        {
            "item_ref": item["ref"],
            "success": False,
            "rate_limited": True,
            "error": f"not attempted, GitHub rate limit hit: {exc}",
        }
        for item in items
    ]


def _execute_batch(
    session: requests.Session,
    *,
    batch: List[Dict[str, Any]],
    batch_query: str,
    batch_variables: Dict[str, Any],
    single_query: str,
    single_variables: Callable[[Dict[str, Any]], Dict[str, Any]],
    success_result: Callable[[Dict[str, Any]], Dict[str, Any]],
    results: List[Dict[str, Any]],
) -> Optional[GitHubRateLimitError]:
    """Run one aliased batch mutation, falling back to per-item mutations if it fails.

    Returns the rate-limit error if GitHub throttled us, after marking this
    batch's unattempted items, so the caller stops sending requests. The
    per-item fallback is skipped when throttled: it would only send 25x
    more requests into the same limit.
    """
    try:
        graphql_query(session, batch_query, batch_variables)
    except GitHubRateLimitError as exc:
        results.extend(_rate_limited_results(batch, exc))
        return exc
    except Exception:
        for i, item in enumerate(batch):
            try:
                graphql_query(session, single_query, single_variables(item))
            except GitHubRateLimitError as exc:
                results.extend(_rate_limited_results(batch[i:], exc))
                return exc
            except Exception as item_exc:
                results.append(
                    {"item_ref": item["ref"], "success": False, "error": str(item_exc)}
                )
            else:
                results.append(success_result(item))
        return None

    results.extend(success_result(item) for item in batch)
    return None


def set_field_value_bulk(
    session: requests.Session,
    *,
    org: str,
    project_number: int,
    item_refs: List[str],
    field_name: str,
    value: str,
) -> Dict[str, Any]:
    """Set (or clear) a project field value on one or more items.

    Resolves field info once, then batches GraphQL mutations using aliases.
    If value is empty string, clears the field instead of setting it.

    Args:
        org: GitHub organization
        project_number: Project number
        item_refs: List of item references (e.g., "dealbot#458") or raw
            project item node IDs (strings starting with "PVTI_"). Node IDs
            skip the per-item lookup, making bulk operations much faster when
            you already have them from a prior list_items call.
        field_name: Display name of the project field
        value: Value to set on all items. Empty string clears the field.

    Returns:
        Dict with success_count, failure_count, and per-item results list.
        If GitHub rate-limits the run, no further mutations are sent and
        every unattempted item's result carries ``"rate_limited": True``.
        No audit logging — that's the caller's responsibility.
    """
    results: List[Dict[str, Any]] = []
    is_clear = value == ""

    if is_clear:
        # Clear mode: only need field info, no value resolution
        field_info = _resolve_field_only(
            session,
            org=org,
            project_number=project_number,
            field_name=field_name,
        )
    else:
        # Set mode: resolve field + value mapping once
        field_info = _resolve_field_and_value(
            session,
            org=org,
            project_number=project_number,
            field_name=field_name,
            value=value,
        )

    if not field_info.get("success"):
        for ref in item_refs:
            results.append(
                {"item_ref": ref, "success": False, "error": field_info["error"]}
            )
        return {"success_count": 0, "failure_count": len(item_refs), "results": results}

    project_id = field_info["project_id"]
    field_id = field_info["field_id"]
    mutation_value = field_info.get("mutation_value")  # None for clear

    # For raw node IDs there is no per-item lookup, so batch-fetch the current
    # field values up front; old_value would otherwise be empty in results.
    pvti_refs = [ref for ref in item_refs if ref.startswith("PVTI_")]
    pvti_old_values: Dict[str, str] = {}
    if pvti_refs:
        pvti_old_values = _fetch_old_values_by_node_id(
            session,
            node_ids=pvti_refs,
            field_name=field_info.get("canonical_name", field_name),
        )

    # Resolve each item — collect node IDs and old values
    resolved_items: List[Dict[str, Any]] = []
    for ref in item_refs:
        # If the ref is a raw project item node ID (starts with PVTI_), skip lookup
        if ref.startswith("PVTI_"):
            resolved_items.append(
                {
                    "ref": ref,
                    "node_id": ref,
                    "old_value": pvti_old_values.get(ref, ""),
                }
            )
            continue
        details = get_item(
            session, org=org, project_number=project_number, item_ref=ref
        )
        if not details:
            results.append(
                {
                    "item_ref": ref,
                    "success": False,
                    "error": f"Could not find item: {ref}",
                }
            )
            continue
        node_id = details.get("_node_id")
        if not node_id:
            results.append(
                {
                    "item_ref": ref,
                    "success": False,
                    "error": f"No node ID for item: {ref}",
                }
            )
            continue
        old_value = details.get(field_name, "")
        resolved_items.append({"ref": ref, "node_id": node_id, "old_value": old_value})

    def success_result(item: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "item_ref": item["ref"],
            "success": True,
            "old_value": item["old_value"],
            "new_value": value,
            "field": field_name,
        }

    if is_clear:
        single_query = CLEAR_FIELD_MUTATION

        def single_variables(item: Dict[str, Any]) -> Dict[str, Any]:
            return {
                "projectId": project_id,
                "itemId": item["node_id"],
                "fieldId": field_id,
            }

        def batch_query(n: int) -> str:
            var_defs = ", ".join(
                f"$projectId{i}: ID!, $itemId{i}: ID!, $fieldId{i}: ID!"
                for i in range(n)
            )
            bodies = "\n    ".join(
                f"m{i}: clearProjectV2ItemFieldValue(input: {{projectId: $projectId{i}, itemId: $itemId{i}, fieldId: $fieldId{i}}}) {{ projectV2Item {{ id }} }}"
                for i in range(n)
            )
            return f"mutation({var_defs}) {{\n    {bodies}\n}}"

        def batch_variables(batch: List[Dict[str, Any]]) -> Dict[str, Any]:
            variables: Dict[str, Any] = {}
            for i, item in enumerate(batch):
                for key, val in single_variables(item).items():
                    variables[f"{key}{i}"] = val
            return variables

    else:
        single_query = UPDATE_FIELD_MUTATION

        def single_input(item: Dict[str, Any]) -> Dict[str, Any]:
            return {
                "projectId": project_id,
                "itemId": item["node_id"],
                "fieldId": field_id,
                "value": mutation_value,
            }

        def single_variables(item: Dict[str, Any]) -> Dict[str, Any]:
            return {"input": single_input(item)}

        def batch_query(n: int) -> str:
            var_defs = ", ".join(
                f"$input{i}: UpdateProjectV2ItemFieldValueInput!" for i in range(n)
            )
            bodies = "\n    ".join(
                f"m{i}: updateProjectV2ItemFieldValue(input: $input{i}) {{ projectV2Item {{ id }} }}"
                for i in range(n)
            )
            return f"mutation({var_defs}) {{\n    {bodies}\n}}"

        def batch_variables(batch: List[Dict[str, Any]]) -> Dict[str, Any]:
            return {f"input{i}": single_input(item) for i, item in enumerate(batch)}

    rate_limit_error: Optional[GitHubRateLimitError] = None
    for batch_start in range(0, len(resolved_items), _BATCH_SIZE):
        batch = resolved_items[batch_start : batch_start + _BATCH_SIZE]
        if rate_limit_error is not None:
            results.extend(_rate_limited_results(batch, rate_limit_error))
            continue
        if batch_start:
            time.sleep(_SECONDS_BETWEEN_BATCHES)
        rate_limit_error = _execute_batch(
            session,
            batch=batch,
            batch_query=batch_query(len(batch)),
            batch_variables=batch_variables(batch),
            single_query=single_query,
            single_variables=single_variables,
            success_result=success_result,
            results=results,
        )

    success_count = sum(1 for r in results if r.get("success"))
    failure_count = sum(1 for r in results if not r.get("success"))

    return {
        "success_count": success_count,
        "failure_count": failure_count,
        "results": results,
    }


def set_field_value(
    session: requests.Session,
    *,
    org: str,
    project_number: int,
    item_ref: str,
    field_name: str,
    value: str,
) -> Dict[str, Any]:
    """Set a project field value on a single item.

    Thin wrapper around set_field_value_bulk for single-item convenience.

    Args:
        org: GitHub organization
        project_number: Project number
        item_ref: Item reference (e.g., "dealbot#111", "Owner/repo#111", or URL)
        field_name: Display name of the project field (e.g., "Status", "Cycle Theme")
        value: Display name of the option (e.g., "🐱 Todo") or raw value for text/number fields

    Returns:
        Dict with result info (success, old_value, new_value, etc.)
        No audit logging — that's the caller's responsibility.
    """
    bulk_result = set_field_value_bulk(
        session,
        org=org,
        project_number=project_number,
        item_refs=[item_ref],
        field_name=field_name,
        value=value,
    )
    # Return the single item's result directly
    if bulk_result["results"]:
        return bulk_result["results"][0]
    return {"success": False, "error": "No results returned"}
