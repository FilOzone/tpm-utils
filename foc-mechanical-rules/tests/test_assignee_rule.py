"""Unit tests for R-PR-001 (assignee) — mocked GitHub API, no live calls."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from foc_mechanical_rules.mutation_log import MutationLog
from foc_mechanical_rules.rule import Rule
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


@patch("foc_mechanical_rules.rules.assignee.add_assignee", return_value=["alice"])
@patch("foc_mechanical_rules.rules.assignee.get_issue_events")
@patch("foc_mechanical_rules.rules.assignee.get_pull_request")
def test_human_author_gets_assigned(mock_get_pr, mock_get_events, _mock_add):
    mock_get_pr.return_value = _pr(author="alice")
    mock_get_events.return_value = []

    result = AssigneeRule().apply_one(
        MagicMock(), ITEM, dry_run=False, mutation_log=MutationLog()
    )

    assert result.status == "applied"
    assert result.new_value == "alice"
    assert result.item_ref == "FilOzone/dealbot#458"


@patch("foc_mechanical_rules.rules.assignee.add_assignee", return_value=[])
@patch("foc_mechanical_rules.rules.assignee.get_issue_events")
@patch("foc_mechanical_rules.rules.assignee.get_pull_request")
def test_silently_unassigned_author_is_an_error(mock_get_pr, mock_get_events, _add):
    """GitHub can accept the request without assigning the user; that must
    not be reported as applied."""
    mock_get_pr.return_value = _pr(author="alice")
    mock_get_events.return_value = []

    result = AssigneeRule().apply_one(
        MagicMock(), ITEM, dry_run=False, mutation_log=MutationLog()
    )

    assert result.status == "error"
    assert "did not assign 'alice'" in result.reason


@patch("foc_mechanical_rules.rules.assignee.get_issue_events")
@patch("foc_mechanical_rules.rules.assignee.get_pull_request")
def test_dependabot_pr_is_skipped(mock_get_pr, mock_get_events):
    mock_get_pr.return_value = _pr(author="dependabot[bot]")
    mock_get_events.return_value = []

    result = AssigneeRule().apply_one(
        MagicMock(), ITEM, dry_run=False, mutation_log=MutationLog()
    )

    assert result.status == "skipped"
    mock_get_events.assert_not_called()


@patch(
    "foc_mechanical_rules.rules.assignee.add_assignee",
    return_value=["release-captain"],
)
@patch("foc_mechanical_rules.rules.assignee.get_issue_events")
@patch("foc_mechanical_rules.rules.assignee.get_pull_request")
def test_merged_release_pr_from_bot_assigned_to_merger(
    mock_get_pr, mock_get_events, _mock_add
):
    item = {**ITEM, "Title": "chore(master): release 1.2.3"}
    mock_get_pr.return_value = _pr(
        author="FilOzzy", merged=True, merged_by="release-captain"
    )
    mock_get_events.return_value = []

    result = AssigneeRule().apply_one(
        MagicMock(), item, dry_run=False, mutation_log=MutationLog()
    )

    assert result.status == "applied"
    assert result.new_value == "release-captain"


@patch("foc_mechanical_rules.rules.assignee.get_issue_events")
@patch("foc_mechanical_rules.rules.assignee.get_pull_request")
def test_merged_release_pr_without_merger_is_flagged(mock_get_pr, mock_get_events):
    item = {**ITEM, "Title": "chore(master): release 1.2.3"}
    mock_get_pr.return_value = _pr(author="FilOzzy", merged=True, merged_by=None)
    mock_get_events.return_value = []

    result = AssigneeRule().apply_one(
        MagicMock(), item, dry_run=False, mutation_log=MutationLog()
    )

    assert result.status == "flagged"


@patch("foc_mechanical_rules.rules.assignee.get_issue_events")
@patch("foc_mechanical_rules.rules.assignee.get_pull_request")
def test_prior_unassigned_event_is_flagged_not_reassigned(mock_get_pr, mock_get_events):
    mock_get_pr.return_value = _pr(author="alice")
    mock_get_events.return_value = [{"event": "unassigned", "actor": {"login": "bob"}}]

    result = AssigneeRule().apply_one(
        MagicMock(), ITEM, dry_run=False, mutation_log=MutationLog()
    )

    assert result.status == "flagged"
    assert "unassigned" in result.reason


def test_external_item_is_skipped_without_api_calls():
    item = {**ITEM, "Repository": "someoutsideorg/repo"}

    with patch("foc_mechanical_rules.rules.assignee.get_pull_request") as mock_get_pr:
        result = AssigneeRule().apply_one(
            MagicMock(), item, dry_run=False, mutation_log=MutationLog()
        )

    assert result.status == "skipped"
    mock_get_pr.assert_not_called()


@patch("foc_mechanical_rules.rules.assignee.add_assignee")
@patch("foc_mechanical_rules.rules.assignee.get_issue_events")
@patch("foc_mechanical_rules.rules.assignee.get_pull_request")
def test_dry_run_does_not_mutate(mock_get_pr, mock_get_events, mock_add_assignee):
    mock_get_pr.return_value = _pr(author="alice")
    mock_get_events.return_value = []

    result = AssigneeRule().apply_one(
        MagicMock(), ITEM, dry_run=True, mutation_log=MutationLog()
    )

    assert result.status == "applied"
    assert result.new_value == "alice"
    mock_add_assignee.assert_not_called()


def test_assignee_rule_is_a_rule_and_run_works():
    # Regression: AssigneeRule must inherit from Rule to pick up run(), or
    # the runner's rule.run(session, dry_run=...) call blows up at runtime
    # with an AttributeError that apply_one-only tests never exercise.
    rule = AssigneeRule()
    assert isinstance(rule, Rule)

    with (
        patch.object(rule, "select", return_value=[ITEM]),
        patch(
            "foc_mechanical_rules.rules.assignee.get_pull_request",
            return_value=_pr(author="alice"),
        ),
        patch(
            "foc_mechanical_rules.rules.assignee.get_issue_events",
            return_value=[],
        ),
    ):
        run = rule.run(MagicMock(), dry_run=True, mutation_log=MutationLog())

    assert run.rule_id == "R-PR-001"
    assert [r.status for r in run.results] == ["applied"]


def test_add_assignee_forbidden_names_the_fixes():
    """A 403 (public repo, as on filecoin-project/FIPs#1294) must explain the
    permissions gap and keep GitHub's own message, not just "Forbidden"."""
    import json

    import pytest
    import requests

    from foc_mechanical_rules.github_api import add_assignee

    resp = requests.Response()
    resp.status_code = 403
    resp.reason = "Forbidden"
    resp.url = (
        "https://api.github.com/repos/filecoin-project/FIPs/issues/1294/assignees"
    )
    resp._content = json.dumps({"message": "Must have admin rights"}).encode()
    session = MagicMock()
    session.post.return_value = resp

    with pytest.raises(requests.HTTPError) as excinfo:
        add_assignee(
            session, owner="filecoin-project", repo="FIPs", number="1294", login="a"
        )

    message = str(excinfo.value)
    assert "Must have admin rights" in message
    assert "triage+ access" in message and "filecoin-project/FIPs" in message
    assert "assign the PR by hand" in message
