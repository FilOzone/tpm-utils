"""Unit tests for R-FC-012 (cycle) — mocked GitHub API, no live calls."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

from foc_mechanical_rules.mutation_log import MutationLog, MutationRecord
from foc_mechanical_rules.rule import ActionResult, Rule
from foc_mechanical_rules.rules.cycle import (
    CycleRule,
    DoneCycleRule,
    get_current_cycle_title,
)

ITEM = {
    "Repository": "FilOzone/dealbot",
    "Id": "458",
    "Title": "fix: something",
    "url": "https://github.com/FilOzone/dealbot/pull/458",
    "_node_id": "PVTI_abc123",
}

ITERATIONS = {
    "organization": {
        "projectV2": {
            "field": {
                "configuration": {
                    "iterations": [
                        {
                            "title": "202608-1",
                            "startDate": "2026-08-03",
                            "duration": 14,
                        },
                        {
                            "title": "202608-2",
                            "startDate": "2026-08-17",
                            "duration": 14,
                        },
                    ]
                }
            }
        }
    }
}


def test_get_current_cycle_title_picks_iteration_containing_today():
    session = MagicMock()
    with patch(
        "foc_mechanical_rules.rules.cycle.graphql_query", return_value=ITERATIONS
    ):
        title = get_current_cycle_title(
            session, org="FilOzone", project_number=14, today=date(2026, 8, 20)
        )
    assert title == "202608-2"


def test_get_current_cycle_title_returns_none_for_gap():
    session = MagicMock()
    with patch(
        "foc_mechanical_rules.rules.cycle.graphql_query", return_value=ITERATIONS
    ):
        title = get_current_cycle_title(
            session, org="FilOzone", project_number=14, today=date(2026, 9, 1)
        )
    assert title is None


@patch(
    "foc_mechanical_rules.rules.cycle.get_current_cycle_title", return_value="202608-2"
)
def test_item_without_prior_history_is_queued_pending(mock_get_cycle):
    # apply_one decides but doesn't mutate -- the actual write is batched by
    # mutate_pending (see test_mutate_pending below), so a real candidate for
    # a real move comes back "pending", not "applied".
    result = CycleRule().apply_one(
        MagicMock(), ITEM, dry_run=False, mutation_log=MutationLog()
    )

    assert result.status == "pending"
    assert result.new_value == "202608-2"
    assert result.node_id == "PVTI_abc123"


@patch(
    "foc_mechanical_rules.rules.cycle.get_current_cycle_title", return_value="202608-2"
)
def test_item_previously_cleared_by_us_is_flagged_not_reset(mock_get_cycle):
    log = MutationLog(
        [
            MutationRecord(
                timestamp="2026-08-18T00:00:00+00:00",
                rule="R-FC-012",
                item="FilOzone/dealbot#458",
                field="cycle",
                old_value="",
                new_value="202608-2",
            )
        ]
    )

    result = CycleRule().apply_one(MagicMock(), ITEM, dry_run=False, mutation_log=log)

    assert result.status == "flagged"


@patch(
    "foc_mechanical_rules.rules.cycle.get_current_cycle_title", return_value="202608-2"
)
def test_prior_history_for_a_different_cycle_does_not_block(mock_get_cycle):
    # We set it to an earlier cycle before; that's not the removal signal —
    # only a prior mutation to the *current* cycle counts.
    log = MutationLog(
        [
            MutationRecord(
                timestamp="2026-07-01T00:00:00+00:00",
                rule="R-FC-012",
                item="FilOzone/dealbot#458",
                field="cycle",
                old_value="",
                new_value="202607-2",
            )
        ]
    )

    result = CycleRule().apply_one(MagicMock(), ITEM, dry_run=False, mutation_log=log)

    assert result.status == "pending"


@patch("foc_mechanical_rules.rules.cycle.get_current_cycle_title", return_value=None)
def test_no_active_cycle_is_an_error(mock_get_cycle):
    result = CycleRule().apply_one(
        MagicMock(), ITEM, dry_run=False, mutation_log=MutationLog()
    )
    assert result.status == "error"


@patch(
    "foc_mechanical_rules.rules.cycle.get_current_cycle_title", return_value="202608-2"
)
def test_dry_run_does_not_queue_a_mutation(mock_get_cycle):
    result = CycleRule().apply_one(
        MagicMock(), ITEM, dry_run=True, mutation_log=MutationLog()
    )

    assert result.status == "applied"
    assert result.new_value == "202608-2"


@patch("foc_mechanical_rules.rules.cycle.set_field_value_bulk")
def test_mutate_pending_batches_same_value_items_in_one_call(mock_bulk):
    mock_bulk.return_value = {
        "results": [
            {"item_ref": "PVTI_1", "success": True, "old_value": ""},
            {"item_ref": "PVTI_2", "success": True, "old_value": ""},
        ]
    }
    pending = [
        ActionResult(
            item_ref="FilOzone/dealbot#1",
            title="a",
            status="pending",
            new_value="202608-2",
            node_id="PVTI_1",
        ),
        ActionResult(
            item_ref="FilOzone/dealbot#2",
            title="b",
            status="pending",
            new_value="202608-2",
            node_id="PVTI_2",
        ),
    ]

    finalized = CycleRule().mutate_pending(MagicMock(), pending)

    assert len(finalized) == 2
    assert all(r.status == "applied" for r in finalized)
    # One GraphQL call for both items, not one per item.
    mock_bulk.assert_called_once()
    assert mock_bulk.call_args.kwargs["item_refs"] == ["PVTI_1", "PVTI_2"]
    assert mock_bulk.call_args.kwargs["value"] == "202608-2"


@patch("foc_mechanical_rules.rules.cycle.set_field_value_bulk")
def test_mutate_pending_reports_per_item_failure(mock_bulk):
    mock_bulk.return_value = {
        "results": [{"item_ref": "PVTI_1", "success": False, "error": "boom"}]
    }
    pending = [
        ActionResult(
            item_ref="FilOzone/dealbot#1",
            title="a",
            status="pending",
            new_value="202608-2",
            node_id="PVTI_1",
        )
    ]

    finalized = CycleRule().mutate_pending(MagicMock(), pending)

    assert len(finalized) == 1
    assert finalized[0].status == "error"
    assert "boom" in finalized[0].reason


def test_cycle_rule_is_a_rule():
    assert isinstance(CycleRule(), Rule)


@patch("foc_mechanical_rules.rules.cycle.list_items")
def test_done_cycle_rule_queries_done_items_with_the_same_window_as_cycle_rule(
    mock_list_items,
):
    mock_list_items.return_value = {"items": [], "has_more": False, "next_cursor": None}

    DoneCycleRule().select(MagicMock())

    query = mock_list_items.call_args.kwargs["query"]
    assert 'status:"🎉 Done"' in query
    assert '-status:"🎉 Done"' not in query
    assert "no:cycle" in query
    assert "updated:>@today-3d" in query


@patch(
    "foc_mechanical_rules.rules.cycle.get_current_cycle_title", return_value="202608-2"
)
def test_done_cycle_rule_reuses_cycle_rules_apply_one(mock_get_cycle):
    # DoneCycleRule only overrides select() -- apply_one's behavior (queue a
    # pending mutation for a candidate with no prior history) should match
    # CycleRule's exactly.
    rule = DoneCycleRule()
    result = rule.apply_one(
        MagicMock(), ITEM, dry_run=False, mutation_log=MutationLog()
    )

    assert result.status == "pending"
    assert result.new_value == "202608-2"
    assert rule.id == "R-FC-014"


def test_done_cycle_rule_is_a_rule():
    assert isinstance(DoneCycleRule(), Rule)
