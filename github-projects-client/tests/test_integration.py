"""
Integration tests for github-projects-client against the live GitHub API.

Requirements:
    - GITHUB_TOKEN env var (or `gh auth token` available)
    - Network access to api.github.com
    - Read access to FilOzone org project #14

Run:
    cd github-projects-client
    GITHUB_TOKEN=$(gh auth token) uv run pytest tests/test_integration.py -v

These tests are read-only — no mutations are performed.
"""

from __future__ import annotations

import json
import os
import subprocess
from urllib.parse import parse_qs, urlparse

import pytest
import requests

from github_projects_client import (
    fetch_items_rest,
    get_item,
    list_field_ids_by_name,
    list_field_options,
    list_items,
    list_fields,
    resolve_view_url,
)

# Mark all tests in this module as integration tests (live GitHub API).
pytestmark = pytest.mark.integration

FILOZ_ORG = "FilOzone"
PROJECT_NUMBER = 14


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
# fetch_items_rest
# ---------------------------------------------------------------------------


class TestFetchItemsRest:
    """Tests for the REST item fetcher."""

    def test_returns_dict_with_expected_keys(self, session: requests.Session):
        result = fetch_items_rest(
            session,
            org=FILOZ_ORG,
            project_number=PROJECT_NUMBER,
            query="is:issue",
            max_pages=1,
            per_page=5,
        )
        assert isinstance(result, dict)
        assert "items" in result
        assert "next_cursor" in result
        assert "pages_fetched" in result
        assert "has_more" in result

    def test_max_pages_caps_fetch(self, session: requests.Session):
        result = fetch_items_rest(
            session,
            org=FILOZ_ORG,
            project_number=PROJECT_NUMBER,
            query="is:issue",
            max_pages=1,
            per_page=5,
        )
        assert result["pages_fetched"] == 1
        assert len(result["items"]) <= 5

    def test_cursor_resumes_pagination(self, session: requests.Session):
        r1 = fetch_items_rest(
            session,
            org=FILOZ_ORG,
            project_number=PROJECT_NUMBER,
            query="is:pr",
            max_pages=1,
            per_page=3,
        )
        assert r1["has_more"] is True
        assert r1["next_cursor"] is not None

        r2 = fetch_items_rest(
            session,
            org=FILOZ_ORG,
            project_number=PROJECT_NUMBER,
            query="is:pr",
            max_pages=1,
            per_page=3,
            cursor=r1["next_cursor"],
        )
        assert len(r2["items"]) > 0

        ids1 = {item.get("node_id") for item in r1["items"]}
        ids2 = {item.get("node_id") for item in r2["items"]}
        assert ids1.isdisjoint(ids2), "Pages should not have overlapping items"

    def test_invalid_filter_returns_empty(self, session: requests.Session):
        result = fetch_items_rest(
            session,
            org=FILOZ_ORG,
            project_number=PROJECT_NUMBER,
            query="xyzzy_bogus_filter:nonsense",
            max_pages=1,
        )
        assert result["items"] == []
        assert result["has_more"] is False

    def test_no_max_pages_fetches_all(self, session: requests.Session):
        """Without max_pages, should exhaust all pages (use a narrow query)."""
        result = fetch_items_rest(
            session,
            org=FILOZ_ORG,
            project_number=PROJECT_NUMBER,
            query='"cycle-theme":"Contract Upgrade" -last-updated:1days',
        )
        assert result["has_more"] is False
        assert result["next_cursor"] is None


# ---------------------------------------------------------------------------
# list_items
# ---------------------------------------------------------------------------


class TestListItems:
    """Tests for the high-level list_items function."""

    def test_returns_expected_shape(self, session: requests.Session):
        result = list_items(
            session, org=FILOZ_ORG, project_number=PROJECT_NUMBER,
            query="is:issue", per_page=5,
        )
        assert "items" in result
        assert "next_cursor" in result
        assert "has_more" in result
        assert "debug" in result

    def test_items_have_default_fields(self, session: requests.Session):
        result = list_items(
            session, org=FILOZ_ORG, project_number=PROJECT_NUMBER,
            query="is:pr", per_page=3,
        )
        assert len(result["items"]) > 0
        item = result["items"][0]
        for field in ["Repository", "Id", "Title", "Status", "_node_id"]:
            assert field in item, f"Missing field: {field}"

    def test_custom_fields(self, session: requests.Session):
        result = list_items(
            session, org=FILOZ_ORG, project_number=PROJECT_NUMBER,
            query="is:pr",
            fields=["Repository", "Id", "Title"],
            per_page=3,
        )
        item = result["items"][0]
        assert "Repository" in item
        assert "Id" in item
        assert "Title" in item
        assert "Cycle Theme" not in item

    def test_cursor_pagination(self, session: requests.Session):
        r1 = list_items(
            session, org=FILOZ_ORG, project_number=PROJECT_NUMBER,
            query="is:pr", per_page=3,
        )
        assert r1["has_more"] is True

        r2 = list_items(
            session, org=FILOZ_ORG, project_number=PROJECT_NUMBER,
            query="is:pr", per_page=3, cursor=r1["next_cursor"],
        )
        assert len(r2["items"]) > 0

        ids1 = {(it["Repository"], it["Id"]) for it in r1["items"]}
        ids2 = {(it["Repository"], it["Id"]) for it in r2["items"]}
        assert ids1.isdisjoint(ids2)

    def test_debug_info(self, session: requests.Session):
        result = list_items(
            session, org=FILOZ_ORG, project_number=PROJECT_NUMBER,
            query="is:issue", per_page=5,
        )
        debug = result["debug"]
        assert debug["rest_query"] == "is:issue"
        assert "rest_endpoint" in debug
        assert "rest_field_ids" in debug
        assert isinstance(debug["items_returned"], int)

    def test_time_based_filter(self, session: requests.Session):
        """Verify last-updated filter works through the full stack."""
        result = list_items(
            session, org=FILOZ_ORG, project_number=PROJECT_NUMBER,
            query="-last-updated:1days", per_page=50,
        )
        assert len(result["items"]) > 0

    def test_combined_filters(self, session: requests.Session):
        """Verify combining custom field + time-based filter."""
        result = list_items(
            session, org=FILOZ_ORG, project_number=PROJECT_NUMBER,
            query='"cycle-theme":"Contract Upgrade" -last-updated:7days',
            per_page=50,
        )
        assert len(result["items"]) >= 1


# ---------------------------------------------------------------------------
# resolve_view_url
# ---------------------------------------------------------------------------


class TestResolveViewUrl:
    """Tests for resolving effective filters from project view URLs."""

    def test_uses_saved_view_filter_when_no_override(self, session: requests.Session):
        resolved = resolve_view_url(
            session,
            view_url="https://github.com/orgs/FilOzone/projects/14/views/20",
        )
        assert resolved["view_number"] == 20
        assert isinstance(resolved["base_filter"], str)
        assert isinstance(resolved["effective_filter"], str)
        assert len(resolved["view_fields"]) > 0
        assert "Title" in resolved["view_fields"]

    def test_uses_filter_query_override_and_slice(self, session: requests.Session):
        resolved = resolve_view_url(
            session,
            view_url=(
                "https://github.com/orgs/FilOzone/projects/14/views/20"
                "?sliceBy%5Bvalue%5D=Dealbot"
                "&filterQuery=-status%3A%22%F0%9F%8E%89+Done%22"
            ),
        )
        assert resolved["override_filter"] is not None
        assert '-status:"🎉 Done"' in resolved["base_filter"]
        assert resolved["slice_group_field"] is None
        assert resolved["slice_filter"] is None
        assert resolved["effective_filter"] == resolved["base_filter"]

    def test_visible_fields_query_param_overrides_view_field_order(self, session: requests.Session):
        view_url = (
            "https://github.com/orgs/FilOzone/projects/14/views/20"
            "?visibleFields=%5B%22Repository%22%2C%22Title%22%2C%22Assignees%22%2C%22Reviewers%22%2C%22Linked+pull+requests%22%2C194437039%2C245538973%2C%22Milestone%22%2C%22Status%22%2C%22Parent+issue%22%2C204711739%2C242588518%2C244708427%2C%22Sub-issues+progress%22%2C%22Labels%22%5D"
        )
        resolved = resolve_view_url(session, view_url=view_url)
        assert resolved["visible_fields_override"] is not None
        params = parse_qs(urlparse(view_url).query)
        raw_visible = (params.get("visibleFields") or [None])[0]
        assert raw_visible is not None
        payload = json.loads(raw_visible)
        id_to_name = {
            fid: name
            for name, fid in list_field_ids_by_name(
                session,
                org=FILOZ_ORG,
                project_number=PROJECT_NUMBER,
            ).items()
        }
        expected = []
        for value in payload:
            if isinstance(value, str):
                expected.append(value)
            elif isinstance(value, int):
                mapped = id_to_name.get(value)
                if mapped:
                    expected.append(mapped)
        expected = list(dict.fromkeys(expected))
        assert resolved["view_fields"] == expected


# ---------------------------------------------------------------------------
# list_fields
# ---------------------------------------------------------------------------


class TestListFields:
    """Tests for field discovery."""

    def test_returns_field_map(self, session: requests.Session):
        fields = list_fields(session, org=FILOZ_ORG, project_number=PROJECT_NUMBER)
        assert isinstance(fields, dict)
        assert len(fields) > 0
        assert "Status" in fields
        assert isinstance(fields["Status"], int)

    def test_known_fields_present(self, session: requests.Session):
        fields = list_fields(session, org=FILOZ_ORG, project_number=PROJECT_NUMBER)
        expected = ["Status", "Milestone", "Cycle Theme"]
        for name in expected:
            assert name in fields, f"Expected field '{name}' not found"


# ---------------------------------------------------------------------------
# list_field_options
# ---------------------------------------------------------------------------


class TestListFieldOptions:
    """Tests for field option discovery."""

    def test_status_field_options(self, session: requests.Session):
        result = list_field_options(
            session, org=FILOZ_ORG, project_number=PROJECT_NUMBER,
            field_name="Status",
        )
        assert "project_id" in result
        assert "fields" in result
        assert "Status" in result["fields"]

        status = result["fields"]["Status"]
        assert status["type"] == "single_select"
        assert len(status["options"]) > 0
        option_names = [opt["name"] for opt in status["options"]]
        assert any("Done" in name for name in option_names)

    def test_iteration_field(self, session: requests.Session):
        result = list_field_options(
            session, org=FILOZ_ORG, project_number=PROJECT_NUMBER,
            field_name="Cycle",
        )
        if "Cycle" not in result["fields"]:
            pytest.skip("Cycle field not found on project")
        cycle = result["fields"]["Cycle"]
        assert cycle["type"] == "iteration"
        assert "iterations" in cycle
        assert "completed_iterations" in cycle

    def test_nonexistent_field(self, session: requests.Session):
        result = list_field_options(
            session, org=FILOZ_ORG, project_number=PROJECT_NUMBER,
            field_name="NonexistentField12345",
        )
        assert result["fields"] == {}

    def test_all_fields_when_no_name(self, session: requests.Session):
        result = list_field_options(
            session, org=FILOZ_ORG, project_number=PROJECT_NUMBER,
        )
        assert len(result["fields"]) > 3


# ---------------------------------------------------------------------------
# list_field_ids_by_name
# ---------------------------------------------------------------------------


class TestListFieldIdsByName:
    def test_returns_field_map(self, session: requests.Session):
        fields = list_field_ids_by_name(
            session, org=FILOZ_ORG, project_number=PROJECT_NUMBER,
        )
        assert isinstance(fields, dict)
        assert "Status" in fields
        assert isinstance(fields["Status"], int)


# ---------------------------------------------------------------------------
# get_item
# ---------------------------------------------------------------------------


class TestGetItem:
    def _find_known_item(self, session: requests.Session) -> dict:
        """Find a known item on the board to test against."""
        result = list_items(
            session, org=FILOZ_ORG, project_number=PROJECT_NUMBER,
            query="is:pr", per_page=1,
        )
        assert len(result["items"]) > 0
        return result["items"][0]

    def test_lookup_by_short_ref(self, session: requests.Session):
        # Short refs expand using the default org, so we need an item from that org
        result = list_items(
            session, org=FILOZ_ORG, project_number=PROJECT_NUMBER,
            query=f"is:pr repo:{FILOZ_ORG}/*", per_page=1,
        )
        assert len(result["items"]) > 0
        known = result["items"][0]
        repo_full = known["Repository"]
        number = known["Id"]
        repo_name = repo_full.split("/", 1)[1] if "/" in repo_full else repo_full

        details = get_item(
            session, org=FILOZ_ORG, project_number=PROJECT_NUMBER,
            item_ref=f"{repo_name}#{number}",
        )
        assert details is not None
        assert details["Id"] == number
        assert "Status" in details

    def test_lookup_by_full_ref(self, session: requests.Session):
        known = self._find_known_item(session)
        repo_full = known["Repository"]
        number = known["Id"]

        details = get_item(
            session, org=FILOZ_ORG, project_number=PROJECT_NUMBER,
            item_ref=f"{repo_full}#{number}",
        )
        assert details is not None
        assert details["Id"] == number

    def test_lookup_by_url(self, session: requests.Session):
        known = self._find_known_item(session)
        url = known.get("url", "")
        if not url:
            pytest.skip("No URL on known item")

        details = get_item(
            session, org=FILOZ_ORG, project_number=PROJECT_NUMBER,
            item_ref=url,
        )
        assert details is not None
        assert details["Id"] == known["Id"]

    def test_nonexistent_item(self, session: requests.Session):
        details = get_item(
            session, org=FILOZ_ORG, project_number=PROJECT_NUMBER,
            item_ref="nonexistent-repo-xyz#99999",
        )
        assert details is None

    def test_invalid_ref_format(self, session: requests.Session):
        details = get_item(
            session, org=FILOZ_ORG, project_number=PROJECT_NUMBER,
            item_ref="not-a-valid-ref",
        )
        assert details is None
