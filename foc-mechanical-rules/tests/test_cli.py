"""Unit tests for the --rule CLI flag — mocked GitHub API, no live calls."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from foc_mechanical_rules import cli


def _run_cli(argv, run_all_mock):
    with (
        patch.object(sys, "argv", ["foc-mechanical-rules", *argv]),
        patch("foc_mechanical_rules.cli.build_session"),
        patch("foc_mechanical_rules.cli.run_all", run_all_mock),
        patch("foc_mechanical_rules.cli.render_summary", return_value=""),
        patch("foc_mechanical_rules.cli.read_tsv", return_value=[]),
        patch("foc_mechanical_rules.cli.write_tsv"),
    ):
        cli.main()


def test_no_rule_flag_runs_every_registered_rule(capsys):
    run_all_mock = MagicMock(return_value=[])

    _run_cli(["--dry-run", "--token", "x"], run_all_mock)

    ran_ids = {rule.id for rule in run_all_mock.call_args.args[1]}
    assert ran_ids == {"R-PR-001", "R-FC-012", "R-FC-013"}


def test_rule_flag_filters_to_the_named_rule(capsys):
    run_all_mock = MagicMock(return_value=[])

    _run_cli(["--dry-run", "--token", "x", "--rule", "R-FC-013"], run_all_mock)

    ran_ids = {rule.id for rule in run_all_mock.call_args.args[1]}
    assert ran_ids == {"R-FC-013"}


def test_rule_flag_is_repeatable(capsys):
    run_all_mock = MagicMock(return_value=[])

    _run_cli(
        ["--dry-run", "--token", "x", "--rule", "R-FC-013", "--rule", "R-PR-001"],
        run_all_mock,
    )

    ran_ids = {rule.id for rule in run_all_mock.call_args.args[1]}
    assert ran_ids == {"R-FC-013", "R-PR-001"}


def test_unknown_rule_id_exits_without_running_anything(capsys):
    run_all_mock = MagicMock(return_value=[])

    with pytest.raises(SystemExit) as exc_info:
        _run_cli(["--dry-run", "--token", "x", "--rule", "R-NOPE"], run_all_mock)

    assert exc_info.value.code == 1
    run_all_mock.assert_not_called()
    assert "R-NOPE" in capsys.readouterr().err
