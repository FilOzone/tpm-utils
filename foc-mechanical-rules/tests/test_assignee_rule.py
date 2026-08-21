"""Unit tests for R-PR-001 (assignee) — mocked GitHub API, no live calls."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from foc_mechanical_rules.rules.assignee import AssigneeRule

ITEM = {
    "Repository": "FilOzone/dealbot",
    "Id": "458",
    "Title": "fix: something",
    "url": "https://github.com/FilOzone/dealbot/pull/458",
}


def _pr(author="alice", merged=False, merged_by=None):
    return {
        "user": {"login": author},
        "merged": merged,
        "merged_by": {"login": merged_by} if merged_by else None,
    }


@patch("foc_mechanical_rules.rules.assignee.get_issue_events")
@patch("foc_mechanical_rules.rules.assignee.get_pull_request")
def test_human_author_gets_assigned(mock_get_pr, mock_get_events):
    mock_get_pr.return_value = _pr(author="alice")
    mock_get_events.return_value = []

    result = AssigneeRule().apply_one(MagicMock(), ITEM, dry_run=False)

    assert result.status == "applied"
    assert result.new_value == "alice"
    assert result.item_ref == "FilOzone/dealbot#458"


@patch("foc_mechanical_rules.rules.assignee.get_issue_events")
@patch("foc_mechanical_rules.rules.assignee.get_pull_request")
def test_dependabot_pr_is_skipped(mock_get_pr, mock_get_events):
    mock_get_pr.return_value = _pr(author="dependabot[bot]")
    mock_get_events.return_value = []

    result = AssigneeRule().apply_one(MagicMock(), ITEM, dry_run=False)

    assert result.status == "skipped"
    mock_get_events.assert_not_called()


@patch("foc_mechanical_rules.rules.assignee.get_issue_events")
@patch("foc_mechanical_rules.rules.assignee.get_pull_request")
def test_merged_release_pr_from_bot_assigned_to_merger(mock_get_pr, mock_get_events):
    item = {**ITEM, "Title": "chore(master): release 1.2.3"}
    mock_get_pr.return_value = _pr(
        author="FilOzzy", merged=True, merged_by="release-captain"
    )
    mock_get_events.return_value = []

    result = AssigneeRule().apply_one(MagicMock(), item, dry_run=False)

    assert result.status == "applied"
    assert result.new_value == "release-captain"


@patch("foc_mechanical_rules.rules.assignee.get_issue_events")
@patch("foc_mechanical_rules.rules.assignee.get_pull_request")
def test_merged_release_pr_without_merger_is_flagged(mock_get_pr, mock_get_events):
    item = {**ITEM, "Title": "chore(master): release 1.2.3"}
    mock_get_pr.return_value = _pr(author="FilOzzy", merged=True, merged_by=None)
    mock_get_events.return_value = []

    result = AssigneeRule().apply_one(MagicMock(), item, dry_run=False)

    assert result.status == "flagged"


@patch("foc_mechanical_rules.rules.assignee.get_issue_events")
@patch("foc_mechanical_rules.rules.assignee.get_pull_request")
def test_prior_unassigned_event_is_flagged_not_reassigned(mock_get_pr, mock_get_events):
    mock_get_pr.return_value = _pr(author="alice")
    mock_get_events.return_value = [{"event": "unassigned", "actor": {"login": "bob"}}]

    result = AssigneeRule().apply_one(MagicMock(), ITEM, dry_run=False)

    assert result.status == "flagged"
    assert "unassigned" in result.reason


def test_external_item_is_skipped_without_api_calls():
    item = {**ITEM, "Repository": "someoutsideorg/repo"}

    with patch("foc_mechanical_rules.rules.assignee.get_pull_request") as mock_get_pr:
        result = AssigneeRule().apply_one(MagicMock(), item, dry_run=False)

    assert result.status == "skipped"
    mock_get_pr.assert_not_called()


@patch("foc_mechanical_rules.rules.assignee.add_assignee")
@patch("foc_mechanical_rules.rules.assignee.get_issue_events")
@patch("foc_mechanical_rules.rules.assignee.get_pull_request")
def test_dry_run_does_not_mutate(mock_get_pr, mock_get_events, mock_add_assignee):
    mock_get_pr.return_value = _pr(author="alice")
    mock_get_events.return_value = []

    result = AssigneeRule().apply_one(MagicMock(), ITEM, dry_run=True)

    assert result.status == "applied"
    assert result.new_value == "alice"
    mock_add_assignee.assert_not_called()
