"""Unit tests for stopping a run once GitHub rate-limits it -- no live calls.

GitHub warns that continuing to send requests while rate limited may get
the integration banned, so after the first throttled response the session
sends nothing more and the rest of the run is reported as deferred.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest
import requests
from github_projects_client import GitHubRateLimitError

from foc_mechanical_rules import cli
from foc_mechanical_rules.github_api import (
    GITHUB_API_PREFIX,
    build_session,
    rate_limit_tripped,
)
from foc_mechanical_rules.mutation_log import MutationLog
from foc_mechanical_rules.rule import ActionResult, Rule
from foc_mechanical_rules.runner import render_summary, run_all


def _response(status: int, body: Dict[str, Any], headers=None) -> requests.Response:
    resp = requests.Response()
    resp.status_code = status
    resp.reason = "test"
    resp._content = json.dumps(body).encode()
    resp.headers.update(headers or {})
    resp.url = "https://api.github.com/graphql"
    return resp


def _trip(session: requests.Session) -> None:
    session.get_adapter(GITHUB_API_PREFIX).tripped_by = "403 on POST graphql"


class TestRateLimitBreaker:
    def test_rate_limited_response_blocks_every_later_request(self):
        session = build_session("token")
        responses = [
            _response(403, {"message": "You have exceeded a secondary rate limit"}),
            _response(200, {"data": {}}),
        ]
        with patch("requests.adapters.HTTPAdapter.send", side_effect=responses) as sent:
            first = session.post("https://api.github.com/graphql", json={})
            assert first.status_code == 403
            assert rate_limit_tripped(session)

            with pytest.raises(GitHubRateLimitError, match="not sent"):
                session.get("https://api.github.com/repos/o/r/pulls/1")

        assert sent.call_count == 1

    def test_graphql_200_rate_limited_trips_the_breaker(self):
        session = build_session("token")
        throttled = _response(
            200, {"errors": [{"type": "RATE_LIMITED", "message": "API rate limit"}]}
        )
        with patch("requests.adapters.HTTPAdapter.send", return_value=throttled):
            session.post("https://api.github.com/graphql", json={})
        assert rate_limit_tripped(session)

    def test_permissions_403_does_not_trip_the_breaker(self):
        session = build_session("token")
        forbidden = _response(403, {"message": "Resource not accessible"})
        with patch("requests.adapters.HTTPAdapter.send", return_value=forbidden):
            session.post("https://api.github.com/graphql", json={})
        assert not rate_limit_tripped(session)


class _FakeRule(Rule):
    """Applies items in order; can trip the breaker on a given item."""

    field_name = "status"
    doc_url = "https://example.invalid/rule"

    def __init__(self, rule_id="R-TEST-1", n_items=3, trip_on=None, pending=False):
        self.id = rule_id
        self.n_items = n_items
        self.trip_on = trip_on
        self.pending = pending
        self.applied: List[str] = []
        self.select_called = False
        self.mutate_pending_called = False

    def select(self, session):
        self.select_called = True
        return [
            {"Repository": "o/r", "Id": str(n), "Title": f"t{n}"}
            for n in range(1, self.n_items + 1)
        ]

    def apply_one(self, session, item, *, dry_run, mutation_log):
        ref = f"o/r#{item['Id']}"
        self.applied.append(ref)
        if item["Id"] == self.trip_on:
            _trip(session)
            return ActionResult(ref, item["Title"], "error", reason="403 throttled")
        status = "pending" if self.pending else "applied"
        return ActionResult(ref, item["Title"], status, node_id=f"PVTI_{item['Id']}")

    def mutate_pending(self, session, pending):
        self.mutate_pending_called = True
        return [ActionResult(p.item_ref, p.title, "applied") for p in pending]


class TestRunStopsAfterRateLimit:
    def test_item_that_tripped_and_later_items_are_deferred_without_calls(self):
        session = build_session("token")
        rule = _FakeRule(n_items=4, trip_on="2")

        run = rule.run(session, dry_run=False, mutation_log=MutationLog())

        assert [r.status for r in run.results] == [
            "applied",
            "deferred",
            "deferred",
            "deferred",
        ]
        assert rule.applied == ["o/r#1", "o/r#2"]  # items 3-4 never evaluated
        assert run.results[3].item_ref == "o/r#4"

    def test_pending_flush_is_skipped_once_tripped(self):
        session = build_session("token")
        rule = _FakeRule(n_items=3, trip_on="3", pending=True)

        run = rule.run(session, dry_run=False, mutation_log=MutationLog())

        assert not rule.mutate_pending_called
        assert sorted(r.status for r in run.results) == ["deferred"] * 3

    def test_later_rules_are_not_run_and_the_run_does_not_fail(self):
        session = build_session("token")
        first = _FakeRule("R-TEST-1", trip_on="1")
        second = _FakeRule("R-TEST-2")

        runs = run_all(
            session, [first, second], dry_run=False, mutation_log=MutationLog()
        )

        assert not second.select_called
        assert runs[1].not_run_reason
        assert not any(r.status == "error" for run in runs for r in run.results)
        assert "R-TEST-2 (status) — not run" in render_summary([first, second], runs)


def test_mutation_log_is_saved_even_if_the_run_crashes():
    write_tsv = MagicMock()
    with (
        patch.object(sys, "argv", ["foc-mechanical-rules", "--token", "x"]),
        patch("foc_mechanical_rules.cli.build_session"),
        patch("foc_mechanical_rules.cli.run_all", side_effect=RuntimeError("boom")),
        patch("foc_mechanical_rules.cli.read_tsv", return_value=[]),
        patch("foc_mechanical_rules.cli.write_tsv", write_tsv),
    ):
        with pytest.raises(RuntimeError):
            cli.main()

    write_tsv.assert_called_once()
