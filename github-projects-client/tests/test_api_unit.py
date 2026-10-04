"""
Unit tests for api.py's graphql_query -- no network access required.

Focus: retry-with-backoff when GitHub's primary/secondary rate limit
returns a 403 mid-run (see github_projects_client/api.py's
_MAX_RATE_LIMIT_RETRIES docstring for why this matters -- a batched Cycle
rollover can trip this after a burst of mutations).

Run:
    cd github-projects-client
    uv run pytest tests/test_api_unit.py -v
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import requests

from github_projects_client.api import GitHubAPIError, graphql_query


def _fake_response(
    status_code: int, body: dict, headers: dict | None = None
) -> MagicMock:
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.headers = headers or {}
    resp.json.return_value = body

    def raise_for_status():
        if status_code >= 400:
            err = requests.HTTPError(f"{status_code} error")
            err.response = resp
            raise err

    resp.raise_for_status.side_effect = raise_for_status
    return resp


class TestGraphqlQueryRateLimitRetry:
    def test_succeeds_without_retry_when_not_rate_limited(self):
        session = MagicMock()
        session.post.return_value = _fake_response(200, {"data": {"ok": True}})
        sleep = MagicMock()

        result = graphql_query(session, "query {}", sleep=sleep)

        assert result == {"ok": True}
        sleep.assert_not_called()
        assert session.post.call_count == 1

    def test_retries_on_secondary_rate_limit_then_succeeds(self):
        session = MagicMock()
        session.post.side_effect = [
            _fake_response(
                403,
                {"message": "You have exceeded a secondary rate limit ..."},
                headers={"Retry-After": "5"},
            ),
            _fake_response(200, {"data": {"ok": True}}),
        ]
        sleep = MagicMock()

        result = graphql_query(session, "query {}", sleep=sleep)

        assert result == {"ok": True}
        assert session.post.call_count == 2
        sleep.assert_called_once_with(5.0)

    def test_falls_back_to_exponential_backoff_without_retry_after_header(self):
        session = MagicMock()
        session.post.side_effect = [
            _fake_response(
                403, {"message": "API rate limit exceeded for installation"}
            ),
            _fake_response(200, {"data": {"ok": True}}),
        ]
        sleep = MagicMock()

        graphql_query(session, "query {}", sleep=sleep)

        sleep.assert_called_once_with(1.0)  # 2**0

    def test_gives_up_after_max_retries(self):
        session = MagicMock()
        session.post.return_value = _fake_response(
            403, {"message": "secondary rate limit"}
        )
        sleep = MagicMock()

        with pytest.raises(requests.HTTPError):
            graphql_query(session, "query {}", sleep=sleep)

        # 1 initial attempt + 3 retries = 4 calls total.
        assert session.post.call_count == 4
        assert sleep.call_count == 3

    def test_non_rate_limit_403_is_not_retried(self):
        """A real auth/permissions 403 (no 'rate limit' in the message) must
        fail immediately, not be mistaken for a throttling response."""
        session = MagicMock()
        session.post.return_value = _fake_response(
            403, {"message": "Resource not accessible by integration"}
        )
        sleep = MagicMock()

        with pytest.raises(requests.HTTPError):
            graphql_query(session, "query {}", sleep=sleep)

        assert session.post.call_count == 1
        sleep.assert_not_called()

    def test_graphql_errors_still_raised_after_success(self):
        session = MagicMock()
        session.post.return_value = _fake_response(
            200, {"errors": [{"message": "boom"}]}
        )

        with pytest.raises(GitHubAPIError):
            graphql_query(session, "query {}")
