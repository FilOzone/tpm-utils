"""Unit tests for the get_board_context coordinator tool.

These are pure-logic tests — no network access or GITHUB_TOKEN required.

Run:
    cd filozzy-mcp
    uv run pytest tests/test_format.py -v
"""

from __future__ import annotations

from filozzy_mcp.server import (
    get_board_context,
    GITHUB_ORG,
    GITHUB_PROJECT_NUMBER,
    API_BASE_URL,
)


class TestGetBoardContext:
    def test_returns_string(self):
        result = get_board_context()
        assert isinstance(result, str)

    def test_contains_board_identity(self):
        result = get_board_context()
        assert GITHUB_ORG in result
        assert str(GITHUB_PROJECT_NUMBER) in result

    def test_contains_api_base_url(self):
        result = get_board_context()
        assert API_BASE_URL in result

    def test_contains_quick_start_examples(self):
        result = get_board_context()
        assert "/items" in result
        assert "PUT" in result
        assert "/fields" in result

    def test_contains_query_syntax(self):
        result = get_board_context()
        assert "Query Syntax" in result
        assert "status:" in result
        assert "is:pr" in result

    def test_contains_openapi_link(self):
        result = get_board_context()
        assert "/openapi.json" in result
        assert "/docs" in result

    def test_contains_curl_examples(self):
        result = get_board_context()
        assert "curl" in result
        assert "Authorization: Bearer" in result
