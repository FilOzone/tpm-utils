"""
Unit tests for items.py — no network access required.

These test _format_item and related helpers with mocked REST API responses.
Mock data uses the real GitHub Projects v2 REST API response shapes.

To regenerate or verify mock data, fetch a real item with all fields:

    export GITHUB_TOKEN=$(gh auth token)
    curl -s "https://api.github.com/orgs/FilOzone/projectsV2/14/items \
      ?q=repo:FilOzone/dealbot%20159 \
      &fields=194437026,194437027,194437028,194437029,194437030,194437031, \
              194437032,194437033,194437036,194437037,194437038,194437039, \
              204711739,242588518,244708427,245538973 \
      &per_page=1" \
      -H "Authorization: Bearer $GITHUB_TOKEN" \
      -H "Accept: application/vnd.github+json" \
      -H "X-GitHub-Api-Version: 2022-11-28" | jq '.[0]'

Run:
    cd github-projects-client
    uv run pytest tests/test_items_unit.py -v
"""

from __future__ import annotations

import json

from github_projects_client.items import _format_field_value, _format_item
from github_projects_client.server.formats import build_display_items


# ---------------------------------------------------------------------------
# Mock data — matches real GitHub Projects v2 REST API response shapes.
#
# Each field value uses the exact structure the API returns (verified 2026-05-08
# against FilOzone project #14).  See module docstring for the curl command to
# regenerate.
# ---------------------------------------------------------------------------

# single_select: {"id": "...", "name": {"raw": "...", "html": "..."}, "color": "...", ...}
SINGLE_SELECT_STATUS = {
    "id": "47fc9ee4",
    "name": {"raw": "⌨️ In Progress", "html": "⌨️ In Progress"},
    "description": {"raw": "Actively in progress", "html": "Actively in progress"},
    "color": "YELLOW",
}

SINGLE_SELECT_TODO = {
    "id": "f75ad846",
    "name": {"raw": "🐱 Todo", "html": "🐱 Todo"},
    "description": {"raw": "Ready to start", "html": "Ready to start"},
    "color": "BLUE",
}

# text: {"raw": "...", "html": "..."}
TEXT_CYCLE_THEME = {"raw": "Dealbot", "html": "Dealbot"}

# number: bare numeric value
NUMBER_DEV_DAYS = 0.5

# iteration: {"id": "...", "title": {"raw": "...", "html": "..."}, "start_date": "...", ...}
ITERATION_CYCLE = {
    "id": "af356b6e",
    "start_date": "2026-02-16",
    "duration": 14,
    "title": {"raw": "202602-2 Acies", "html": "202602-2 Acies"},
    "completed": True,
}

# milestone: full GitHub milestone object (title is a plain string, not a dict)
MILESTONE_VALUE = {
    "url": "https://api.github.com/repos/FilOzone/dealbot/milestones/7",
    "html_url": "https://github.com/FilOzone/dealbot/milestone/7",
    "id": 14626044,
    "node_id": "MI_kwDOPdGgVs4A3yz8",
    "number": 7,
    "title": "M4.2: mainnet GA",
    "state": "open",
    "open_issues": 10,
    "closed_issues": 39,
}

# sub_issues_progress: {"total": N, "completed": N, "percent_completed": N}
SUB_ISSUES_PROGRESS = {"total": 2, "completed": 2, "percent_completed": 100}

# reviewers (with requested_reviewers): {"requested_reviewers": [...], "requested_teams": [...]}
REVIEWERS_VALUE = {
    "requested_reviewers": [
        {"login": "rjan90", "id": 8628857},
        {"login": "SgtPooki", "id": 1173416},
    ],
    "requested_teams": [{"slug": "foc-core", "name": "FOC Core"}],
}

# A realistic mock item using real API field shapes.
MOCK_ITEM = {
    "node_id": "PVTI_lADOBt3abc4AkXYZzgZ1234",
    "content": {
        "url": "https://api.github.com/repos/FilOzone/dealbot/issues/458",
        "html_url": "https://github.com/FilOzone/dealbot/issues/458",
        "number": 458,
        "title": "chore: release to production (main)",
        "assignees": [
            {"login": "SgtPooki", "id": 1173416},
        ],
    },
    "fields": [
        {"name": "Status", "data_type": "single_select", "value": SINGLE_SELECT_TODO},
        {"name": "Cycle Theme", "data_type": "text", "value": TEXT_CYCLE_THEME},
        {"name": "Milestone", "data_type": "milestone", "value": MILESTONE_VALUE},
        {"name": "Dev Days Estimate", "data_type": "number", "value": NUMBER_DEV_DAYS},
        {"name": "Cycle", "data_type": "iteration", "value": ITERATION_CYCLE},
        {
            "name": "Sub-issues progress",
            "data_type": "sub_issues_progress",
            "value": SUB_ISSUES_PROGRESS,
        },
        {"name": "Prio", "data_type": "single_select", "value": None},
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
        {"name": "Status", "data_type": "single_select", "value": SINGLE_SELECT_TODO},
    ],
}


# ---------------------------------------------------------------------------
# _format_field_value tests — one class per field type
# ---------------------------------------------------------------------------


class TestFormatFieldValueSingleSelect:
    """single_select: name is {"raw": "...", "html": "..."}, not a plain string."""

    def test_returns_raw_name(self):
        assert _format_field_value(SINGLE_SELECT_STATUS) == "⌨️ In Progress"

    def test_todo_status(self):
        assert _format_field_value(SINGLE_SELECT_TODO) == "🐱 Todo"

    def test_null_returns_empty(self):
        assert _format_field_value(None) == ""


class TestFormatFieldValueText:
    """text: {"raw": "...", "html": "..."}."""

    def test_returns_raw(self):
        assert _format_field_value(TEXT_CYCLE_THEME) == "Dealbot"


class TestFormatFieldValueNumber:
    """number: bare numeric value."""

    def test_float(self):
        assert _format_field_value(0.5) == "0.5"

    def test_int(self):
        assert _format_field_value(3) == "3"

    def test_zero(self):
        assert _format_field_value(0) == "0"


class TestFormatFieldValueIteration:
    """iteration: title is {"raw": "...", "html": "..."}, not a plain string.

    This was a bug — _format_field_value checked isinstance(title, str) but the
    REST API returns title as a dict.  See Bug 2 fix in items.py.
    """

    def test_returns_title_raw(self):
        assert _format_field_value(ITERATION_CYCLE) == "202602-2 Acies"

    def test_null_value_returns_empty(self):
        assert _format_field_value(None) == ""


class TestFormatFieldValueMilestone:
    """milestone: full GitHub milestone object — title is a plain string."""

    def test_returns_title(self):
        assert _format_field_value(MILESTONE_VALUE) == "M4.2: mainnet GA"


class TestFormatFieldValueSubIssuesProgress:
    """sub_issues_progress: {"total": N, "completed": N, "percent_completed": N}.

    Previously returned "" (silent data loss) because no dict branch matched.
    """

    def test_returns_completed_over_total(self):
        assert _format_field_value(SUB_ISSUES_PROGRESS) == "2/2"

    def test_partial_progress(self):
        assert (
            _format_field_value({"total": 5, "completed": 3, "percent_completed": 60})
            == "3/5"
        )

    def test_zero_progress(self):
        assert (
            _format_field_value({"total": 4, "completed": 0, "percent_completed": 0})
            == "0/4"
        )


class TestFormatFieldValueReviewers:
    """reviewers: {"requested_reviewers": [...], "requested_teams": [...]}."""

    def test_returns_logins_and_teams(self):
        result = _format_field_value(REVIEWERS_VALUE)
        assert "rjan90" in result
        assert "SgtPooki" in result
        assert "foc-core" in result

    def test_empty_reviewers(self):
        result = _format_field_value({"requested_reviewers": [], "requested_teams": []})
        assert result == ""


class TestFormatFieldValueLinkedPRs:
    """linked_pull_requests: list of full GitHub PR objects (~8KB each)."""

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
        parsed = json.loads(_format_field_value(self.LINKED_PRS))
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

    def test_strips_verbose_fields(self):
        result = _format_field_value(self.LINKED_PRS)
        assert "avatar_url" not in result
        assert "html_url" not in result
        assert "labels" not in result
        assert "repository_url" not in result

    def test_empty_list(self):
        assert _format_field_value([]) == "[]"

    def test_assignee_list_still_works(self):
        users = [{"login": "alice"}, {"login": "bob"}]
        assert _format_field_value(users) == "alice, bob"


class TestFormatItemLinkedPRs:
    """'Linked pull requests' must always be a real JSON array, never a
    JSON-encoded string and never ""; jq consumers need one consistent shape.
    (Added 2026-07-09 after a sweep retry caused by the string/array split.)"""

    ITEM_WITH_LINKED = {
        "node_id": "PVTI_linked1",
        "content": {
            "url": "https://api.github.com/repos/FilOzone/dealbot/issues/500",
            "number": 500,
            "title": "an issue",
            "assignees": [],
        },
        "fields": [
            {
                "name": "Linked pull requests",
                "data_type": "linked_pull_requests",
                "value": TestFormatFieldValueLinkedPRs.LINKED_PRS,
            },
        ],
    }

    def test_returns_real_array(self):
        result = _format_item(self.ITEM_WITH_LINKED, ["Linked pull requests"])
        value = result["Linked pull requests"]
        assert isinstance(value, list)
        assert value[0]["number"] == 487
        assert value[0]["repo"] == "dealbot"
        assert value[0]["author"] == "alice"

    def test_empty_value_returns_empty_array(self):
        item = dict(self.ITEM_WITH_LINKED)
        item["fields"] = [
            {
                "name": "Linked pull requests",
                "data_type": "linked_pull_requests",
                "value": [],
            }
        ]
        result = _format_item(item, ["Linked pull requests"])
        assert result["Linked pull requests"] == []

    def test_absent_field_returns_empty_array(self):
        """When the REST API omits the field entirely (no linked PRs), the
        requested field must still come back as [], not ""."""
        result = _format_item(MOCK_ITEM, ["Linked pull requests"])
        assert result["Linked pull requests"] == []


# ---------------------------------------------------------------------------
# _format_item tests — full item formatting with real field shapes
# ---------------------------------------------------------------------------


class TestFormatItemNodeId:
    """Tests for the 'Node ID' synthetic field in _format_item."""

    def test_node_id_field_returned_when_requested(self):
        result = _format_item(MOCK_ITEM, ["Title", "Node ID"])
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
        assert "_node_id" in result
        assert result["_node_id"] == "PVTI_lADOBt3abc4AkXYZzgZ1234"


class TestFormatItemAllFieldTypes:
    """Verify _format_item correctly renders all field types from MOCK_ITEM."""

    def test_all_fields_render(self):
        fields = [
            "Repository",
            "Id",
            "Title",
            "Status",
            "Cycle Theme",
            "Milestone",
            "Dev Days Estimate",
            "Cycle",
            "Sub-issues progress",
        ]
        result = _format_item(MOCK_ITEM, fields)
        assert result["Repository"] == "FilOzone/dealbot"
        assert result["Id"] == "458"
        assert result["Title"] == "chore: release to production (main)"
        assert result["Status"] == "🐱 Todo"
        assert result["Cycle Theme"] == "Dealbot"
        assert result["Milestone"] == "M4.2: mainnet GA"
        assert result["Dev Days Estimate"] == "0.5"
        assert result["Cycle"] == "202602-2 Acies"
        assert result["Sub-issues progress"] == "2/2"

    def test_null_field_renders_as_empty(self):
        """Fields with null value should render as empty string, not vanish."""
        result = _format_item(MOCK_ITEM, ["Prio"])
        assert result["Prio"] == ""

    def test_unrequested_field_not_present(self):
        result = _format_item(MOCK_ITEM, ["Status"])
        assert "Cycle" not in result


# ---------------------------------------------------------------------------
# build_display_items tests
# ---------------------------------------------------------------------------


class TestBuildDisplayItems:
    """Tests for build_display_items — strips _internal fields, preserves empties."""

    def test_strips_underscore_fields(self):
        items = [{"Title": "foo", "_node_id": "PVTI_abc"}]
        result = build_display_items(items)
        assert "_node_id" not in result[0]
        assert result[0]["Title"] == "foo"

    def test_preserves_empty_strings(self):
        """Empty string means 'field has no value', not 'field missing'."""
        items = [{"Title": "foo", "Cycle": "", "Status": "🐱 Todo"}]
        result = build_display_items(items)
        assert result[0]["Cycle"] == ""

    def test_preserves_none_values(self):
        items = [{"Title": "foo", "Prio": None}]
        result = build_display_items(items)
        assert "Prio" in result[0]

    def test_multiple_items(self):
        items = [
            {"Title": "a", "_node_id": "x", "Status": ""},
            {"Title": "b", "_node_id": "y", "Status": "🐱 Todo"},
        ]
        result = build_display_items(items)
        assert len(result) == 2
        assert "_node_id" not in result[0]
        assert result[0]["Status"] == ""
        assert result[1]["Status"] == "🐱 Todo"
