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

from github_projects_client.api import GitHubRateLimitError

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


def _node_ids(n: int) -> list[str]:
    return [f"PVTI_{i}" for i in range(n)]


def _run_bulk(fake_graphql, item_refs, value="🎉 Done"):
    with (
        patch(
            "github_projects_client.mutations.list_field_options",
            return_value=STATUS_FIELD_OPTIONS,
        ),
        patch(
            "github_projects_client.mutations.graphql_query",
            side_effect=fake_graphql,
        ),
        patch("github_projects_client.mutations.time.sleep") as sleep,
    ):
        result = set_field_value_bulk(
            None,
            org="TestOrg",
            project_number=1,
            item_refs=item_refs,
            field_name="Status",
            value=value,
        )
    return result, sleep


class TestBulkRateLimiting:
    def test_paces_mutation_batches(self):
        def fake_graphql(session, query, variables=None):
            return {"nodes": []} if "fieldValueByName" in query else {}

        result, sleep = _run_bulk(fake_graphql, _node_ids(60))  # 3 batches

        assert result["success_count"] == 60
        assert sleep.call_count == 2  # between batches, not before the first
        sleep.assert_called_with(1.0)

    def test_stops_sending_after_rate_limit_and_skips_per_item_fallback(self):
        mutation_calls = []

        def fake_graphql(session, query, variables=None):
            if "fieldValueByName" in query:
                return {"nodes": []}
            mutation_calls.append(variables)
            if len(mutation_calls) == 2:
                raise GitHubRateLimitError("secondary rate limit")
            return {}

        result, _ = _run_bulk(fake_graphql, _node_ids(60))

        assert len(mutation_calls) == 2  # no fallback, no third batch
        assert result["success_count"] == 25
        limited = [r for r in result["results"] if r.get("rate_limited")]
        assert len(limited) == 35
        assert all(not r["success"] for r in limited)

    def test_rate_limit_during_per_item_fallback_stops_immediately(self):
        mutation_calls = []

        def fake_graphql(session, query, variables=None):
            if "fieldValueByName" in query:
                return {"nodes": []}
            mutation_calls.append(variables)
            if len(mutation_calls) == 1:
                raise RuntimeError("batch failed for a non-throttling reason")
            if len(mutation_calls) == 3:
                raise GitHubRateLimitError("secondary rate limit")
            return {}

        result, _ = _run_bulk(fake_graphql, _node_ids(5))

        # 1 failed batch + 1 successful single + 1 throttled single.
        assert len(mutation_calls) == 3
        assert result["success_count"] == 1
        assert sum(1 for r in result["results"] if r.get("rate_limited")) == 4

    def test_non_rate_limit_failure_still_falls_back_per_item(self):
        mutation_calls = []

        def fake_graphql(session, query, variables=None):
            if "fieldValueByName" in query:
                return {"nodes": []}
            mutation_calls.append(variables)
            if len(mutation_calls) == 1:
                raise RuntimeError("one bad item poisons the batch")
            if variables["input"]["itemId"] == "PVTI_1":
                raise RuntimeError("bad item")
            return {}

        result, _ = _run_bulk(fake_graphql, _node_ids(3))

        assert result["success_count"] == 2
        failed = [r for r in result["results"] if not r["success"]]
        assert [r["item_ref"] for r in failed] == ["PVTI_1"]
        assert not failed[0].get("rate_limited")

    def test_clear_mode_batches_with_aliased_variables(self):
        mutation_calls = []

        def fake_graphql(session, query, variables=None):
            if "fieldValueByName" in query:
                return {"nodes": []}
            mutation_calls.append((query, variables))
            return {}

        result, _ = _run_bulk(fake_graphql, _node_ids(2), value="")

        assert result["success_count"] == 2
        assert len(mutation_calls) == 1
        query, variables = mutation_calls[0]
        assert "clearProjectV2ItemFieldValue" in query
        assert variables["itemId0"] == "PVTI_0"
        assert variables["itemId1"] == "PVTI_1"
        assert variables["projectId1"] == "PVT_project1"
        assert variables["fieldId0"] == "PVTSSF_field1"
