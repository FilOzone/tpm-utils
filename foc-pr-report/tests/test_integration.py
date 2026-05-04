"""
Integration tests for foc-pr-report against the live GitHub API.

Verifies that the PR report pipeline (fetch → enrich → render) works
end-to-end after the migration to github_projects_client + pr_enrichment.

Requirements:
    - GITHUB_TOKEN env var (or `gh auth token` available)
    - Network access to api.github.com
    - Read access to FilOzone org project #14

Run:
    cd foc-pr-report
    GITHUB_TOKEN=$(gh auth token) uv run pytest tests/test_integration.py -v
"""

from __future__ import annotations

import os
import subprocess

import pytest
import requests

from foc_pr_report.pr_enrichment import (
    fetch_project_board_items_rest_filtered,
    field_values_by_name,
)
from foc_pr_report.report import BASE_FILTER, aggregate_rows, render_full_markdown

pytestmark = pytest.mark.integration


@pytest.fixture(scope="session")
def session() -> requests.Session:
    """Build a GitHub API session from env or gh CLI."""
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        try:
            token = subprocess.check_output(
                ["gh", "auth", "token"], text=True,
            ).strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            pytest.skip("No GITHUB_TOKEN and gh CLI unavailable")

    s = requests.Session()
    s.headers.update({
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    })
    return s


class TestPRReportPipeline:
    """End-to-end regression test for the PR report pipeline."""

    def test_fetch_and_render_produces_markdown(self, session: requests.Session):
        items = fetch_project_board_items_rest_filtered(
            session, filter_query=BASE_FILTER, verbose=False,
        )
        assert len(items) > 0, "Expected at least one PR on the board"

        # Verify items have the expected GraphQL-node shape
        first = items[0]
        assert "fieldValues" in first
        assert "content" in first

        # Verify field_values_by_name works on the fetched items
        pr_items = [it for it in items if (it.get("content") or {}).get("__typename") == "PullRequest"]
        assert len(pr_items) > 0
        fv = field_values_by_name(pr_items[0])
        assert "Status" in fv

        # Verify render pipeline doesn't crash
        rows = aggregate_rows(items)
        md = render_full_markdown(items, rows)
        assert isinstance(md, str)
        assert len(md) > 100
        assert "Status" in md or "|" in md  # Should contain a markdown table
