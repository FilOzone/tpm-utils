"""
Integration tests for filozzy-mcp against the live GitHub API.

Requirements:
    - GITHUB_TOKEN env var (or `gh auth token` available)
    - Network access to api.github.com
    - Read access to FilOzone org project #14

Run:
    cd filozzy-mcp
    uv run pytest tests/test_integration.py -v

These tests are read-only — no mutations are performed.
"""

from __future__ import annotations

import os
import subprocess

import pytest
import requests

from foc_pr_report.foc_project14_client import (
    FILOZ_ORG,
    PROJECT_NUMBER,
    fetch_project_v2_items_rest,
    list_project_v2_field_ids_by_name,
)
from filozzy_mcp.read_tools import (
    get_item_details,
    list_field_options,
    list_fields,
    list_project_items,
)


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
# foc_project14_client: fetch_project_v2_items_rest
# ---------------------------------------------------------------------------


class TestFetchProjectV2ItemsRest:
    """Tests for the shared REST item fetcher."""

    def test_returns_dict_with_expected_keys(self, session: requests.Session):
        result = fetch_project_v2_items_rest(
            session,
            org=FILOZ_ORG,
            project_number=PROJECT_NUMBER,
            query="is:issue",
            max_pages=1,
            per_page=5,
            verbose=False,
        )
        assert isinstance(result, dict)
        assert "items" in result
        assert "next_cursor" in result
        assert "pages_fetched" in result
        assert "has_more" in result

    def test_max_pages_caps_fetch(self, session: requests.Session):
        result = fetch_project_v2_items_rest(
            session,
            org=FILOZ_ORG,
            project_number=PROJECT_NUMBER,
            query="is:issue",
            max_pages=1,
            per_page=5,
            verbose=False,
        )
        assert result["pages_fetched"] == 1
        assert len(result["items"]) <= 5

    def test_cursor_resumes_pagination(self, session: requests.Session):
        # Page 1
        r1 = fetch_project_v2_items_rest(
            session,
            org=FILOZ_ORG,
            project_number=PROJECT_NUMBER,
            query="is:pr",
            max_pages=1,
            per_page=3,
            verbose=False,
        )
        assert r1["has_more"] is True
        assert r1["next_cursor"] is not None

        # Page 2 via cursor
        r2 = fetch_project_v2_items_rest(
            session,
            org=FILOZ_ORG,
            project_number=PROJECT_NUMBER,
            query="is:pr",  # ignored when cursor is set
            max_pages=1,
            per_page=3,
            cursor=r1["next_cursor"],
            verbose=False,
        )
        assert len(r2["items"]) > 0

        # No overlap between pages
        ids1 = {item.get("node_id") for item in r1["items"]}
        ids2 = {item.get("node_id") for item in r2["items"]}
        assert ids1.isdisjoint(ids2), "Pages should not have overlapping items"

    def test_invalid_filter_returns_empty(self, session: requests.Session):
        result = fetch_project_v2_items_rest(
            session,
            org=FILOZ_ORG,
            project_number=PROJECT_NUMBER,
            query="xyzzy_bogus_filter:nonsense",
            max_pages=1,
            verbose=False,
        )
        assert result["items"] == []
        assert result["has_more"] is False

    def test_no_max_pages_fetches_all(self, session: requests.Session):
        """Without max_pages, should exhaust all pages (use a narrow query)."""
        result = fetch_project_v2_items_rest(
            session,
            org=FILOZ_ORG,
            project_number=PROJECT_NUMBER,
            query='"cycle-theme":"Contract Upgrade" -last-updated:1days',
            verbose=False,
        )
        # Should have fetched everything (no cursor left)
        assert result["has_more"] is False
        assert result["next_cursor"] is None


# ---------------------------------------------------------------------------
# read_tools: list_project_items
# ---------------------------------------------------------------------------


class TestListProjectItems:
    """Tests for the MCP-facing list_project_items function."""

    def test_returns_expected_shape(self, session: requests.Session):
        result = list_project_items(
            session, query="is:issue", per_page=5,
        )
        assert "items" in result
        assert "next_cursor" in result
        assert "has_more" in result
        assert "debug" in result

    def test_items_have_default_fields(self, session: requests.Session):
        result = list_project_items(
            session, query="is:pr", per_page=3,
        )
        assert len(result["items"]) > 0
        item = result["items"][0]
        # Default fields should be present (may be empty string)
        for field in ["Repository", "Id", "Title", "Status", "_node_id"]:
            assert field in item, f"Missing field: {field}"

    def test_custom_fields(self, session: requests.Session):
        result = list_project_items(
            session,
            query="is:pr",
            fields=["Repository", "Id", "Title"],
            per_page=3,
        )
        item = result["items"][0]
        assert "Repository" in item
        assert "Id" in item
        assert "Title" in item
        # Fields not requested should not be present (except _node_id)
        assert "Cycle Theme" not in item

    def test_cursor_pagination(self, session: requests.Session):
        r1 = list_project_items(
            session, query="is:pr", per_page=3,
        )
        assert r1["has_more"] is True

        r2 = list_project_items(
            session, query="is:pr", per_page=3, cursor=r1["next_cursor"],
        )
        assert len(r2["items"]) > 0

        # No overlap
        ids1 = {(it["Repository"], it["Id"]) for it in r1["items"]}
        ids2 = {(it["Repository"], it["Id"]) for it in r2["items"]}
        assert ids1.isdisjoint(ids2)

    def test_debug_info(self, session: requests.Session):
        result = list_project_items(
            session, query="is:issue", per_page=5,
        )
        debug = result["debug"]
        assert debug["rest_query"] == "is:issue"
        assert "rest_endpoint" in debug
        assert "rest_field_ids" in debug
        assert isinstance(debug["items_returned"], int)

    def test_time_based_filter(self, session: requests.Session):
        """Verify last-updated filter works through the full stack."""
        result = list_project_items(
            session, query="-last-updated:1days", per_page=50,
        )
        # Should return some recently updated items
        assert len(result["items"]) > 0

    def test_combined_filters(self, session: requests.Session):
        """Verify combining custom field + time-based filter."""
        result = list_project_items(
            session,
            query='"cycle-theme":"Contract Upgrade" -last-updated:1days',
            per_page=50,
        )
        # Should match the known item from the board
        assert len(result["items"]) >= 1
        titles = [it["Title"] for it in result["items"]]
        assert any("FWSS" in t or "Mainnet Upgrade" in t for t in titles)


# ---------------------------------------------------------------------------
# read_tools: list_fields
# ---------------------------------------------------------------------------


class TestListFields:
    """Tests for field discovery."""

    def test_returns_field_map(self, session: requests.Session):
        fields = list_fields(session)
        assert isinstance(fields, dict)
        assert len(fields) > 0
        # Known fields that should exist
        assert "Status" in fields
        assert isinstance(fields["Status"], int)

    def test_known_fields_present(self, session: requests.Session):
        fields = list_fields(session)
        expected = ["Status", "Milestone", "Cycle Theme"]
        for name in expected:
            assert name in fields, f"Expected field '{name}' not found"


# ---------------------------------------------------------------------------
# read_tools: list_field_options
# ---------------------------------------------------------------------------


class TestListFieldOptions:
    """Tests for field option discovery."""

    def test_status_field_options(self, session: requests.Session):
        result = list_field_options(session, field_name="Status")
        assert "project_id" in result
        assert "fields" in result
        assert "Status" in result["fields"]

        status = result["fields"]["Status"]
        assert status["type"] == "single_select"
        assert len(status["options"]) > 0
        option_names = [opt["name"] for opt in status["options"]]
        # At least some known statuses should be present
        assert any("Done" in name for name in option_names)

    def test_iteration_field(self, session: requests.Session):
        result = list_field_options(session, field_name="Cycle")
        if "Cycle" not in result["fields"]:
            pytest.skip("Cycle field not found on project")
        cycle = result["fields"]["Cycle"]
        assert cycle["type"] == "iteration"
        assert "iterations" in cycle
        assert "completed_iterations" in cycle

    def test_nonexistent_field(self, session: requests.Session):
        result = list_field_options(session, field_name="NonexistentField12345")
        assert result["fields"] == {}

    def test_all_fields_when_no_name(self, session: requests.Session):
        result = list_field_options(session)
        assert len(result["fields"]) > 3  # Should have many fields


# ---------------------------------------------------------------------------
# read_tools: get_item_details
# ---------------------------------------------------------------------------


class TestGetItemDetails:
    def _find_known_item(self, session: requests.Session) -> dict:
        """Find a known item on the board to test against."""
        result = list_project_items(
            session, query="is:pr", per_page=1,
        )
        assert len(result["items"]) > 0
        return result["items"][0]

    def test_lookup_by_short_ref(self, session: requests.Session):
        known = self._find_known_item(session)
        repo_full = known["Repository"]  # e.g. "FilOzone/dealbot"
        number = known["Id"]
        repo_name = repo_full.split("/", 1)[1] if "/" in repo_full else repo_full

        details = get_item_details(session, item_ref=f"{repo_name}#{number}")
        assert details is not None
        assert details["Id"] == number
        assert "Status" in details

    def test_lookup_by_full_ref(self, session: requests.Session):
        known = self._find_known_item(session)
        repo_full = known["Repository"]
        number = known["Id"]

        details = get_item_details(session, item_ref=f"{repo_full}#{number}")
        assert details is not None
        assert details["Id"] == number

    def test_lookup_by_url(self, session: requests.Session):
        known = self._find_known_item(session)
        url = known.get("url", "")
        if not url:
            pytest.skip("No URL on known item")

        details = get_item_details(session, item_ref=url)
        assert details is not None
        assert details["Id"] == known["Id"]

    def test_nonexistent_item(self, session: requests.Session):
        details = get_item_details(
            session, item_ref="nonexistent-repo-xyz#99999",
        )
        assert details is None

    def test_invalid_ref_format(self, session: requests.Session):
        details = get_item_details(session, item_ref="not-a-valid-ref")
        assert details is None


# ---------------------------------------------------------------------------
# foc_project14_client: list_project_v2_field_ids_by_name
# ---------------------------------------------------------------------------


class TestListFieldIdsByName:
    def test_returns_field_map(self, session: requests.Session):
        fields = list_project_v2_field_ids_by_name(
            session, org=FILOZ_ORG, project_number=PROJECT_NUMBER,
        )
        assert isinstance(fields, dict)
        assert "Status" in fields
        assert isinstance(fields["Status"], int)
