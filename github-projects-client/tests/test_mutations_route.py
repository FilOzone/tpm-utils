"""
Unit tests for the mutation route — no network access required.

Tests the consolidated PUT /orgs/{org}/projects/{project_number}/items/field/{field_name}
endpoint with mocked client functions.

Run:
    cd github-projects-client
    uv run pytest tests/test_mutations_route.py -v
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from github_projects_client.server.app import create_app

AUTH_HEADER = {"Authorization": "Bearer fake-token-for-tests"}


@pytest.fixture()
def client():
    app = create_app()
    return TestClient(app, raise_server_exceptions=False)


# --- Helpers ---


def _bulk_result(items: list[dict], *, success_count=None, failure_count=None):
    """Build a mock return value matching client_set_field_value_bulk's shape."""
    sc = (
        success_count
        if success_count is not None
        else sum(1 for i in items if i.get("success"))
    )
    fc = (
        failure_count
        if failure_count is not None
        else sum(1 for i in items if not i.get("success"))
    )
    return {"success_count": sc, "failure_count": fc, "results": items}


# --- Success cases ---


class TestSetFieldSuccess:
    def test_single_item(self, client):
        mock_result = _bulk_result(
            [
                {
                    "item_ref": "dealbot#458",
                    "success": True,
                    "old_value": "🐱 Todo",
                    "new_value": "⌨️ In Progress",
                },
            ]
        )
        with (
            patch(
                "github_projects_client.server.routes.mutations.client_set_field_value_bulk",
                return_value=mock_result,
            ),
            patch(
                "github_projects_client.server.routes.mutations._get_caller",
                return_value="testuser",
            ),
            patch("github_projects_client.server.routes.mutations.log_action"),
        ):
            resp = client.put(
                "/orgs/TestOrg/projects/1/items/field/Status",
                json={"item_refs": ["dealbot#458"], "value": "⌨️ In Progress"},
                headers=AUTH_HEADER,
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success_count"] == 1
        assert body["failure_count"] == 0
        assert len(body["results"]) == 1
        assert body["results"][0]["item_ref"] == "dealbot#458"
        assert body["results"][0]["old_value"] == "🐱 Todo"
        assert body["results"][0]["new_value"] == "⌨️ In Progress"

    def test_multiple_items(self, client):
        mock_result = _bulk_result(
            [
                {
                    "item_ref": "dealbot#458",
                    "success": True,
                    "old_value": "",
                    "new_value": "🎉 Done",
                },
                {
                    "item_ref": "synapse-sdk#748",
                    "success": True,
                    "old_value": "🐱 Todo",
                    "new_value": "🎉 Done",
                },
            ]
        )
        with (
            patch(
                "github_projects_client.server.routes.mutations.client_set_field_value_bulk",
                return_value=mock_result,
            ),
            patch(
                "github_projects_client.server.routes.mutations._get_caller",
                return_value="testuser",
            ),
            patch("github_projects_client.server.routes.mutations.log_action"),
        ):
            resp = client.put(
                "/orgs/TestOrg/projects/1/items/field/Status",
                json={
                    "item_refs": ["dealbot#458", "synapse-sdk#748"],
                    "value": "🎉 Done",
                },
                headers=AUTH_HEADER,
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success_count"] == 2
        assert body["failure_count"] == 0
        assert len(body["results"]) == 2

    def test_field_name_with_spaces(self, client):
        """Field names with spaces work via URL-encoding (Cycle%20Theme)."""
        mock_result = _bulk_result(
            [
                {
                    "item_ref": "dealbot#458",
                    "success": True,
                    "old_value": "",
                    "new_value": "Dealbot",
                },
            ]
        )
        with (
            patch(
                "github_projects_client.server.routes.mutations.client_set_field_value_bulk",
                return_value=mock_result,
            ) as mock_bulk,
            patch(
                "github_projects_client.server.routes.mutations._get_caller",
                return_value="testuser",
            ),
            patch("github_projects_client.server.routes.mutations.log_action"),
        ):
            resp = client.put(
                "/orgs/TestOrg/projects/1/items/field/Cycle%20Theme",
                json={"item_refs": ["dealbot#458"], "value": "Dealbot"},
                headers=AUTH_HEADER,
            )

        assert resp.status_code == 200
        # Verify the decoded field name was passed to the client
        mock_bulk.assert_called_once()
        call_kwargs = mock_bulk.call_args
        assert call_kwargs.kwargs["field_name"] == "Cycle Theme"


# --- Partial failure ---


class TestSetFieldPartialFailure:
    def test_mixed_success_and_failure(self, client):
        mock_result = _bulk_result(
            [
                {
                    "item_ref": "dealbot#458",
                    "success": True,
                    "old_value": "",
                    "new_value": "⌨️ In Progress",
                },
                {
                    "item_ref": "bad-ref#999",
                    "success": False,
                    "error": "Could not find item: bad-ref#999",
                },
            ]
        )
        with (
            patch(
                "github_projects_client.server.routes.mutations.client_set_field_value_bulk",
                return_value=mock_result,
            ),
            patch(
                "github_projects_client.server.routes.mutations._get_caller",
                return_value="testuser",
            ),
            patch("github_projects_client.server.routes.mutations.log_action"),
        ):
            resp = client.put(
                "/orgs/TestOrg/projects/1/items/field/Status",
                json={
                    "item_refs": ["dealbot#458", "bad-ref#999"],
                    "value": "⌨️ In Progress",
                },
                headers=AUTH_HEADER,
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success_count"] == 1
        assert body["failure_count"] == 1
        failed = [r for r in body["results"] if not r["success"]]
        assert len(failed) == 1
        assert "Could not find item" in failed[0]["error"]


# --- Audit logging ---


class TestAuditLogging:
    def test_logs_successful_mutations_only(self, client):
        mock_result = _bulk_result(
            [
                {
                    "item_ref": "dealbot#458",
                    "success": True,
                    "old_value": "🐱 Todo",
                    "new_value": "⌨️ In Progress",
                },
                {"item_ref": "bad#999", "success": False, "error": "not found"},
            ]
        )
        with (
            patch(
                "github_projects_client.server.routes.mutations.client_set_field_value_bulk",
                return_value=mock_result,
            ),
            patch(
                "github_projects_client.server.routes.mutations._get_caller",
                return_value="sweepbot",
            ),
            patch(
                "github_projects_client.server.routes.mutations.log_action"
            ) as mock_log,
        ):
            client.put(
                "/orgs/FilOzone/projects/14/items/field/Status",
                json={
                    "item_refs": ["dealbot#458", "bad#999"],
                    "value": "⌨️ In Progress",
                },
                headers=AUTH_HEADER,
            )

        # Only the successful mutation should be logged
        assert mock_log.call_count == 1
        call_kwargs = mock_log.call_args.kwargs
        assert call_kwargs["caller"] == "sweepbot"
        assert call_kwargs["endpoint"] == "/items/field/Status"
        assert call_kwargs["params"]["item_ref"] == "dealbot#458"
        assert call_kwargs["result"] == "success"
        assert call_kwargs["old_value"] == "🐱 Todo"
        assert call_kwargs["new_value"] == "⌨️ In Progress"


# --- Validation errors ---


class TestValidation:
    def test_missing_auth_header(self, client):
        resp = client.put(
            "/orgs/TestOrg/projects/1/items/field/Status",
            json={"item_refs": ["dealbot#458"], "value": "⌨️ In Progress"},
        )
        assert resp.status_code in (401, 403)

    def test_missing_item_refs(self, client):
        resp = client.put(
            "/orgs/TestOrg/projects/1/items/field/Status",
            json={"value": "⌨️ In Progress"},
            headers=AUTH_HEADER,
        )
        assert resp.status_code == 422

    def test_missing_value(self, client):
        resp = client.put(
            "/orgs/TestOrg/projects/1/items/field/Status",
            json={"item_refs": ["dealbot#458"]},
            headers=AUTH_HEADER,
        )
        assert resp.status_code == 422

    def test_empty_body(self, client):
        resp = client.put(
            "/orgs/TestOrg/projects/1/items/field/Status",
            headers=AUTH_HEADER,
        )
        assert resp.status_code == 422


# --- Audit log token validation ---


class TestAuditLogAuth:
    def test_invalid_token_returns_401(self, client):
        """Audit log endpoint must validate the bearer token against GitHub."""
        mock_response = type("R", (), {"ok": False, "status_code": 401})()
        with patch(
            "github_projects_client.server.auth.req.get",
            return_value=mock_response,
        ):
            resp = client.get(
                "/orgs/TestOrg/projects/1/audit-log",
                headers={"Authorization": "Bearer bad-token"},
            )
        assert resp.status_code == 401

    def test_valid_token_returns_entries(self, client):
        """Audit log returns entries when the token is validated by GitHub."""
        mock_response = type(
            "R",
            (),
            {
                "ok": True,
                "status_code": 200,
                "json": lambda self: {"login": "testuser"},
            },
        )()
        with (
            patch(
                "github_projects_client.server.auth.req.get",
                return_value=mock_response,
            ),
            patch(
                "github_projects_client.server.routes.mutations.read_recent_entries",
                return_value=[],
            ),
        ):
            resp = client.get(
                "/orgs/TestOrg/projects/1/audit-log",
                headers=AUTH_HEADER,
            )
        assert resp.status_code == 200
        assert resp.json()["entries"] == []


# --- GraphQL auth error handling ---


class TestGitHubErrorHandling:
    def test_insufficient_scopes_returns_401(self, client):
        """INSUFFICIENT_SCOPES from GraphQL should surface as 401, not 500."""
        from github_projects_client.api import GitHubAuthError

        with (
            patch(
                "github_projects_client.server.routes.mutations.client_set_field_value_bulk",
                side_effect=GitHubAuthError(
                    "GitHub token is missing required OAuth/PAT scopes"
                ),
            ),
            patch(
                "github_projects_client.server.routes.mutations._get_caller",
                return_value="testuser",
            ),
        ):
            resp = client.put(
                "/orgs/TestOrg/projects/1/items/field/Status",
                json={"item_refs": ["dealbot#458"], "value": "⌨️ In Progress"},
                headers=AUTH_HEADER,
            )
        assert resp.status_code == 401
        body = resp.json()
        assert body["error"] == "unauthorized"
        assert "scopes" in body["message"]

    def test_graphql_error_returns_502_with_message(self, client):
        """Non-auth GraphQL errors should surface as 502, not swallowed as 500."""
        from github_projects_client.api import GitHubAPIError

        with (
            patch(
                "github_projects_client.server.routes.mutations.client_set_field_value_bulk",
                side_effect=GitHubAPIError(
                    "GraphQL errors: [{'message': 'something broke'}]"
                ),
            ),
            patch(
                "github_projects_client.server.routes.mutations._get_caller",
                return_value="testuser",
            ),
        ):
            resp = client.put(
                "/orgs/TestOrg/projects/1/items/field/Status",
                json={"item_refs": ["dealbot#458"], "value": "⌨️ In Progress"},
                headers=AUTH_HEADER,
            )
        assert resp.status_code == 502
        body = resp.json()
        assert body["error"] == "github_api_error"
        assert "something broke" in body["message"]
