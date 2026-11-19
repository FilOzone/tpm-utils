#!/usr/bin/env python3
"""Post the review queue for active FOC release milestones to Slack."""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import requests

from foc_review_queue_github import GitHubQueueError, fetch_epic_candidates
from foc_review_queue_notion import DEFAULT_NOTION_DATA_SOURCE_ID, fetch_projects

USER_MAP = Path(__file__).with_name("gh_slack_users.json")
NEEDS_REVIEWER = ("unassigned", "")
SLACK_MESSAGE_SIZE = 3800


def timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def review_targets(pr):
    """Return pending reviewers, or a routing item if nobody has been requested."""
    if pr["state"] != "OPEN" or pr["isDraft"]:
        return []

    decision = pr["reviewDecision"]
    author = (pr.get("author") or {}).get("login", "").lower()
    pending = [
        reviewer
        for reviewer in pr["reviewers"]
        if reviewer["kind"] != "user" or reviewer["login"].lower() != author
    ]
    change_reviewers = {login.lower() for login in pr.get("changesRequestedBy", [])}
    rerequests = [
        reviewer
        for reviewer in pending
        if reviewer["kind"] == "user" and reviewer["login"].lower() in change_reviewers
    ]

    if decision == "APPROVED":
        # A blocking reviewer can still be explicitly asked to re-review.
        pending = rerequests
        if not pending:
            return []
    elif decision == "CHANGES_REQUESTED":
        last_change = timestamp(pr.get("lastChangesRequestedAt"))
        last_commit = timestamp(pr.get("lastCommitAt"))
        if not (last_change and last_commit and last_commit > last_change):
            # Other pending requests may predate unresolved feedback.
            pending = rerequests
            if not pending:
                return []
    elif not pending and decision is None and pr.get("latestReviewAt"):
        # Without a repository review decision, avoid asking for another reviewer
        # when a human review is at least as recent as the code.
        last_commit = timestamp(pr.get("lastCommitAt"))
        if not last_commit or timestamp(pr["latestReviewAt"]) >= last_commit:
            return []

    if pending:
        return [
            ((reviewer["kind"], reviewer["login"]), reviewer.get("requestedAt"))
            for reviewer in pending
        ]
    if pr.get("unresolvedReviewerRequests"):
        return []
    return [(NEEDS_REVIEWER, None)]


def collect_queue(session, projects, diagnostics):
    """Collect unique PRs with every path that makes each PR P1."""
    queue = {}
    epics = {}
    unknown_reviewers = set()
    incomplete = False
    for project in projects:
        for epic_url in project["epic_urls"]:
            if epic_url not in epics:
                try:
                    epics[epic_url] = fetch_epic_candidates(
                        session, epic_url, diagnostics=diagnostics
                    )
                except GitHubQueueError as exc:
                    incomplete = True
                    diagnostics.append(f"{epic_url}: {exc}")
                    epics[epic_url] = []

            for candidate in epics[epic_url]:
                pr = candidate["pr"]
                if (
                    pr.get("unresolvedReviewerRequests")
                    and pr["id"] not in unknown_reviewers
                ):
                    unknown_reviewers.add(pr["id"])
                    diagnostics.append(
                        f"{pr['url']}: GitHub did not identify every requested reviewer."
                    )
                targets = review_targets(pr)
                if not targets:
                    continue

                item = queue.setdefault(
                    pr["id"], {"pr": pr, "targets": targets, "paths": {}}
                )
                epic, ticket = candidate["epic"], candidate["ticket"]
                key = (project["url"], epic["url"], ticket["url"])
                item["paths"][key] = (project, epic, ticket)
    return queue, incomplete


def branch_key(repo, branch):
    name = (repo or {}).get("nameWithOwner")
    return (name.lower(), branch) if name and branch else None


def stack_parents(queue):
    heads = {}
    for pr_id, item in queue.items():
        pr = item["pr"]
        key = branch_key(pr.get("headRepository"), pr.get("headRefName"))
        if key:
            heads.setdefault(key, []).append(pr_id)

    parents = {}
    for pr_id, item in queue.items():
        pr = item["pr"]
        key = branch_key(pr.get("baseRepository"), pr.get("baseRefName"))
        candidates = [parent for parent in heads.get(key, []) if parent != pr_id]
        if len(candidates) == 1:
            parents[pr_id] = candidates[0]
    return parents


def wait_since(pr, requested_at):
    dates = [
        timestamp(value)
        for value in (requested_at, pr.get("readyForReviewAt"))
        if value
    ]
    if not requested_at:
        return None
    return max(dates)


def sorted_reviews(reviews, queue, parents):
    def order(pr_id):
        pr = queue[pr_id]["pr"]
        since = wait_since(pr, reviews[pr_id])
        return (since.timestamp() if since else float("inf"), pr["url"])

    remaining = set(reviews)
    while remaining:
        ready = [pr_id for pr_id in remaining if parents.get(pr_id) not in remaining]
        # A cycle or ambiguous stack should never prevent displaying the reviews.
        next_id = min(ready or remaining, key=order)
        remaining.remove(next_id)
        yield next_id


def escape(text):
    return (
        re.sub(r"\s+", " ", text)
        .strip()
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def link(url, label):
    return f"<{url}|{escape(label).replace('|', '¦')}>"


def pr_link(pr):
    repo = pr["repository"]["nameWithOwner"]
    number = pr["url"].rsplit("/", 1)[-1]
    return link(pr["url"], f"{repo}#{number}")


def render_queue(queue, user_map, diagnostic_count=0):
    coverage = (
        f"\nSource and routing notes: {diagnostic_count}. See the workflow log."
        if diagnostic_count
        else ""
    )
    if not queue:
        return [
            "*FOC-WG P1 review queue*\nNo reviews found on linked tickets." + coverage
        ]

    groups = {}
    for pr_id, item in queue.items():
        for target, requested_at in item["targets"]:
            groups.setdefault(target, {})[pr_id] = requested_at

    lines = [f"*FOC-WG P1 review queue* · {len(queue)} unique PR(s)" + coverage]
    parents = stack_parents(queue)

    for target in sorted(
        groups,
        key=lambda key: (key[0] != "user", key[0] == "unassigned", key[1].lower()),
    ):
        kind, login = target
        if kind == "user":
            slack_id = user_map.get(login.lower())
            who = f"<@{slack_id}>" if slack_id else f"@{escape(login)}"
        elif kind == "team":
            who = f"Team request · {escape(login)}"
        else:
            who = "Needs a reviewer"

        lines.append(f"\n*{who}*")
        for pr_id in sorted_reviews(groups[target], queue, parents):
            item = queue[pr_id]
            pr = item["pr"]
            title = escape(pr["title"])[:180]
            after = (
                f" · Review after {pr_link(queue[parents[pr_id]]['pr'])}"
                if pr_id in parents
                else ""
            )
            assignment = ""
            if kind == "unassigned":
                author = (pr.get("author") or {}).get("login")
                if author:
                    assignment = f" · Author: @{escape(author)}"
            since = wait_since(pr, groups[target][pr_id])
            wait = f" · Waiting since {since:%Y-%m-%d}" if since else ""
            lines.append(f"• {pr_link(pr)} · {title}{wait}{after}{assignment}")
            for project, epic, ticket in sorted(
                item["paths"].values(),
                key=lambda path: (path[0]["title"], path[1]["url"], path[2]["url"]),
            ):
                lines.append(
                    f"  {link(project['url'], project['title'][:120])}"
                    f" → {link(epic['url'], 'epic #' + epic['url'].rsplit('/', 1)[-1])}"
                    f" → {link(ticket['url'], ticket['title'][:120])}"
                )

    messages = []
    message = ""
    for line in lines:
        if message and len(message) + len(line) + 1 > SLACK_MESSAGE_SIZE:
            messages.append(message)
            message = "*FOC-WG P1 review queue (continued)*"
        message = f"{message}\n{line}" if message else line
    if message:
        messages.append(message)
    return messages


def load_user_map(path, *, summary_only=False):
    try:
        with path.open(encoding="utf-8") as file:
            values = json.load(file)
        if not isinstance(values, dict):
            raise ValueError("expected a JSON object")
    except (OSError, ValueError) as exc:
        warning = "Could not load Slack user mapping"
        print(f"{warning}." if summary_only else f"{warning}: {exc}", file=sys.stderr)
        return {}
    return {
        login.lower(): slack_id
        for login, slack_id in values.items()
        if isinstance(slack_id, str) and re.fullmatch(r"[UW][A-Z0-9]+", slack_id)
    }


def main():
    parser = argparse.ArgumentParser(
        description="Post the FOC-WG P1 review queue from Notion and GitHub"
    )
    parser.add_argument("--token", help="GitHub token (or set GITHUB_TOKEN)")
    parser.add_argument(
        "--notion-token", help="Notion connection token (or set NOTION_TOKEN)"
    )
    parser.add_argument(
        "--notion-data-source-id",
        default=DEFAULT_NOTION_DATA_SOURCE_ID,
        help="Notion data source ID for the release planning database",
    )
    parser.add_argument(
        "--webhook", help="Slack webhook URL (or set SLACK_WEBHOOK_URL)"
    )
    parser.add_argument("--user-map", type=Path, default=USER_MAP)
    parser.add_argument(
        "--dry-run", action="store_true", help="Print the queue without posting"
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Keep project and reviewer details out of command output",
    )
    args = parser.parse_args()

    github_token = args.token or os.getenv("GITHUB_TOKEN")
    notion_token = args.notion_token or os.getenv("NOTION_TOKEN")
    webhook = args.webhook or os.getenv("SLACK_WEBHOOK_URL")
    if not github_token:
        parser.error("Set GITHUB_TOKEN or pass --token.")
    if not notion_token:
        parser.error("Set NOTION_TOKEN or pass --notion-token.")
    if not args.dry_run and not webhook:
        parser.error("Set SLACK_WEBHOOK_URL or use --dry-run.")

    try:
        return run_notifier(args, github_token, notion_token, webhook)
    except Exception:
        if not args.summary_only:
            raise
        print(
            "Unexpected notifier error. Run a private preview for details.",
            file=sys.stderr,
        )
        return 1


def run_notifier(args, github_token, notion_token, webhook):
    with requests.Session() as notion, requests.Session() as github:
        notion.headers["Authorization"] = f"Bearer {notion_token}"
        github.headers["Authorization"] = f"Bearer {github_token}"
        try:
            projects, diagnostics = fetch_projects(notion, args.notion_data_source_id)
        except (RuntimeError, requests.RequestException, ValueError) as exc:
            if args.summary_only:
                status = (
                    exc.response.status_code
                    if (
                        isinstance(exc, requests.HTTPError) and exc.response is not None
                    )
                    else None
                )
                suffix = f" (HTTP {status})" if status else ""
                print(f"Could not load Notion projects{suffix}.", file=sys.stderr)
            else:
                print(f"Could not load Notion projects: {exc}", file=sys.stderr)
            return 1
        queue, incomplete = collect_queue(github, projects, diagnostics)

    if not args.summary_only:
        for diagnostic in diagnostics:
            print(f"Queue diagnostic: {diagnostic}", file=sys.stderr)

    if incomplete:
        print(
            "GitHub data is incomplete. No Slack message was posted.", file=sys.stderr
        )
        if not args.dry_run or args.summary_only:
            return 1

    if args.dry_run and args.summary_only:
        print(
            f"Dry run complete. Active milestones: {len(projects)}. "
            f"PRs waiting for review: {len(queue)}. Source and routing notes: {len(diagnostics)}."
        )
        return 0

    messages = render_queue(
        queue,
        load_user_map(args.user_map, summary_only=args.summary_only),
        len(diagnostics),
    )
    if args.dry_run:
        print("=== DRY RUN (incomplete) ===" if incomplete else "=== DRY RUN ===")
        print("\n\n".join(messages))
        return int(incomplete)

    for message in messages:
        try:
            response = requests.post(
                webhook,
                json={"text": message, "unfurl_links": False, "unfurl_media": False},
                timeout=30,
                allow_redirects=False,
            )
        except requests.RequestException:
            print("Could not reach Slack webhook.", file=sys.stderr)
            return 1
        if response.status_code != 200:
            print(
                f"Slack rejected the message (HTTP {response.status_code}).",
                file=sys.stderr,
            )
            return 1
    print(f"Posted the P1 review queue ({len(queue)} unique PRs).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
