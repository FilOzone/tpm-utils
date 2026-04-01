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

# Synthetic row: PRs with no assignee (assignee column) or no reviewer (reviewer column).
EMPTY_ROW_LOGIN = "empty"

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


def _person_row_sort_key(t: Row) -> Tuple[int, str, Tuple[int, str], str]:
    """Real users first (A–z), then the synthetic ``empty`` row, then by status."""
    login, status, _, _ = t
    group = 1 if login == EMPTY_ROW_LOGIN else 0
    return (group, login.lower(), _status_sort_key(status), status)


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

        if not assignee_logins:
            assignee_counts[(EMPTY_ROW_LOGIN, status)] += 1
        else:
            for login in assignee_logins:
                assignee_counts[(login, status)] += 1

        if not reviewer_logins:
            reviewer_counts[(EMPTY_ROW_LOGIN, status)] += 1
        else:
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

    rows.sort(key=_person_row_sort_key)
    return rows


def render_markdown(rows: List[Row]) -> str:
    """GFM table with linked username, state label, assignee count, reviewer count."""
    lines = [
        "| who | state | assignee | reviewer |",
        "| --- | --- | --- | --- |",
    ]

    for login, status, a_count, r_count in rows:
        if login == EMPTY_ROW_LOGIN:
            user_q = BASE_FILTER
            state_q = _filter_body(BASE_FILTER, f'status:"{status}"')
            assign_q = _filter_body(BASE_FILTER, f'status:"{status}"', "no:assignee")
            rev_q = _filter_body(BASE_FILTER, f'status:"{status}"', "review:none")
            label = "empty"
        else:
            user_q = _filter_body(BASE_FILTER, login)
            state_q = _filter_body(BASE_FILTER, f'status:"{status}"', login)
            assign_q = _filter_body(BASE_FILTER, f'status:"{status}"', f"assignee:{login}")
            rev_q = _filter_body(BASE_FILTER, f'status:"{status}"', f"reviewers:{login}")
            label = login

        lines.append(
            "| "
            + f"[{label}]({view2_url(user_q)}) | "
            + f"[{status}]({view2_url(state_q)}) | "
            + f"[{a_count}]({view2_url(assign_q)}) | "
            + f"[{r_count}]({view2_url(rev_q)}) |"
        )

    return "\n".join(lines) + "\n"


def aggregate_repo_status_matrix(
    items: List[Dict[str, Any]],
) -> Tuple[List[str], List[str], Dict[Tuple[str, str], int]]:
    """
    Count PRs per (repository, Status) for items matching the same rules as aggregate_rows
    (pull requests only; Status not Done/Todo).
    """
    counts: Dict[Tuple[str, str], int] = defaultdict(int)

    for item in items:
        content = item.get("content")
        if not content or content.get("__typename") != "PullRequest":
            continue

        field_values = field_values_by_name(item)
        status = field_values.get("Status")
        if not status or status in (STATUS_DONE, STATUS_TODO):
            continue

        repo = (content.get("repository") or {}).get("nameWithOwner")
        if not isinstance(repo, str) or not repo.strip():
            repo = "unknown"

        counts[(repo, status)] += 1

    repos = sorted({r for (r, _) in counts}, key=str.lower)
    statuses = sorted({s for (_, s) in counts}, key=lambda s: (_status_sort_key(s), s))
    return repos, statuses, dict(counts)


def render_repo_status_markdown(
    items: List[Dict[str, Any]],
) -> str:
    """
    Markdown table: rows = repository, columns = status, cells = PR count (linked to View 2).

    Row header links: BASE_FILTER + repo:owner/name.
    Column header links: BASE_FILTER + status:\"…\" (no repo).
    Cell links: BASE_FILTER + repo + status (intersection).
    Total column: per-repo sum, linked like the row repo filter; header links BASE_FILTER.
    Total row: per-status sum, linked like status headers; grand total links BASE_FILTER.
    """
    repos, statuses, counts = aggregate_repo_status_matrix(items)

    if not repos or not statuses:
        return "_No pull requests to show in this matrix._\n"

    lines: List[str] = []

    status_headers = [
        f"[{status}]({view2_url(_filter_body(BASE_FILTER, f'status:\"{status}\"'))})"
        for status in statuses
    ]
    total_col_header = f"[Total]({view2_url(BASE_FILTER)})"
    lines.append("| Repository | " + " | ".join(status_headers) + f" | {total_col_header} |")

    col_count = len(statuses) + 2  # Repository + statuses + Total
    sep = ["---"] * col_count
    lines.append("| " + " | ".join(sep) + " |")

    column_totals = [sum(counts.get((r, s), 0) for r in repos) for s in statuses]
    grand_total = sum(column_totals)

    for repo in repos:
        if repo == "unknown":
            first = "unknown"
            row_q_repo = None
        else:
            row_q_repo = _filter_body(BASE_FILTER, f"repo:{repo}")
            first = f"[{repo}]({view2_url(row_q_repo)})"

        row_out = [first]
        row_sum = 0
        for status in statuses:
            n = counts.get((repo, status), 0)
            row_sum += n
            if n == 0:
                row_out.append("0")
            else:
                cell_q = _filter_body(BASE_FILTER, f"repo:{repo}", f'status:"{status}"')
                row_out.append(f"[{n}]({view2_url(cell_q)})")

        if row_sum == 0:
            row_out.append("0")
        elif row_q_repo is not None:
            row_out.append(f"[{row_sum}]({view2_url(row_q_repo)})")
        else:
            row_out.append(str(row_sum))

        lines.append("| " + " | ".join(row_out) + " |")

    total_first = f"[Total]({view2_url(BASE_FILTER)})"
    total_row_cells: List[str] = [total_first]
    for status, col_sum in zip(statuses, column_totals, strict=True):
        if col_sum == 0:
            total_row_cells.append("0")
        else:
            col_q = _filter_body(BASE_FILTER, f'status:"{status}"')
            total_row_cells.append(f"[{col_sum}]({view2_url(col_q)})")
    if grand_total == 0:
        total_row_cells.append("0")
    else:
        total_row_cells.append(f"[{grand_total}]({view2_url(BASE_FILTER)})")
    lines.append("| " + " | ".join(total_row_cells) + " |")

    return "\n".join(lines) + "\n"


def render_full_markdown(
    items: List[Dict[str, Any]],
    person_rows: List[Row],
) -> str:
    """Person-centric table then repository × status matrix."""
    parts = [
        "## PR count by individual",
        "",
        render_markdown(person_rows).rstrip(),
        "",
    ]
    parts.append("## PR count by repository and status")
    parts.append("")
    parts.append(render_repo_status_markdown(items).rstrip())
    parts.append("")
    return "\n".join(parts)
