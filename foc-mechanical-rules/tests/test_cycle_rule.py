"""Unit tests for R-FC-012 (cycle) — mocked GitHub API, no live calls."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

from foc_mechanical_rules.rule import Rule
from foc_mechanical_rules.rules.cycle import CycleRule, get_current_cycle_title
from foc_mechanical_rules.state import MutationRecord

ITEM = {
    "Repository": "FilOzone/dealbot",
    "Id": "458",
    "Title": "fix: something",
    "url": "https://github.com/FilOzone/dealbot/pull/458",
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


@patch("foc_mechanical_rules.rules.cycle.load_mutations", return_value=[])
@patch("foc_mechanical_rules.rules.cycle.set_field_value")
@patch(
    "foc_mechanical_rules.rules.cycle.get_current_cycle_title", return_value="202608-2"
)
def test_item_without_prior_history_gets_current_cycle(
    mock_get_cycle, mock_set, mock_load
):
    mock_set.return_value = {"success": True, "old_value": ""}

    result = CycleRule().apply_one(MagicMock(), ITEM, dry_run=False)

    assert result.status == "applied"
    assert result.new_value == "202608-2"
    mock_set.assert_called_once()


@patch("foc_mechanical_rules.rules.cycle.set_field_value")
@patch(
    "foc_mechanical_rules.rules.cycle.get_current_cycle_title", return_value="202608-2"
)
def test_item_previously_cleared_by_us_is_flagged_not_reset(mock_get_cycle, mock_set):
    prior = [
        MutationRecord(
            timestamp="2026-08-18T00:00:00+00:00",
            rule="R-FC-012",
            item="FilOzone/dealbot#458",
            field="cycle",
            old_value="",
            new_value="202608-2",
        )
    ]
    with patch("foc_mechanical_rules.rules.cycle.load_mutations", return_value=prior):
        result = CycleRule().apply_one(MagicMock(), ITEM, dry_run=False)

    assert result.status == "flagged"
    mock_set.assert_not_called()


@patch("foc_mechanical_rules.rules.cycle.load_mutations", return_value=[])
@patch("foc_mechanical_rules.rules.cycle.set_field_value")
@patch(
    "foc_mechanical_rules.rules.cycle.get_current_cycle_title", return_value="202608-2"
)
def test_prior_history_for_a_different_cycle_does_not_block(
    mock_get_cycle, mock_set, mock_load
):
    # We set it to an earlier cycle before; that's not the removal signal —
    # only a prior mutation to the *current* cycle counts.
    mock_load.return_value = [
        MutationRecord(
            timestamp="2026-07-01T00:00:00+00:00",
            rule="R-FC-012",
            item="FilOzone/dealbot#458",
            field="cycle",
            old_value="",
            new_value="202607-2",
        )
    ]
    mock_set.return_value = {"success": True, "old_value": ""}

    result = CycleRule().apply_one(MagicMock(), ITEM, dry_run=False)

    assert result.status == "applied"


@patch("foc_mechanical_rules.rules.cycle.get_current_cycle_title", return_value=None)
def test_no_active_cycle_is_an_error(mock_get_cycle):
    result = CycleRule().apply_one(MagicMock(), ITEM, dry_run=False)
    assert result.status == "error"


@patch("foc_mechanical_rules.rules.cycle.load_mutations", return_value=[])
@patch("foc_mechanical_rules.rules.cycle.set_field_value")
@patch(
    "foc_mechanical_rules.rules.cycle.get_current_cycle_title", return_value="202608-2"
)
def test_dry_run_does_not_mutate(mock_get_cycle, mock_set, mock_load):
    result = CycleRule().apply_one(MagicMock(), ITEM, dry_run=True)

    assert result.status == "applied"
    assert result.new_value == "202608-2"
    mock_set.assert_not_called()


def test_cycle_rule_is_a_rule():
    assert isinstance(CycleRule(), Rule)
