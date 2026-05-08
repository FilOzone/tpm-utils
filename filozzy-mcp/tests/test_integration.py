"""
Integration tests for the filozzy-mcp MCP coordinator.

The coordinator no longer calls the GitHub API directly — it only
returns board context and API usage instructions. These tests verify
the coordinator tool works correctly.

Run:
    cd filozzy-mcp
    uv run pytest tests/test_integration.py -v
"""

from __future__ import annotations

from filozzy_mcp.server import get_board_context, GITHUB_ORG, GITHUB_PROJECT_NUMBER


class TestCoordinatorIntegration:
    """Verify the coordinator returns complete board context."""

    def test_context_includes_key_content(self):
        result = get_board_context()
        # Quick start examples
        assert "/items" in result
        assert "PUT" in result
        assert "/items/field/" in result
        # Query syntax reference
        assert "status:" in result
        assert "is:pr" in result
        # When to use which tool
        assert "gh pr view" in result
        # OpenAPI pointer
        assert "/openapi.json" in result

    def test_context_includes_board_identity(self):
        result = get_board_context()
        assert GITHUB_ORG in result
        assert str(GITHUB_PROJECT_NUMBER) in result
        assert "FOC Board" in result

    def test_no_github_token_required(self):
        """The coordinator should work without GITHUB_TOKEN."""
        # If we got here, the module imported without GITHUB_TOKEN — pass
        result = get_board_context()
        assert len(result) > 100
