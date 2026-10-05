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
    is_rate_limited,
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

    def test_rate_limited_graphql_error_on_200_raises_rate_limit_error(self):
        """GitHub can report throttling as HTTP 200 with a RATE_LIMITED error."""
        session = _session_returning(
            _fake_response(
                200,
                {
                    "data": None,
                    "errors": [
                        {
                            "type": "RATE_LIMITED",
                            "message": "API rate limit already exceeded for user ID 1.",
                        }
                    ],
                },
            )
        )
        with pytest.raises(GitHubRateLimitError) as excinfo:
            graphql_query(session, "query {}")
        assert "RATE_LIMITED" in str(excinfo.value)

    def test_graphql_errors_still_raised_on_200(self):
        session = _session_returning(
            _fake_response(200, {"errors": [{"message": "boom"}]})
        )
        with pytest.raises(GitHubAPIError):
            graphql_query(session, "query {}")


@pytest.mark.parametrize(
    "status, body, headers",
    [
        (403, {"message": "whatever"}, {"Retry-After": "60"}),
        (403, {"message": "You have triggered an abuse detection mechanism."}, {}),
        (
            200,
            {"errors": [{"message": "You have exceeded a secondary rate limit."}]},
            {},
        ),
    ],
    ids=["403-retry-after", "403-abuse-detection", "200-secondary-message"],
)
def test_other_documented_rate_limit_shapes(status, body, headers):
    assert is_rate_limited(_fake_response(status, body, headers))


@pytest.mark.parametrize(
    "status, body",
    [
        (403, {"message": "Resource not accessible by integration"}),
        (200, {"data": {"ok": True}}),
        (200, {"errors": [{"type": "NOT_FOUND", "message": "nope"}]}),
        (502, {}),
    ],
    ids=["403-permissions", "200-ok", "200-other-error", "502"],
)
def test_non_rate_limit_responses(status, body):
    assert not is_rate_limited(_fake_response(status, body))
