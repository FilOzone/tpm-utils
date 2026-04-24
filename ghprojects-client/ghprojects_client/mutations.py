"""Mutation tools for GitHub Projects v2 — set field values by name."""

from __future__ import annotations

from typing import Any, Dict

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


def set_field_value(
    session: requests.Session,
    *,
    org: str,
    project_number: int,
    item_ref: str,
    field_name: str,
    value: str,
) -> Dict[str, Any]:
    """
    Set a project field value on an item.

    Args:
        org: GitHub organization
        project_number: Project number
        item_ref: Item reference (e.g., "dealbot#111", "Owner/repo#111", or URL)
        field_name: Display name of the project field (e.g., "Status", "Cycle Theme")
        value: Display name of the option (e.g., "🐱 Todo") or raw value for text/number fields

    Returns:
        Dict with result info (success, old_value, new_value, etc.)
        No audit logging ��� that's the caller's responsibility.
    """
    # Resolve item
    details = get_item(
        session, org=org, project_number=project_number, item_ref=item_ref,
    )
    if not details:
        return {"success": False, "error": f"Could not find item: {item_ref}"}

    item_node_id = details.get("_node_id")
    if not item_node_id:
        return {"success": False, "error": f"No node ID for item: {item_ref}"}

    # Get field info and options
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

    # Build the value input based on field type
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

    # Get current value for caller to use (e.g., audit logging)
    old_value = details.get(field_name, "")

    # Execute the mutation
    mutation_input = {
        "projectId": project_id,
        "itemId": item_node_id,
        "fieldId": field_id,
        "value": mutation_value,
    }

    graphql_query(session, UPDATE_FIELD_MUTATION, {"input": mutation_input})

    return {
        "success": True,
        "item": item_ref,
        "field": field_name,
        "old_value": old_value,
        "new_value": value,
    }
