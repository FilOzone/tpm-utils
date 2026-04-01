"""Aggregate Project 14 PRs and render Markdown."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Tuple
from urllib.parse import quote

from foc_project14_client import field_values_by_name

# Base board filter (View 2) — keep in sync with ManuallyApplied FOC table links
BASE_FILTER = 'is:pr -status:"🎉 Done" -status:"🐱 Todo"'

STATUS_DONE = "🎉 Done"
STATUS_TODO = "🐱 Todo"

PROJECT_VIEW_2 = "https://github.com/orgs/FilOzone/projects/14/views/2"

# Primary lanes first; other statuses sort after these, alphabetically
STATUS_ORDER = [
    "⌨️ In Progress",
    "🔎 Awaiting review",
    "✔️ Approved by reviewer",
]

Row = Tuple[str, str, int, int]


def _filter_body(*parts: str) -> str:
    return " ".join(parts)


def view2_url(filter_body: str) -> str:
    return f"{PROJECT_VIEW_2}?filterQuery={quote(filter_body)}"


def _status_sort_key(status: str) -> Tuple[int, str]:
    try:
        return (0, f"{STATUS_ORDER.index(status):04d}")
    except ValueError:
        return (1, status.lower())


def aggregate_rows(items: List[Dict[str, Any]]) -> List[Row]:
    """Return (login, status, assignee_count, reviewer_count) for each user/status lane."""
    assignee_counts: Dict[Tuple[str, str], int] = defaultdict(int)
    reviewer_counts: Dict[Tuple[str, str], int] = defaultdict(int)

    for item in items:
        content = item.get("content")
        if not content or content.get("__typename") != "PullRequest":
            continue

        field_values = field_values_by_name(item)
        status = field_values.get("Status")
        if not status or status in (STATUS_DONE, STATUS_TODO):
            continue

        assignee_nodes = content.get("assignees", {}).get("nodes", [])
        assignee_logins = [
            n.get("login")
            for n in assignee_nodes
            if n and n.get("login")
        ]

        # Reviewers: requested on the PR plus users who submitted a PR review (COMMENTED/APPROVED/…).
        # See README — board UI can show the latter even when they're no longer in requested_reviewers.
        reviewer_logins: set[str] = set()
        for rr in content.get("reviewRequests", {}).get("nodes", []):
            rev = rr.get("requestedReviewer") or {}
            login = rev.get("login")
            if login:
                reviewer_logins.add(login)
        for login in content.get("_submitted_reviewer_logins") or []:
            reviewer_logins.add(login)

        for login in assignee_logins:
            assignee_counts[(login, status)] += 1
        for login in reviewer_logins:
            reviewer_counts[(login, status)] += 1

    keys = set(assignee_counts) | set(reviewer_counts)
    rows: List[Row] = []
    for login, status in keys:
        a = assignee_counts.get((login, status), 0)
        r = reviewer_counts.get((login, status), 0)
        if a == 0 and r == 0:
            continue
        rows.append((login, status, a, r))

    rows.sort(key=lambda t: (t[0].lower(), _status_sort_key(t[1]), t[1]))
    return rows


def render_markdown(rows: List[Row]) -> str:
    """GFM table with linked username, state label, assignee count, reviewer count."""
    lines = [
        "| github username | state | assignee | reviewer |",
        "| --- | --- | --- | --- |",
    ]

    for login, status, a_count, r_count in rows:
        user_q = _filter_body(BASE_FILTER, login)
        state_q = _filter_body(BASE_FILTER, f'status:"{status}"', login)
        assign_q = _filter_body(BASE_FILTER, f'status:"{status}"', f"assignee:{login}")
        rev_q = _filter_body(BASE_FILTER, f'status:"{status}"', f"reviewers:{login}")

        lines.append(
            "| "
            + f"[{login}]({view2_url(user_q)}) | "
            + f"[{status}]({view2_url(state_q)}) | "
            + f"[{a_count}]({view2_url(assign_q)}) | "
            + f"[{r_count}]({view2_url(rev_q)}) |"
        )

    return "\n".join(lines) + "\n"
