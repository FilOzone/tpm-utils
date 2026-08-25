"""Unit tests for R-PR-010 (Triage PR status routing) — mocked GitHub API, no live calls."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from foc_mechanical_rules.rule import ActionResult, Rule
from foc_mechanical_rules.rules.pr_status import PRStatusRule

ITEM = {
    "Repository": "FilOzone/dealbot",
    "Id": "458",
    "Title": "fix: something",
    "url": "https://github.com/FilOzone/dealbot/pull/458",
    "_node_id": "PVTI_abc123",
}

# get_pr_review_context's query asks GitHub for just the last (most recent)
# status-changed event via `timelineItems(last: 1, ...)`, so these fixtures
# hold at most one element, matching what the real query returns.
NEVER_LEFT_TRIAGE = [
    {"createdAt": "2026-08-01T00:00:00Z", "previousStatus": "", "status": "📌 Triage"},
]

RETURNED_TO_TRIAGE = [
    {
        "createdAt": "2026-08-10T00:00:00Z",
        "previousStatus": "⌨️ In Progress",
        "status": "📌 Triage",
    },
]


def _pr(
    *,
    is_draft=False,
    author="alice",
    last_commit=None,
    reviews=None,
    review_requests=None,
    comments=None,
    timeline=NEVER_LEFT_TRIAGE,
):
    return {
        "isDraft": is_draft,
        "author": {"login": author},
        "commits": {
            "nodes": [{"commit": {"committedDate": last_commit}}] if last_commit else []
        },
        "reviews": {"nodes": reviews or []},
        "reviewRequests": {"nodes": review_requests or []},
        "comments": {"nodes": comments or []},
        "timelineItems": {"nodes": timeline},
    }


def _review(login, state, submitted_at, typename="User"):
    return {
        "author": {"login": login, "__typename": typename},
        "state": state,
        "submittedAt": submitted_at,
    }


def _comment(login, created_at, typename="User"):
    return {"author": {"login": login, "__typename": typename}, "createdAt": created_at}


@patch("foc_mechanical_rules.rules.pr_status.get_pr_review_context")
def test_explicit_return_to_triage_is_flagged(mock_ctx):
    mock_ctx.return_value = _pr(is_draft=True, timeline=RETURNED_TO_TRIAGE)

    result = PRStatusRule().apply_one(
        MagicMock(), ITEM, dry_run=False, mutation_log=None
    )

    assert result.status == "flagged"
    assert "moved it back" in result.reason


@patch("foc_mechanical_rules.rules.pr_status.get_pr_review_context")
def test_draft_pr_moves_to_in_progress(mock_ctx):
    mock_ctx.return_value = _pr(is_draft=True)

    result = PRStatusRule().apply_one(
        MagicMock(), ITEM, dry_run=False, mutation_log=None
    )

    assert result.status == "pending"
    assert result.new_value == "⌨️ In Progress"
    assert result.node_id == "PVTI_abc123"


@patch("foc_mechanical_rules.rules.pr_status.get_pr_review_context")
def test_bot_authored_pr_moves_to_todo(mock_ctx):
    mock_ctx.return_value = _pr(author="dependabot")

    result = PRStatusRule().apply_one(
        MagicMock(), ITEM, dry_run=False, mutation_log=None
    )

    assert result.status == "pending"
    assert result.new_value == "🐱 Todo"


@patch("foc_mechanical_rules.rules.pr_status.get_pr_review_context")
def test_release_pr_moves_to_todo(mock_ctx):
    item = {**ITEM, "Title": "chore(master): release 1.2.3"}
    mock_ctx.return_value = _pr(author="alice")

    result = PRStatusRule().apply_one(
        MagicMock(), item, dry_run=False, mutation_log=None
    )

    assert result.status == "pending"
    assert result.new_value == "🐱 Todo"


@patch(
    "foc_mechanical_rules.rules.pr_status.get_collaborator_permission",
    return_value="write",
)
@patch("foc_mechanical_rules.rules.pr_status.get_pr_review_context")
def test_authoritative_approval_moves_to_approved(mock_ctx, mock_perm):
    mock_ctx.return_value = _pr(
        last_commit="2026-08-01T00:00:00Z",
        reviews=[_review("bob", "APPROVED", "2026-08-02T00:00:00Z")],
    )

    result = PRStatusRule().apply_one(
        MagicMock(), ITEM, dry_run=False, mutation_log=None
    )

    assert result.status == "pending"
    assert result.new_value == "✔️ Approved by reviewer"


@patch(
    "foc_mechanical_rules.rules.pr_status.get_collaborator_permission",
    return_value="read",
)
@patch("foc_mechanical_rules.rules.pr_status.get_pr_review_context")
def test_read_access_approval_does_not_count(mock_ctx, mock_perm):
    mock_ctx.return_value = _pr(
        last_commit="2026-08-01T00:00:00Z",
        reviews=[_review("bob", "APPROVED", "2026-08-02T00:00:00Z")],
    )

    result = PRStatusRule().apply_one(
        MagicMock(), ITEM, dry_run=False, mutation_log=None
    )

    # No qualifying feedback and no qualifying approval -> row 6, Awaiting review.
    assert result.status == "pending"
    assert result.new_value == "🔎 Awaiting review"


@patch(
    "foc_mechanical_rules.rules.pr_status.get_collaborator_permission",
    return_value="write",
)
@patch("foc_mechanical_rules.rules.pr_status.get_pr_review_context")
def test_blocking_changes_requested_moves_to_in_progress(mock_ctx, mock_perm):
    mock_ctx.return_value = _pr(
        last_commit="2026-08-01T00:00:00Z",
        reviews=[_review("bob", "CHANGES_REQUESTED", "2026-08-02T00:00:00Z")],
    )

    result = PRStatusRule().apply_one(
        MagicMock(), ITEM, dry_run=False, mutation_log=None
    )

    assert result.status == "pending"
    assert result.new_value == "⌨️ In Progress"


@patch(
    "foc_mechanical_rules.rules.pr_status.get_collaborator_permission",
    return_value="write",
)
@patch("foc_mechanical_rules.rules.pr_status.get_pr_review_context")
def test_commit_after_changes_requested_moves_to_awaiting_review(mock_ctx, mock_perm):
    mock_ctx.return_value = _pr(
        last_commit="2026-08-03T00:00:00Z",
        reviews=[_review("bob", "CHANGES_REQUESTED", "2026-08-02T00:00:00Z")],
    )

    result = PRStatusRule().apply_one(
        MagicMock(), ITEM, dry_run=False, mutation_log=None
    )

    assert result.status == "pending"
    assert result.new_value == "🔎 Awaiting review"


@patch(
    "foc_mechanical_rules.rules.pr_status.get_collaborator_permission",
    return_value="write",
)
@patch("foc_mechanical_rules.rules.pr_status.get_pr_review_context")
def test_re_requested_cr_reviewer_blocks_a_later_approval(mock_ctx, mock_perm):
    # filecoin-pin-website#154 shape: bob's CR is superseded by a commit and
    # carol's later approval, but bob has been re-requested -- his objection
    # stays blocking, so the approval never becomes authoritative and row 3
    # doesn't fire (falls through to the timestamp rows instead).
    mock_ctx.return_value = _pr(
        last_commit="2026-08-02T00:00:00Z",
        reviews=[
            _review("bob", "CHANGES_REQUESTED", "2026-08-01T00:00:00Z"),
            _review("carol", "APPROVED", "2026-08-03T00:00:00Z"),
        ],
        review_requests=[{"requestedReviewer": {"login": "bob"}}],
    )

    result = PRStatusRule().apply_one(
        MagicMock(), ITEM, dry_run=False, mutation_log=None
    )

    assert result.status == "pending"
    assert result.new_value != "✔️ Approved by reviewer"


@patch("foc_mechanical_rules.rules.pr_status.get_pr_review_context")
def test_no_feedback_moves_to_awaiting_review(mock_ctx):
    mock_ctx.return_value = _pr()

    result = PRStatusRule().apply_one(
        MagicMock(), ITEM, dry_run=False, mutation_log=None
    )

    assert result.status == "pending"
    assert result.new_value == "🔎 Awaiting review"


@patch("foc_mechanical_rules.rules.pr_status.get_pr_review_context")
def test_comments_after_last_commit_are_flagged_not_auto_routed(mock_ctx):
    mock_ctx.return_value = _pr(
        last_commit="2026-08-01T00:00:00Z",
        comments=[_comment("bob", "2026-08-02T00:00:00Z")],
    )

    result = PRStatusRule().apply_one(
        MagicMock(), ITEM, dry_run=False, mutation_log=None
    )

    assert result.status == "flagged"
    assert "comments" in result.reason


@patch("foc_mechanical_rules.rules.pr_status.get_pr_review_context")
def test_bot_comment_after_last_commit_is_ignored(mock_ctx):
    mock_ctx.return_value = _pr(
        last_commit="2026-08-01T00:00:00Z",
        comments=[
            _comment(
                "copilot-pull-request-reviewer", "2026-08-02T00:00:00Z", typename="Bot"
            )
        ],
    )

    result = PRStatusRule().apply_one(
        MagicMock(), ITEM, dry_run=False, mutation_log=None
    )

    assert result.status == "pending"
    assert result.new_value == "🔎 Awaiting review"


@patch("foc_mechanical_rules.rules.pr_status.get_pr_review_context")
def test_self_comment_after_last_commit_is_ignored(mock_ctx):
    mock_ctx.return_value = _pr(
        author="alice",
        last_commit="2026-08-01T00:00:00Z",
        comments=[_comment("alice", "2026-08-02T00:00:00Z")],
    )

    result = PRStatusRule().apply_one(
        MagicMock(), ITEM, dry_run=False, mutation_log=None
    )

    assert result.status == "pending"
    assert result.new_value == "🔎 Awaiting review"


@patch("foc_mechanical_rules.rules.pr_status.get_pr_review_context")
def test_trailing_comments_do_not_block_draft_routing(mock_ctx):
    # R-PR-005 has no comment carve-out -- a draft PR routes to In Progress
    # regardless of trailing comments.
    mock_ctx.return_value = _pr(
        is_draft=True,
        last_commit="2026-08-01T00:00:00Z",
        comments=[_comment("bob", "2026-08-02T00:00:00Z")],
    )

    result = PRStatusRule().apply_one(
        MagicMock(), ITEM, dry_run=False, mutation_log=None
    )

    assert result.status == "pending"
    assert result.new_value == "⌨️ In Progress"


@patch("foc_mechanical_rules.rules.pr_status.get_pr_review_context")
def test_dry_run_does_not_queue_a_mutation(mock_ctx):
    mock_ctx.return_value = _pr(is_draft=True)

    result = PRStatusRule().apply_one(
        MagicMock(), ITEM, dry_run=True, mutation_log=None
    )

    assert result.status == "applied"
    assert result.new_value == "⌨️ In Progress"


@patch("foc_mechanical_rules.rules.pr_status.get_pr_review_context")
def test_pr_not_found_is_an_error(mock_ctx):
    mock_ctx.return_value = {}

    result = PRStatusRule().apply_one(
        MagicMock(), ITEM, dry_run=False, mutation_log=None
    )

    assert result.status == "error"


@patch("foc_mechanical_rules.rules.pr_status.set_field_value_bulk")
def test_mutate_pending_batches_by_target_value(mock_bulk):
    mock_bulk.return_value = {
        "results": [
            {"item_ref": "PVTI_1", "success": True, "old_value": "📌 Triage"},
            {"item_ref": "PVTI_2", "success": True, "old_value": "📌 Triage"},
        ]
    }
    pending = [
        ActionResult(
            item_ref="FilOzone/dealbot#1",
            title="a",
            status="pending",
            old_value="📌 Triage",
            new_value="⌨️ In Progress",
            node_id="PVTI_1",
        ),
        ActionResult(
            item_ref="FilOzone/dealbot#2",
            title="b",
            status="pending",
            old_value="📌 Triage",
            new_value="⌨️ In Progress",
            node_id="PVTI_2",
        ),
    ]

    finalized = PRStatusRule().mutate_pending(MagicMock(), pending)

    assert len(finalized) == 2
    assert all(r.status == "applied" for r in finalized)
    mock_bulk.assert_called_once()
    assert mock_bulk.call_args.kwargs["field_name"] == "Status"
    assert mock_bulk.call_args.kwargs["item_refs"] == ["PVTI_1", "PVTI_2"]


def test_pr_status_rule_is_a_rule():
    assert isinstance(PRStatusRule(), Rule)
