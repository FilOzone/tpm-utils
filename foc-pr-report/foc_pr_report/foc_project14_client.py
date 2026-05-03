"""Backward-compatibility shim — all logic has moved.

Core project board functions → ``github_projects_client``
PR-specific functions → ``foc_pr_report.pr_enrichment``

This module re-exports under the old names so that any external code
importing ``foc_pr_report.foc_project14_client`` keeps working.
"""

# Re-exports from github_projects_client (generic board functions)
from github_projects_client.api import graphql_query  # noqa: F401
from github_projects_client.api import (  # noqa: F401
    list_field_ids_by_name as list_project_v2_field_ids_by_name,
    fetch_items_rest as fetch_project_v2_items_rest,
)
from github_projects_client.views import resolve_view_url as resolve_view_url_filter  # noqa: F401

# Re-exports from pr_enrichment (PR-specific functions)
from foc_pr_report.pr_enrichment import (  # noqa: F401
    FILOZ_ORG,
    PROJECT_NUMBER,
    PROJECT_QUERY,
    ITEMS_QUERY,
    enrich_pull_items_with_submitted_reviewers,
    fetch_project_board_items_rest_filtered,
    fetch_pull_request_review_activity,
    fetch_pull_request_review_logins,
    rest_board_item_to_graphql_node,
    field_values_by_name,
    fetch_all_project_items,
)

GRAPHQL_URL = "https://api.github.com/graphql"
