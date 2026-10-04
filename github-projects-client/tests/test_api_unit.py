"""
Unit tests for api.py's graphql_query -- no network access required.

Focus: telling GitHub's rate limits (403 with a rate-limit message or an
exhausted quota, or 429) apart from real failures, and surfacing GitHub's
own error message instead of a bare "403 Forbidden".

Run:
    cd github-projects-client
    uv run pytest tests/test_api_unit.py -v
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import requests

from github_projects_client.api import (
    GitHubAPIError,
    GitHubRateLimitError,
    graphql_query,
)


def _fake_response(
    status_code: int, body: dict, headers: dict | None = None
) -> MagicMock:
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.ok = status_code < 400
    resp.reason = "Forbidden" if status_code == 403 else "Error"
    resp.url = "https://api.github.com/graphql"
    resp.headers = headers or {}
    resp.json.return_value = body
    return resp


def _session_returning(resp: MagicMock) -> MagicMock:
    session = MagicMock()
    session.post.return_value = resp
    return session


class TestGraphqlQueryErrors:
    def test_returns_data_on_success(self):
        session = _session_returning(_fake_response(200, {"data": {"ok": True}}))
        assert graphql_query(session, "query {}") == {"ok": True}

    def test_secondary_rate_limit_403_raises_rate_limit_error(self):
        session = _session_returning(
            _fake_response(
                403, {"message": "You have exceeded a secondary rate limit."}
            )
        )
        with pytest.raises(GitHubRateLimitError) as excinfo:
            graphql_query(session, "query {}")
        assert "secondary rate limit" in str(excinfo.value)
        assert session.post.call_count == 1  # never retried here

    def test_429_raises_rate_limit_error(self):
        session = _session_returning(_fake_response(429, {}))
        with pytest.raises(GitHubRateLimitError):
            graphql_query(session, "query {}")

    def test_exhausted_primary_quota_raises_rate_limit_error(self):
        session = _session_returning(
            _fake_response(403, {}, headers={"X-RateLimit-Remaining": "0"})
        )
        with pytest.raises(GitHubRateLimitError):
            graphql_query(session, "query {}")

    def test_rate_limit_error_is_still_an_http_error(self):
        """Existing `except requests.HTTPError` callers must keep catching it."""
        session = _session_returning(_fake_response(429, {}))
        with pytest.raises(requests.HTTPError):
            graphql_query(session, "query {}")

    def test_permissions_403_is_plain_http_error_with_github_message(self):
        session = _session_returning(
            _fake_response(403, {"message": "Resource not accessible by integration"})
        )
        with pytest.raises(requests.HTTPError) as excinfo:
            graphql_query(session, "query {}")
        assert not isinstance(excinfo.value, GitHubRateLimitError)
        assert "Resource not accessible by integration" in str(excinfo.value)

    def test_graphql_errors_still_raised_on_200(self):
        session = _session_returning(
            _fake_response(200, {"errors": [{"message": "boom"}]})
        )
        with pytest.raises(GitHubAPIError):
            graphql_query(session, "query {}")
