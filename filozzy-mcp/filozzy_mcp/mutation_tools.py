"""Mutation tools for FOC project board (Projects v2)."""

from __future__ import annotations

from typing import Any, Dict, Optional

import requests

from foc_pr_report.foc_project14_client import (
    FILOZ_ORG,
    PROJECT_NUMBER,
    graphql_query,
)

from filozzy_mcp.action_log import log_action
from filozzy_mcp.read_tools import list_field_options, list_project_items


UPDATE_FIELD_MUTATION = """
mutation($input: UpdateProjectV2ItemFieldValueInput!) {
    updateProjectV2ItemFieldValue(input: $input) {
        projectV2Item {
            id
        }
    }
}
"""


def _resolve_item_node_id(
    session: requests.Session,
    item_ref: str,
    *,
    org: str = FILOZ_ORG,
    project_number: int = PROJECT_NUMBER,
) -> Optional[str]:
    """Resolve an item reference (e.g., 'dealbot#111') to its project item node ID."""
    from filozzy_mcp.read_tools import get_item_details

    details = get_item_details(
        session, item_ref=item_ref, org=org, project_number=project_number,
    )
    if details is None:
        return None
    return details.get("_node_id")


def set_item_field(
    session: requests.Session,
    *,
    item_ref: str,
    field_name: str,
    value: str,
    org: str = FILOZ_ORG,
    project_number: int = PROJECT_NUMBER,
) -> Dict[str, Any]:
    """
    Set a project field value on an item.

    Args:
        item_ref: Item reference (e.g., "dealbot#111", "FilOzone/dealbot#111", or URL)
        field_name: Display name of the project field (e.g., "Status", "Cycle Theme")
        value: Display name of the option (e.g., "🐱 Todo") or raw value for text/number fields
        org: GitHub organization
        project_number: Project number

    Returns:
        Dict with result info (success, old_value, new_value, etc.)
    """
    # Resolve item node ID
    item_node_id = _resolve_item_node_id(
        session, item_ref, org=org, project_number=project_number,
    )
    if not item_node_id:
        result = {"success": False, "error": f"Could not find item: {item_ref}"}
        log_action("set_item_field", {"item_ref": item_ref, "field": field_name, "value": value}, "item_not_found")
        return result

    # Get field info and options
    field_data = list_field_options(
        session, field_name=field_name, org=org, project_number=project_number,
    )
    project_id = field_data["project_id"]
    fields = field_data.get("fields", {})

    if not fields:
        result = {"success": False, "error": f"Field not found: {field_name}"}
        log_action("set_item_field", {"item_ref": item_ref, "field": field_name, "value": value}, "field_not_found")
        return result

    field_info = next(iter(fields.values()))
    field_id = field_info["id"]
    field_type = field_info.get("type", "unknown")

    # Build the value input based on field type
    mutation_value: Dict[str, Any] = {}

    if field_type == "single_select":
        # Find the option ID by name (case-insensitive)
        option_id = None
        for opt in field_info.get("options", []):
            if opt["name"].lower() == value.lower():
                option_id = opt["id"]
                break
        if option_id is None:
            available = [opt["name"] for opt in field_info.get("options", [])]
            result = {
                "success": False,
                "error": f"Option '{value}' not found for field '{field_name}'. Available: {available}",
            }
            log_action("set_item_field", {"item_ref": item_ref, "field": field_name, "value": value}, "option_not_found")
            return result
        mutation_value = {"singleSelectOptionId": option_id}

    elif field_type == "iteration":
        # Find iteration by title
        iteration_id = None
        for it in field_info.get("iterations", []) + field_info.get("completed_iterations", []):
            if it["title"].lower() == value.lower():
                iteration_id = it["id"]
                break
        if iteration_id is None:
            available = [it["title"] for it in field_info.get("iterations", [])]
            result = {
                "success": False,
                "error": f"Iteration '{value}' not found for field '{field_name}'. Active iterations: {available}",
            }
            log_action("set_item_field", {"item_ref": item_ref, "field": field_name, "value": value}, "iteration_not_found")
            return result
        mutation_value = {"iterationId": iteration_id}

    elif field_type in ("TEXT",):
        mutation_value = {"text": value}

    elif field_type in ("NUMBER",):
        try:
            mutation_value = {"number": float(value)}
        except ValueError:
            result = {"success": False, "error": f"'{value}' is not a valid number for field '{field_name}'"}
            log_action("set_item_field", {"item_ref": item_ref, "field": field_name, "value": value}, "invalid_number")
            return result

    elif field_type in ("DATE",):
        mutation_value = {"date": value}

    else:
        result = {"success": False, "error": f"Unsupported field type: {field_type} for field '{field_name}'"}
        log_action("set_item_field", {"item_ref": item_ref, "field": field_name, "value": value}, "unsupported_type")
        return result

    # Get current value for logging
    from filozzy_mcp.read_tools import get_item_details
    current = get_item_details(session, item_ref=item_ref, org=org, project_number=project_number)
    old_value = current.get(field_name, "") if current else ""

    # Execute the mutation
    mutation_input = {
        "projectId": project_id,
        "itemId": item_node_id,
        "fieldId": field_id,
        "value": mutation_value,
    }

    graphql_query(session, UPDATE_FIELD_MUTATION, {"input": mutation_input})

    log_action(
        "set_item_field",
        {"item_ref": item_ref, "field": field_name, "value": value},
        "success",
        old_value=old_value,
        new_value=value,
    )

    return {
        "success": True,
        "item": item_ref,
        "field": field_name,
        "old_value": old_value,
        "new_value": value,
    }
