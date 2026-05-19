#!/usr/bin/env python3
"""Generate a weekly Markdown report for FilOzone/foc-problems activity."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote_plus

import requests


DEFAULT_REPO = "FilOzone/foc-problems"
DEFAULT_DAYS = 7
MAX_SEARCH_PAGES = 10
MAX_ACTIVITY_ITEMS = 8


@dataclass(frozen=True)
class ReportWindow:
    since: datetime
    until: datetime

    @property
    def since_date(self) -> str:
        return self.since.date().isoformat()

    @property
    def until_date(self) -> str:
        return self.until.date().isoformat()


class GitHubClient:
    def __init__(self, token: str | None):
        self.base_url = "https://api.github.com"
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "tpm-utils-foc-problems-report",
            }
        )
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}{path}"
        for attempt in range(3):
            response = self.session.get(url, params=params, timeout=30)
            if response.status_code == 403 and "rate limit" in response.text.lower():
                reset = response.headers.get("X-RateLimit-Reset")
                if reset and attempt < 2:
                    sleep_for = max(1, int(reset) - int(time.time()) + 1)
                    time.sleep(min(sleep_for, 60))
                    continue
            response.raise_for_status()
            return response.json()
        response.raise_for_status()
        return None

    def search_issues(self, query: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for page in range(1, MAX_SEARCH_PAGES + 1):
            data = self.get(
                "/search/issues",
                {
                    "q": query,
                    "sort": "updated",
                    "order": "desc",
                    "per_page": 100,
                    "page": page,
                },
            )
            page_items = data.get("items", [])
            items.extend(page_items)
            if len(page_items) < 100:
                break
        return items

    def issue_timeline(self, repo: str, number: int) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for page in range(1, 6):
            page_items = self.get(
                f"/repos/{repo}/issues/{number}/timeline",
                {"per_page": 100, "page": page},
            )
            items.extend(page_items)
            if len(page_items) < 100:
                break
        return items


def parse_github_datetime(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def parse_cli_datetime(value: str) -> datetime:
    if "T" not in value:
        return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def resolve_token(explicit_token: str | None) -> str | None:
    if explicit_token:
        return explicit_token
    if os.getenv("GITHUB_TOKEN"):
        return os.environ["GITHUB_TOKEN"]

    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None

    token = result.stdout.strip()
    return token or None


def issue_created_at(issue: dict[str, Any]) -> datetime:
    return parse_github_datetime(issue["created_at"])


def issue_updated_at(issue: dict[str, Any]) -> datetime:
    return parse_github_datetime(issue["updated_at"])


def issue_labels(issue: dict[str, Any]) -> list[str]:
    return sorted(label["name"] for label in issue.get("labels", []))


def issue_assignees(issue: dict[str, Any]) -> list[str]:
    return sorted(assignee["login"] for assignee in issue.get("assignees", []))


def actor_login(item: dict[str, Any]) -> str:
    actor = item.get("actor") or item.get("user") or {}
    login = actor.get("login")
    return f"@{login}" if login else "unknown actor"


def label_name(item: dict[str, Any]) -> str:
    label = item.get("label") or {}
    return label.get("name", "unknown")


def assignee_login(item: dict[str, Any]) -> str:
    assignee = item.get("assignee") or {}
    login = assignee.get("login")
    return f"@{login}" if login else "unknown assignee"


def source_ref(item: dict[str, Any]) -> str | None:
    source = item.get("source") or {}
    issue = source.get("issue") or {}
    if issue.get("html_url") and issue.get("number"):
        return f"[#{issue['number']}]({issue['html_url']})"
    if source.get("html_url") and source.get("number"):
        return f"[#{source['number']}]({source['html_url']})"
    return None


def summarize_timeline_item(item: dict[str, Any]) -> str | None:
    event = item.get("event")
    actor = actor_login(item)

    if not event and item.get("body") is not None:
        return f"comment by {actor}"
    if event == "commented":
        return f"comment by {actor}"
    if event == "labeled":
        return f"label `{label_name(item)}` added by {actor}"
    if event == "unlabeled":
        return f"label `{label_name(item)}` removed by {actor}"
    if event == "assigned":
        return f"{assignee_login(item)} assigned by {actor}"
    if event == "unassigned":
        return f"{assignee_login(item)} unassigned by {actor}"
    if event == "closed":
        return f"closed by {actor}"
    if event == "reopened":
        return f"reopened by {actor}"
    if event == "renamed":
        rename = item.get("rename") or {}
        from_title = rename.get("from")
        to_title = rename.get("to")
        if from_title and to_title:
            return f"renamed by {actor}: `{from_title}` -> `{to_title}`"
        return f"renamed by {actor}"
    if event in {"connected", "disconnected", "cross-referenced"}:
        ref = source_ref(item)
        if ref:
            return f"{event} {ref} by {actor}"
        return f"{event} by {actor}"
    if event == "marked_as_duplicate":
        return f"marked as duplicate by {actor}"
    if event == "unmarked_as_duplicate":
        return f"unmarked as duplicate by {actor}"

    # Skip noisy or low-signal events in the weekly summary.
    if event in {
        "mentioned",
        "subscribed",
        "referenced",
        "pinned",
        "unpinned",
        "locked",
        "unlocked",
    }:
        return None

    if event:
        return f"{event.replace('_', ' ')} by {actor}"
    return None


def timeline_item_datetime(item: dict[str, Any]) -> datetime | None:
    value = item.get("created_at") or item.get("updated_at") or item.get("submitted_at")
    if not value:
        return None
    return parse_github_datetime(value)


def recent_activity(
    client: GitHubClient,
    repo: str,
    issue: dict[str, Any],
    window: ReportWindow,
) -> list[str]:
    activity: list[str] = []
    for item in client.issue_timeline(repo, issue["number"]):
        item_at = timeline_item_datetime(item)
        if not item_at or not (window.since <= item_at <= window.until):
            continue
        summary = summarize_timeline_item(item)
        if summary:
            activity.append(summary)

    if not activity and window.since <= issue_updated_at(issue) <= window.until:
        activity.append("issue metadata or body updated")

    return activity


def dedupe_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[int] = set()
    deduped: list[dict[str, Any]] = []
    for issue in issues:
        number = issue["number"]
        if number in seen:
            continue
        seen.add(number)
        deduped.append(issue)
    return deduped


def fetch_report_data(
    client: GitHubClient,
    repo: str,
    window: ReportWindow,
) -> dict[str, Any]:
    base = f"repo:{repo} is:issue"
    created_query = f"{base} created:>={window.since_date}"
    updated_query = f"{base} updated:>={window.since_date}"

    created_candidates = client.search_issues(created_query)
    updated_candidates = client.search_issues(updated_query)

    new_issues = [
        issue
        for issue in created_candidates
        if window.since <= issue_created_at(issue) <= window.until
    ]
    updated_existing = [
        issue
        for issue in updated_candidates
        if issue_created_at(issue) < window.since
        and window.since <= issue_updated_at(issue) <= window.until
    ]

    needs_triage = client.search_issues(f"{base} is:open label:needs-triage")
    stale_needs_info = [
        issue
        for issue in client.search_issues(f"{base} is:open label:needs-info")
        if issue_updated_at(issue) < window.since
    ]
    unassigned_open = client.search_issues(f"{base} is:open no:assignee")

    updated_activity = {
        issue["number"]: recent_activity(client, repo, issue, window)
        for issue in updated_existing
    }

    return {
        "new_issues": sorted(new_issues, key=issue_created_at, reverse=True),
        "updated_existing": sorted(
            updated_existing,
            key=issue_updated_at,
            reverse=True,
        ),
        "updated_activity": updated_activity,
        "needs_triage": sorted(
            dedupe_issues(needs_triage),
            key=issue_updated_at,
            reverse=True,
        ),
        "stale_needs_info": sorted(
            dedupe_issues(stale_needs_info),
            key=issue_updated_at,
        ),
        "unassigned_open": sorted(
            dedupe_issues(unassigned_open),
            key=issue_updated_at,
        ),
    }


def issue_link(issue: dict[str, Any]) -> str:
    title = issue["title"].replace("\n", " ").strip()
    return f"[#{issue['number']} {title}]({issue['html_url']})"


def format_names(names: list[str]) -> str:
    if not names:
        return "none"
    return ", ".join(f"`{name}`" for name in names)


def issue_summary(issue: dict[str, Any], date_label: str) -> str:
    labels = format_names(issue_labels(issue))
    assignees = format_names(issue_assignees(issue))
    author = issue.get("user", {}).get("login", "unknown")
    updated = issue_updated_at(issue).strftime("%Y-%m-%d")
    if date_label == "opened":
        date_text = f"opened {issue_created_at(issue):%Y-%m-%d} by @{author}"
    elif date_label == "updated":
        date_text = f"updated {issue_updated_at(issue):%Y-%m-%d}; opened by @{author}"
    else:
        date_text = f"last touched {issue_updated_at(issue):%Y-%m-%d}"

    return (
        f"- {issue_link(issue)} - {date_text}; state: `{issue['state']}`; "
        f"labels: {labels}; assignees: {assignees}; last updated: {updated}"
    )


def append_issue_list(
    lines: list[str],
    issues: list[dict[str, Any]],
    date_label: str,
) -> None:
    if not issues:
        lines.append("_None._")
        lines.append("")
        return

    for issue in issues:
        lines.append(issue_summary(issue, date_label))
    lines.append("")


def append_updated_issues(
    lines: list[str],
    issues: list[dict[str, Any]],
    activity_by_number: dict[int, list[str]],
) -> None:
    if not issues:
        lines.append("_None._")
        lines.append("")
        return

    for issue in issues:
        lines.append(issue_summary(issue, "updated"))
        activity = activity_by_number.get(issue["number"], [])
        if activity:
            visible_activity = activity[:MAX_ACTIVITY_ITEMS]
            lines.append(f"  - Activity: {'; '.join(visible_activity)}")
            if len(activity) > MAX_ACTIVITY_ITEMS:
                hidden_count = len(activity) - MAX_ACTIVITY_ITEMS
                lines.append(f"  - Activity omitted: {hidden_count} more events")
    lines.append("")


def search_url(repo: str, query: str) -> str:
    return f"https://github.com/{repo}/issues?q={quote_plus(query)}"


def render_report(repo: str, window: ReportWindow, data: dict[str, Any]) -> str:
    base = f"repo:{repo} is:issue"
    needs_triage_query = f"{base} is:open label:needs-triage"
    stale_needs_info_query = (
        f"{base} is:open label:needs-info updated:<{window.since_date}"
    )
    unassigned_query = f"{base} is:open no:assignee"

    lines = [
        "# FOC Problems Weekly Activity",
        "",
        f"Repository: [{repo}](https://github.com/{repo})",
        f"Window: `{window.since:%Y-%m-%d %H:%M UTC}` to "
        f"`{window.until:%Y-%m-%d %H:%M UTC}`",
        "",
        "## Summary",
        "",
        f"- New reports: {len(data['new_issues'])}",
        f"- Existing reports updated: {len(data['updated_existing'])}",
        f"- Open `needs-triage`: {len(data['needs_triage'])}",
        f"- Stale open `needs-info`: {len(data['stale_needs_info'])}",
        f"- Open unassigned reports: {len(data['unassigned_open'])}",
        "",
        "## New Reports",
        "",
    ]

    append_issue_list(lines, data["new_issues"], "opened")

    lines.extend(["## Updated Existing Reports", ""])
    append_updated_issues(
        lines,
        data["updated_existing"],
        data["updated_activity"],
    )

    lines.extend(
        [
            "## Needs Attention",
            "",
            "### Open `needs-triage`",
            "",
            f"Query: [{needs_triage_query}]({search_url(repo, needs_triage_query)})",
            "",
        ]
    )
    append_issue_list(lines, data["needs_triage"], "updated")

    lines.extend(
        [
            "### Stale Open `needs-info`",
            "",
            f"Query: [{stale_needs_info_query}]"
            f"({search_url(repo, stale_needs_info_query)})",
            "",
        ]
    )
    append_issue_list(lines, data["stale_needs_info"], "updated")

    lines.extend(
        [
            "### Open Unassigned Reports",
            "",
            f"Query: [{unassigned_query}]({search_url(repo, unassigned_query)})",
            "",
        ]
    )
    append_issue_list(lines, data["unassigned_open"], "updated")

    return "\n".join(lines).rstrip() + "\n"


def build_window(args: argparse.Namespace) -> ReportWindow:
    until = parse_cli_datetime(args.until) if args.until else datetime.now(timezone.utc)
    since = (
        parse_cli_datetime(args.since)
        if args.since
        else until - timedelta(days=args.days)
    )
    if since >= until:
        raise ValueError("--since must be before --until")
    return ReportWindow(since=since, until=until)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a Markdown report of foc-problems weekly activity."
    )
    parser.add_argument(
        "--repo",
        default=DEFAULT_REPO,
        help=f"Repository to report on (default: {DEFAULT_REPO})",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_DAYS,
        help=f"Look back this many days when --since is not set (default: {DEFAULT_DAYS})",
    )
    parser.add_argument(
        "--since",
        help="Start time in UTC, as YYYY-MM-DD or ISO-8601. Overrides --days.",
    )
    parser.add_argument(
        "--until",
        help="End time in UTC, as YYYY-MM-DD or ISO-8601 (default: now).",
    )
    parser.add_argument(
        "--token",
        help="GitHub token. Defaults to GITHUB_TOKEN or `gh auth token`.",
    )
    parser.add_argument("--output", "-o", help="Write Markdown report to this file.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    token = resolve_token(args.token)
    window = build_window(args)
    client = GitHubClient(token)

    data = fetch_report_data(client, args.repo, window)
    report = render_report(args.repo, window, data)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as file:
            file.write(report)
    else:
        print(report, end="")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
