"""Mutation tools for GitHub Projects v2 — set field values by name."""

from __future__ import annotations

from typing import Any, Dict, List

import requests

from .api import graphql_query
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
        session, org=org, project_number=project_number, field_name=field_name,
    )
    project_id = field_data["project_id"]
    fields = field_data.get("fields", {})

    if not fields:
        return {"success": False, "error": f"Field not found: {field_name}"}

    field_info = next(iter(fields.values()))
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
        for it in field_info.get("iterations", []) + field_info.get("completed_iterations", []):
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
            return {"success": False, "error": f"'{value}' is not a valid number for field '{field_name}'"}

    elif field_type in ("DATE",):
        mutation_value = {"date": value}

    else:
        return {"success": False, "error": f"Unsupported field type: {field_type} for field '{field_name}'"}

    return {
        "success": True,
        "project_id": project_id,
        "field_id": field_id,
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
        session, org=org, project_number=project_number, field_name=field_name,
    )
    project_id = field_data["project_id"]
    fields = field_data.get("fields", {})

    if not fields:
        return {"success": False, "error": f"Field not found: {field_name}"}

    field_info = next(iter(fields.values()))
    field_id = field_info["id"]

    return {"success": True, "project_id": project_id, "field_id": field_id}


def _execute_clear_batch(
    session: requests.Session,
    *,
    project_id: str,
    field_id: str,
    batch: List[Dict[str, Any]],
    field_name: str,
    results: List[Dict[str, Any]],
) -> None:
    """Execute a batch of clear mutations using GraphQL aliases."""
    var_defs = ", ".join(
        f"$projectId{i}: ID!, $itemId{i}: ID!, $fieldId{i}: ID!"
        for i in range(len(batch))
    )
    mutation_bodies = "\n    ".join(
        f"m{i}: clearProjectV2ItemFieldValue(input: {{projectId: $projectId{i}, itemId: $itemId{i}, fieldId: $fieldId{i}}}) {{ projectV2Item {{ id }} }}"
        for i in range(len(batch))
    )
    query = f"mutation({var_defs}) {{\n    {mutation_bodies}\n}}"

    variables = {}
    for i, item in enumerate(batch):
        variables[f"projectId{i}"] = project_id
        variables[f"itemId{i}"] = item["node_id"]
        variables[f"fieldId{i}"] = field_id

    try:
        graphql_query(session, query, variables)
        for item in batch:
            results.append({
                "item": item["ref"],
                "success": True,
                "old_value": item["old_value"],
                "new_value": "",
                "field": field_name,
            })
    except Exception:
        # Fall back to individual clears
        for item in batch:
            try:
                graphql_query(session, CLEAR_FIELD_MUTATION, {
                    "projectId": project_id,
                    "itemId": item["node_id"],
                    "fieldId": field_id,
                })
                results.append({
                    "item": item["ref"],
                    "success": True,
                    "old_value": item["old_value"],
                    "new_value": "",
                    "field": field_name,
                })
            except Exception as item_exc:
                results.append({
                    "item": item["ref"],
                    "success": False,
                    "error": str(item_exc),
                })


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
        item_refs: List of item references
        field_name: Display name of the project field
        value: Value to set on all items. Empty string clears the field.

    Returns:
        Dict with success_count, failure_count, and per-item results list.
        No audit logging — that's the caller's responsibility.
    """
    results: List[Dict[str, Any]] = []
    is_clear = value == ""

    if is_clear:
        # Clear mode: only need field info, no value resolution
        field_info = _resolve_field_only(
            session, org=org, project_number=project_number, field_name=field_name,
        )
    else:
        # Set mode: resolve field + value mapping once
        field_info = _resolve_field_and_value(
            session, org=org, project_number=project_number,
            field_name=field_name, value=value,
        )

    if not field_info.get("success"):
        for ref in item_refs:
            results.append({"item": ref, "success": False, "error": field_info["error"]})
        return {"success_count": 0, "failure_count": len(item_refs), "results": results}

    project_id = field_info["project_id"]
    field_id = field_info["field_id"]
    mutation_value = field_info.get("mutation_value")  # None for clear

    # Resolve each item — collect node IDs and old values
    resolved_items: List[Dict[str, Any]] = []
    for ref in item_refs:
        details = get_item(session, org=org, project_number=project_number, item_ref=ref)
        if not details:
            results.append({"item": ref, "success": False, "error": f"Could not find item: {ref}"})
            continue
        node_id = details.get("_node_id")
        if not node_id:
            results.append({"item": ref, "success": False, "error": f"No node ID for item: {ref}"})
            continue
        old_value = details.get(field_name, "")
        resolved_items.append({"ref": ref, "node_id": node_id, "old_value": old_value})

    # Execute mutations in batches
    for batch_start in range(0, len(resolved_items), _BATCH_SIZE):
        batch = resolved_items[batch_start:batch_start + _BATCH_SIZE]

        if is_clear:
            _execute_clear_batch(
                session, project_id=project_id, field_id=field_id,
                batch=batch, field_name=field_name, results=results,
            )
        else:
            # Build aliased update mutation query
            var_defs = ", ".join(
                f"$input{i}: UpdateProjectV2ItemFieldValueInput!" for i in range(len(batch))
            )
            mutation_bodies = "\n    ".join(
                f"m{i}: updateProjectV2ItemFieldValue(input: $input{i}) {{ projectV2Item {{ id }} }}"
                for i in range(len(batch))
            )
            query = f"mutation({var_defs}) {{\n    {mutation_bodies}\n}}"

            variables = {}
            for i, item in enumerate(batch):
                variables[f"input{i}"] = {
                    "projectId": project_id,
                    "itemId": item["node_id"],
                    "fieldId": field_id,
                    "value": mutation_value,
                }

            try:
                graphql_query(session, query, variables)
                for item in batch:
                    results.append({
                        "item": item["ref"],
                        "success": True,
                        "old_value": item["old_value"],
                        "new_value": value,
                        "field": field_name,
                    })
            except Exception:
                # Batch failed — fall back to individual mutations
                for item in batch:
                    try:
                        single_input = {
                            "projectId": project_id,
                            "itemId": item["node_id"],
                            "fieldId": field_id,
                            "value": mutation_value,
                        }
                        graphql_query(session, UPDATE_FIELD_MUTATION, {"input": single_input})
                        results.append({
                            "item": item["ref"],
                            "success": True,
                            "old_value": item["old_value"],
                            "new_value": value,
                            "field": field_name,
                        })
                    except Exception as item_exc:
                        results.append({
                            "item": item["ref"],
                            "success": False,
                            "error": str(item_exc),
                        })

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
