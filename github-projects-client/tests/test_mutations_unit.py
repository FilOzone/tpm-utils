"""
Unit tests for mutations.py — no network access required.

Focus: old_value reporting for bulk mutations addressed by raw PVTI_ node IDs.
Before 2026-07-09, PVTI_ refs skipped the per-item lookup and always reported
old_value as "", which broke the "old → new" reporting the board rules require.

Run:
    cd github-projects-client
    uv run pytest tests/test_mutations_unit.py -v
"""

from __future__ import annotations

from unittest.mock import patch

from github_projects_client.mutations import (
    _fetch_old_values_by_node_id,
    set_field_value_bulk,
)

STATUS_FIELD_OPTIONS = {
    "project_id": "PVT_project1",
    "fields": {
        "Status": {
            "id": "PVTSSF_field1",
            "type": "single_select",
            "options": [
                {"id": "opt_todo", "name": "🐱 Todo"},
                {"id": "opt_done", "name": "🎉 Done"},
            ],
        }
    },
}


class TestFetchOldValuesByNodeId:
    def test_extracts_single_select_and_iteration_values(self):
        graphql_response = {
            "nodes": [
                {"id": "PVTI_a", "fieldValueByName": {"name": "🐱 Todo"}},
                {"id": "PVTI_b", "fieldValueByName": {"title": "202607-1"}},
                {"id": "PVTI_c", "fieldValueByName": None},
            ]
        }
        with patch(
            "github_projects_client.mutations.graphql_query",
            return_value=graphql_response,
        ):
            result = _fetch_old_values_by_node_id(
                None, node_ids=["PVTI_a", "PVTI_b", "PVTI_c"], field_name="Status"
            )
        assert result == {"PVTI_a": "🐱 Todo", "PVTI_b": "202607-1", "PVTI_c": ""}

    def test_lookup_failure_degrades_to_empty(self):
        """A failed lookup must not break the mutation; just omit old values."""
        with patch(
            "github_projects_client.mutations.graphql_query",
            side_effect=RuntimeError("boom"),
        ):
            result = _fetch_old_values_by_node_id(
                None, node_ids=["PVTI_a"], field_name="Status"
            )
        assert result == {}


class TestBulkOldValueForNodeIdRefs:
    def test_pvti_refs_report_old_value(self):
        """Bulk mutations addressed by PVTI_ node IDs must still report the
        old field value in results."""
        old_value_response = {
            "nodes": [
                {"id": "PVTI_a", "fieldValueByName": {"name": "🐱 Todo"}},
                {"id": "PVTI_b", "fieldValueByName": {"name": "⌨️ In Progress"}},
            ]
        }
        calls = []

        def fake_graphql(session, query, variables=None):
            calls.append(query)
            if "fieldValueByName" in query:
                return old_value_response
            return {}  # mutation response is unused

        with (
            patch(
                "github_projects_client.mutations.list_field_options",
                return_value=STATUS_FIELD_OPTIONS,
            ),
            patch(
                "github_projects_client.mutations.graphql_query",
                side_effect=fake_graphql,
            ),
        ):
            result = set_field_value_bulk(
                None,
                org="TestOrg",
                project_number=1,
                item_refs=["PVTI_a", "PVTI_b"],
                field_name="Status",
                value="🎉 Done",
            )

        assert result["success_count"] == 2
        by_ref = {r["item_ref"]: r for r in result["results"]}
        assert by_ref["PVTI_a"]["old_value"] == "🐱 Todo"
        assert by_ref["PVTI_b"]["old_value"] == "⌨️ In Progress"
        assert by_ref["PVTI_a"]["new_value"] == "🎉 Done"

    def test_old_value_lookup_failure_does_not_block_mutation(self):
        def fake_graphql(session, query, variables=None):
            if "fieldValueByName" in query:
                raise RuntimeError("lookup failed")
            return {}

        with (
            patch(
                "github_projects_client.mutations.list_field_options",
                return_value=STATUS_FIELD_OPTIONS,
            ),
            patch(
                "github_projects_client.mutations.graphql_query",
                side_effect=fake_graphql,
            ),
        ):
            result = set_field_value_bulk(
                None,
                org="TestOrg",
                project_number=1,
                item_refs=["PVTI_a"],
                field_name="Status",
                value="🎉 Done",
            )

        assert result["success_count"] == 1
        assert result["results"][0]["old_value"] == ""
