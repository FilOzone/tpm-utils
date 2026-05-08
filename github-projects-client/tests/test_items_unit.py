"""
Unit tests for items.py — no network access required.

These test _format_item and related helpers with mocked REST API responses.

Run:
    cd github-projects-client
    uv run pytest tests/test_items_unit.py -v
"""

from __future__ import annotations

import json

from github_projects_client.items import _format_field_value, _format_item


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
        result = _format_item(
            MOCK_ITEM, ["Repository", "Id", "Title", "Node ID", "Status"]
        )
        assert result["Node ID"] == "PVTI_lADOBt3abc4AkXYZzgZ1234"
        assert result["Title"] == "chore: release to production (main)"
        assert result["Id"] == "458"
        assert result["Status"] == "🐱 Todo"


class TestFormatFieldValueLinkedPRs:
    """Tests for _format_field_value handling of linked PR/issue objects."""

    LINKED_PRS = [
        {
            "number": 487,
            "title": "feat: add retry logic",
            "state": "open",
            "draft": False,
            "repository_url": "https://api.github.com/repos/FilOzone/dealbot",
            "user": {"login": "alice", "avatar_url": "https://..."},
            "labels": [{"name": "enhancement"}],
            "html_url": "https://github.com/FilOzone/dealbot/pull/487",
        },
        {
            "number": 492,
            "title": "fix: handle timeout",
            "state": "closed",
            "draft": True,
            "repository_url": "https://api.github.com/repos/FilOzone/dealbot",
            "user": {"login": "bob"},
        },
    ]

    def test_returns_valid_json(self):
        result = _format_field_value(self.LINKED_PRS)
        parsed = json.loads(result)
        assert isinstance(parsed, list)
        assert len(parsed) == 2

    def test_keeps_useful_fields(self):
        parsed = json.loads(_format_field_value(self.LINKED_PRS))
        first = parsed[0]
        assert first["repo"] == "dealbot"
        assert first["number"] == 487
        assert first["state"] == "open"
        assert first["draft"] is False
        assert first["title"] == "feat: add retry logic"
        assert first["author"] == "alice"

    def test_second_item(self):
        parsed = json.loads(_format_field_value(self.LINKED_PRS))
        second = parsed[1]
        assert second["number"] == 492
        assert second["state"] == "closed"
        assert second["draft"] is True
        assert second["author"] == "bob"

    def test_strips_verbose_fields(self):
        """Full user objects, labels, URLs should NOT be in output."""
        result = _format_field_value(self.LINKED_PRS)
        assert "avatar_url" not in result
        assert "html_url" not in result
        assert "labels" not in result
        assert "enhancement" not in result
        assert "repository_url" not in result

    def test_compact_size(self):
        """Output should be smaller than raw str(value).

        With real API data (~8KB per PR), the ratio is ~50:1.
        With minimal test fixtures it's ~2:1.
        """
        compact = _format_field_value(self.LINKED_PRS)
        raw = str(self.LINKED_PRS)
        assert len(compact) < len(raw)

    def test_single_linked_pr(self):
        parsed = json.loads(_format_field_value([self.LINKED_PRS[0]]))
        assert len(parsed) == 1
        assert parsed[0]["number"] == 487

    def test_empty_list(self):
        result = _format_field_value([])
        assert result == "[]"

    def test_assignee_list_still_works(self):
        """Existing login-based handling should still work."""
        users = [{"login": "alice"}, {"login": "bob"}]
        result = _format_field_value(users)
        assert result == "alice, bob"
