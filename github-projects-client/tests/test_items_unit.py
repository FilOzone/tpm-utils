"""
Unit tests for items.py — no network access required.

These test _format_item and related helpers with mocked REST API responses.

Run:
    cd github-projects-client
    uv run pytest tests/test_items_unit.py -v
"""

from __future__ import annotations

from github_projects_client.items import _format_item


# A minimal mock of a REST API item response
MOCK_ITEM = {
    "node_id": "PVTI_lADOBt3abc4AkXYZzgZ1234",
    "content": {
        "url": "https://api.github.com/repos/FilOzone/dealbot/issues/458",
        "number": 458,
        "title": "chore: release to production (main)",
        "assignees": [{"login": "SgtPooki"}],
    },
    "fields": [
        {"name": "Status", "value": {"name": "🐱 Todo"}},
        {"name": "Cycle Theme", "value": "Dealbot"},
        {"name": "Milestone", "value": {"title": "M4.2: mainnet GA"}},
    ],
}

MOCK_ITEM_ID_ONLY = {
    "id": "PVTI_fallback_id_field",
    "content": {
        "url": "https://api.github.com/repos/FilOzone/synapse-sdk/pulls/748",
        "number": 748,
        "title": "chore(master): release synapse-sdk 0.40.5",
        "assignees": [],
    },
    "fields": [
        {"name": "Status", "value": {"name": "🐱 Todo"}},
    ],
}


class TestFormatItemNodeId:
    """Tests for the 'Node ID' synthetic field in _format_item."""

    def test_node_id_field_returned_when_requested(self):
        result = _format_item(MOCK_ITEM, ["Title", "Node ID"])
        assert "Node ID" in result
        assert result["Node ID"] == "PVTI_lADOBt3abc4AkXYZzgZ1234"

    def test_node_id_case_insensitive(self):
        result = _format_item(MOCK_ITEM, ["node id"])
        assert result["node id"] == "PVTI_lADOBt3abc4AkXYZzgZ1234"

    def test_node_id_underscore_variant(self):
        result = _format_item(MOCK_ITEM, ["node_id"])
        assert result["node_id"] == "PVTI_lADOBt3abc4AkXYZzgZ1234"

    def test_node_id_falls_back_to_id_field(self):
        result = _format_item(MOCK_ITEM_ID_ONLY, ["Node ID"])
        assert result["Node ID"] == "PVTI_fallback_id_field"

    def test_node_id_empty_when_missing(self):
        item_no_id = {"content": {"url": "", "number": 1, "title": "x"}, "fields": []}
        result = _format_item(item_no_id, ["Node ID"])
        assert result["Node ID"] == ""

    def test_node_id_not_included_unless_requested(self):
        result = _format_item(MOCK_ITEM, ["Title", "Status"])
        assert "Node ID" not in result
        # But _node_id is always there internally
        assert "_node_id" in result
        assert result["_node_id"] == "PVTI_lADOBt3abc4AkXYZzgZ1234"

    def test_node_id_alongside_other_fields(self):
        result = _format_item(MOCK_ITEM, ["Repository", "Id", "Title", "Node ID", "Status"])
        assert result["Node ID"] == "PVTI_lADOBt3abc4AkXYZzgZ1234"
        assert result["Title"] == "chore: release to production (main)"
        assert result["Id"] == "458"
        assert result["Status"] == "🐱 Todo"
