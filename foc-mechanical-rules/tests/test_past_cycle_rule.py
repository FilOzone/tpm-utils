"""Unit tests for R-FC-013 (past cycle) — mocked GitHub API, no live calls."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

from foc_mechanical_rules.mutation_log import MutationLog, MutationRecord
from foc_mechanical_rules.rule import ActionResult, Rule
from foc_mechanical_rules.rules.cycle import (
    PastCycleRule,
    get_current_and_past_cycle_titles,
)

ITEM = {
    "Repository": "FilOzone/dealbot",
    "Id": "458",
    "Title": "fix: something",
    "url": "https://github.com/FilOzone/dealbot/pull/458",
    "Cycle": "202607-2",
    "_node_id": "PVTI_abc123",
}

ITERATIONS = {
    "organization": {
        "projectV2": {
            "field": {
                "configuration": {
                    # GitHub's GraphQL schema splits current/future iterations
                    # from completed ones -- ``iterations`` alone never
                    # includes a truly past cycle. Mirror that split here so
                    # a regression back to reading only ``iterations`` fails
                    # this test instead of passing by accident.
                    "iterations": [
                        {
                            "title": "202608-2",
                            "startDate": "2026-08-17",
                            "duration": 14,
                        },
                        {
                            "title": "202608-3",
                            "startDate": "2026-08-31",
                            "duration": 14,
                        },
                    ],
                    "completedIterations": [
                        {
                            "title": "202608-1",
                            "startDate": "2026-08-03",
                            "duration": 14,
                        },
                        {
                            "title": "202607-2",
                            "startDate": "2026-07-20",
                            "duration": 14,
                        },
                    ],
                }
            }
        }
    }
}


def test_get_current_and_past_cycle_titles():
    session = MagicMock()
    with patch(
        "foc_mechanical_rules.rules.cycle.graphql_query", return_value=ITERATIONS
    ):
        current, past = get_current_and_past_cycle_titles(
            session, org="FilOzone", project_number=14, today=date(2026, 8, 20)
        )
    assert current == "202608-2"
    assert past == {"202607-2", "202608-1"}


@patch(
    "foc_mechanical_rules.rules.cycle.get_current_and_past_cycle_titles",
    return_value=("202608-2", {"202607-2", "202608-1"}),
)
def test_open_item_in_past_cycle_is_queued_pending(mock_get):
    # apply_one decides but doesn't mutate -- the actual write is batched by
    # mutate_pending (see test_cycle_rule.py's mutate_pending tests, which
    # cover the shared _CycleFieldRule logic both rules use).
    result = PastCycleRule().apply_one(
        MagicMock(), ITEM, dry_run=False, mutation_log=MutationLog()
    )

    assert result.status == "pending"
    assert result.old_value == "202607-2"
    assert result.new_value == "202608-2"
    assert result.node_id == "PVTI_abc123"


@patch(
    "foc_mechanical_rules.rules.cycle.get_current_and_past_cycle_titles",
    return_value=("202608-2", {"202607-2", "202608-1"}),
)
def test_draft_note_with_no_repository_is_skipped(mock_get):
    # A draft note (board item with no linked repo issue/PR) matches
    # `has:cycle` too but has no Repository/Id to build a mutable ref from.
    item = {**ITEM, "Repository": "", "Id": ""}

    result = PastCycleRule().apply_one(
        MagicMock(), item, dry_run=False, mutation_log=MutationLog()
    )

    assert result.status == "skipped"


@patch(
    "foc_mechanical_rules.rules.cycle.get_current_and_past_cycle_titles",
    return_value=("202608-2", {"202607-2", "202608-1"}),
)
def test_item_already_in_current_cycle_is_skipped(mock_get):
    item = {**ITEM, "Cycle": "202608-2"}

    result = PastCycleRule().apply_one(
        MagicMock(), item, dry_run=False, mutation_log=MutationLog()
    )

    assert result.status == "skipped"


@patch(
    "foc_mechanical_rules.rules.cycle.get_current_and_past_cycle_titles",
    return_value=("202608-2", {"202607-2", "202608-1"}),
)
def test_item_in_future_cycle_is_skipped(mock_get):
    item = {**ITEM, "Cycle": "202608-3"}

    result = PastCycleRule().apply_one(
        MagicMock(), item, dry_run=False, mutation_log=MutationLog()
    )

    assert result.status == "skipped"


@patch(
    "foc_mechanical_rules.rules.cycle.get_current_and_past_cycle_titles",
    return_value=("202608-2", {"202607-2", "202608-1"}),
)
def test_item_human_reverted_is_flagged_not_reset(mock_get):
    log = MutationLog(
        [
            MutationRecord(
                timestamp="2026-08-18T00:00:00+00:00",
                rule="R-FC-013",
                item="FilOzone/dealbot#458",
                field="cycle",
                old_value="202607-2",
                new_value="202608-2",
            )
        ]
    )

    result = PastCycleRule().apply_one(
        MagicMock(), ITEM, dry_run=False, mutation_log=log
    )

    assert result.status == "flagged"


@patch(
    "foc_mechanical_rules.rules.cycle.get_current_and_past_cycle_titles",
    return_value=("202608-2", {"202607-2", "202608-1"}),
)
def test_prior_history_for_a_different_cycle_does_not_block(mock_get):
    # We previously moved this item off a *different* past cycle; that's not
    # the reversion signal -- only a prior move off *this exact* cycle counts.
    log = MutationLog(
        [
            MutationRecord(
                timestamp="2026-07-01T00:00:00+00:00",
                rule="R-FC-013",
                item="FilOzone/dealbot#458",
                field="cycle",
                old_value="202606-2",
                new_value="202607-2",
            )
        ]
    )

    result = PastCycleRule().apply_one(
        MagicMock(), ITEM, dry_run=False, mutation_log=log
    )

    assert result.status == "pending"


@patch(
    "foc_mechanical_rules.rules.cycle.get_current_and_past_cycle_titles",
    return_value=(None, set()),
)
def test_no_active_cycle_is_an_error(mock_get):
    result = PastCycleRule().apply_one(
        MagicMock(), ITEM, dry_run=False, mutation_log=MutationLog()
    )
    assert result.status == "error"


@patch(
    "foc_mechanical_rules.rules.cycle.get_current_and_past_cycle_titles",
    return_value=("202608-2", {"202607-2", "202608-1"}),
)
def test_dry_run_does_not_queue_a_mutation(mock_get):
    result = PastCycleRule().apply_one(
        MagicMock(), ITEM, dry_run=True, mutation_log=MutationLog()
    )

    assert result.status == "applied"
    assert result.new_value == "202608-2"


@patch("foc_mechanical_rules.rules.cycle.set_field_value_bulk")
def test_mutate_pending_via_past_cycle_rule_batches_multiple_items(mock_bulk):
    # PastCycleRule uses the shared _CycleFieldRule.mutate_pending -- this
    # covers it through PastCycleRule specifically (test_cycle_rule.py covers
    # it through CycleRule). NOTE: this only exercises one rule's own pending
    # list; runner.run_all() calls each registered rule's run() (including
    # its own pending flush) to completion before moving to the next, so
    # R-FC-012's and R-FC-013's writes are never combined into one real batch
    # even though both rules share this method.
    mock_bulk.return_value = {
        "results": [
            {"item_ref": "PVTI_1", "success": True, "old_value": ""},
            {"item_ref": "PVTI_2", "success": True, "old_value": "202607-2"},
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
            old_value="202607-2",
            new_value="202608-2",
            node_id="PVTI_2",
        ),
    ]

    finalized = PastCycleRule().mutate_pending(MagicMock(), pending)

    assert len(finalized) == 2
    assert all(r.status == "applied" for r in finalized)
    mock_bulk.assert_called_once()
    assert mock_bulk.call_args.kwargs["item_refs"] == ["PVTI_1", "PVTI_2"]


def test_past_cycle_rule_is_a_rule():
    assert isinstance(PastCycleRule(), Rule)
