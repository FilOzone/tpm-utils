"""
Integration tests for the filozzy-mcp MCP layer against the live GitHub API.

These tests cover MCP-specific behavior (docstring validation, tool formatting).
Shared client tests live in ghprojects-client/tests/test_integration.py.

Requirements:
    - GITHUB_TOKEN env var (or `gh auth token` available)
    - Network access to api.github.com
    - Read access to FilOzone org project #14

Run:
    cd filozzy-mcp
    GITHUB_TOKEN=$(gh auth token) uv run pytest tests/test_integration.py -v
"""

from __future__ import annotations

import os
import re
import subprocess

import pytest
import requests

pytestmark = pytest.mark.integration

from ghprojects_client import list_items
from filozzy_mcp.server import list_board_items, GITHUB_ORG, GITHUB_PROJECT_NUMBER


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


# ---------------------------------------------------------------------------
# MCP tool docstring validation
# ---------------------------------------------------------------------------


class TestListBoardItemsDocstringExamples:
    """Validate list_board_items docstring query examples against live API."""

    @staticmethod
    def _parse_docstring_query_examples() -> tuple[list[str], list[str]]:
        doc = list_board_items.__doc__
        assert doc is not None

        runnable_queries: list[str] = []
        skipped_queries: list[str] = []
        for line in doc.splitlines():
            match = re.match(r'^\s{2,}(.+?)\s+—\s+.+$', line)
            if not match:
                continue
            query = match.group(1).strip()
            if not query:
                continue

            should_skip = False
            if query.startswith("\"search text\""):
                should_skip = True
            if query == "blocking:FilOzone/dealbot#470":
                should_skip = True
            if re.match(r'^[a-zA-Z0-9_:"@#.,><\-/\s]+$', query):
                if should_skip:
                    skipped_queries.append(query)
                else:
                    runnable_queries.append(query)

        seen = set()
        runnable_ordered: list[str] = []
        for q in runnable_queries:
            if q in seen:
                continue
            seen.add(q)
            runnable_ordered.append(q)

        seen.clear()
        skipped_ordered: list[str] = []
        for q in skipped_queries:
            if q in seen:
                continue
            seen.add(q)
            skipped_ordered.append(q)

        return runnable_ordered, skipped_ordered

    def test_docstring_examples_return_non_empty(self, session: requests.Session):
        examples, _skipped = self._parse_docstring_query_examples()
        assert len(examples) > 0, "No query examples parsed from list_board_items docstring"
        print(f"Extracted {len(examples)} docstring query examples:")
        for idx, query in enumerate(examples, start=1):
            print(f"  {idx:02d}. {query}")

        empty_results: list[str] = []
        for query in examples:
            result = list_items(
                session, org=GITHUB_ORG, project_number=GITHUB_PROJECT_NUMBER,
                query=query, per_page=1,
            )
            if len(result["items"]) == 0:
                empty_results.append(query)

        assert not empty_results, (
            "These docstring query examples returned no items:\n"
            + "\n".join(f"- {q}" for q in empty_results)
        )

    def test_docstring_skipped_examples_are_syntactically_accepted(self, session: requests.Session):
        _examples, skipped = self._parse_docstring_query_examples()
        assert len(skipped) > 0, "No skipped query examples parsed from list_board_items docstring"
        print(f"Skipped {len(skipped)} docstring query examples (syntax-only validation):")
        for idx, query in enumerate(skipped, start=1):
            print(f"  {idx:02d}. {query}")

        for query in skipped:
            result = list_items(
                session, org=GITHUB_ORG, project_number=GITHUB_PROJECT_NUMBER,
                query=query, per_page=1,
            )
            assert "items" in result
            assert "has_more" in result
