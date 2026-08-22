"""Unit tests for R-FC-013 (past cycle) — mocked GitHub API, no live calls."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

from foc_mechanical_rules.mutation_log import MutationLog, MutationRecord
from foc_mechanical_rules.rule import Rule
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


@patch("foc_mechanical_rules.rules.cycle.set_field_value")
@patch(
    "foc_mechanical_rules.rules.cycle.get_current_and_past_cycle_titles",
    return_value=("202608-2", {"202607-2", "202608-1"}),
)
def test_open_item_in_past_cycle_moves_to_current(mock_get, mock_set):
    mock_set.return_value = {"success": True, "old_value": "202607-2"}

    result = PastCycleRule().apply_one(
        MagicMock(), ITEM, dry_run=False, mutation_log=MutationLog()
    )

    assert result.status == "applied"
    assert result.old_value == "202607-2"
    assert result.new_value == "202608-2"
    mock_set.assert_called_once()


@patch("foc_mechanical_rules.rules.cycle.set_field_value")
@patch(
    "foc_mechanical_rules.rules.cycle.get_current_and_past_cycle_titles",
    return_value=("202608-2", {"202607-2", "202608-1"}),
)
def test_item_already_in_current_cycle_is_skipped(mock_get, mock_set):
    item = {**ITEM, "Cycle": "202608-2"}

    result = PastCycleRule().apply_one(
        MagicMock(), item, dry_run=False, mutation_log=MutationLog()
    )

    assert result.status == "skipped"
    mock_set.assert_not_called()


@patch("foc_mechanical_rules.rules.cycle.set_field_value")
@patch(
    "foc_mechanical_rules.rules.cycle.get_current_and_past_cycle_titles",
    return_value=("202608-2", {"202607-2", "202608-1"}),
)
def test_item_in_future_cycle_is_skipped(mock_get, mock_set):
    item = {**ITEM, "Cycle": "202608-3"}

    result = PastCycleRule().apply_one(
        MagicMock(), item, dry_run=False, mutation_log=MutationLog()
    )

    assert result.status == "skipped"
    mock_set.assert_not_called()


@patch("foc_mechanical_rules.rules.cycle.set_field_value")
@patch(
    "foc_mechanical_rules.rules.cycle.get_current_and_past_cycle_titles",
    return_value=("202608-2", {"202607-2", "202608-1"}),
)
def test_item_human_reverted_is_flagged_not_reset(mock_get, mock_set):
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
    mock_set.assert_not_called()


@patch("foc_mechanical_rules.rules.cycle.set_field_value")
@patch(
    "foc_mechanical_rules.rules.cycle.get_current_and_past_cycle_titles",
    return_value=("202608-2", {"202607-2", "202608-1"}),
)
def test_prior_history_for_a_different_cycle_does_not_block(mock_get, mock_set):
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
    mock_set.return_value = {"success": True, "old_value": "202607-2"}

    result = PastCycleRule().apply_one(
        MagicMock(), ITEM, dry_run=False, mutation_log=log
    )

    assert result.status == "applied"


@patch(
    "foc_mechanical_rules.rules.cycle.get_current_and_past_cycle_titles",
    return_value=(None, set()),
)
def test_no_active_cycle_is_an_error(mock_get):
    result = PastCycleRule().apply_one(
        MagicMock(), ITEM, dry_run=False, mutation_log=MutationLog()
    )
    assert result.status == "error"


@patch("foc_mechanical_rules.rules.cycle.set_field_value")
@patch(
    "foc_mechanical_rules.rules.cycle.get_current_and_past_cycle_titles",
    return_value=("202608-2", {"202607-2", "202608-1"}),
)
def test_dry_run_does_not_mutate(mock_get, mock_set):
    result = PastCycleRule().apply_one(
        MagicMock(), ITEM, dry_run=True, mutation_log=MutationLog()
    )

    assert result.status == "applied"
    assert result.new_value == "202608-2"
    mock_set.assert_not_called()


def test_past_cycle_rule_is_a_rule():
    assert isinstance(PastCycleRule(), Rule)
