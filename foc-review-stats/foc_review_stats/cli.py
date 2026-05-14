#!/usr/bin/env python3
"""CLI for foc-review-stats."""

from __future__ import annotations

import argparse
import os
import sys
import tomllib
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from foc_review_stats import github, stats
from foc_review_stats.render import RENDERERS


CONFIG_NAME = "team.toml"


def _load_config() -> dict:
    """Load team.toml from the tool's root directory."""
    config_path = Path(__file__).resolve().parent.parent / CONFIG_NAME
    if not config_path.exists():
        print(f"Error: missing config {config_path}", file=sys.stderr)
        sys.exit(2)
    with config_path.open("rb") as f:
        return tomllib.load(f)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Report PR authorship and review counts across configured GitHub "
            "orgs and repos. Edit team.toml to change scope or silence "
            "out-of-scope contributors."
        )
    )
    p.add_argument(
        "--since",
        help="ISO date (YYYY-MM-DD). Defaults to --weeks weeks before today.",
    )
    p.add_argument(
        "--weeks", type=int, default=6, help="Window length in weeks (default 6)."
    )
    p.add_argument(
        "--top",
        type=int,
        default=3,
        help="How many top reviewers/reviewees to list per contributor (default 3).",
    )
    p.add_argument(
        "--format",
        choices=list(RENDERERS),
        default="text",
        help="Output format (default text). html cells are shaded by Rev/PR ratio.",
    )
    p.add_argument(
        "--pushed-buffer-weeks",
        type=int,
        default=6,
        help=(
            "When discovering org repos, include those pushed within "
            "(since - this many weeks). Larger = more dormant repos included. "
            "Default 6."
        ),
    )
    p.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Parallel fetch workers (default 8).",
    )
    p.add_argument(
        "--token", help="GitHub token (or set GITHUB_TOKEN). Needs read:org, repo."
    )
    p.add_argument(
        "-o", "--output", help="Write to this file instead of stdout."
    )
    p.add_argument(
        "-q", "--quiet", action="store_true", help="Suppress progress output."
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)

    token = args.token or os.environ.get("GITHUB_TOKEN")
    if not token:
        print("Error: set GITHUB_TOKEN or pass --token", file=sys.stderr)
        sys.exit(1)

    config = _load_config()
    scope = config.get("scope", {})
    team_cfg = config.get("team", {})
    orgs: list[str] = scope.get("orgs", [])
    extra_repos: list[str] = scope.get("extra_repos", [])
    github_teams: list[str] = team_cfg.get("github_teams", [])
    extra_members: list[str] = team_cfg.get("extra_members", [])
    ignored_lower = {
        l.lower() for l in config.get("ignored", {}).get("logins", [])
    }

    since_date = (
        date.fromisoformat(args.since)
        if args.since
        else (datetime.now(timezone.utc).date() - timedelta(weeks=args.weeks))
    )
    since_iso = since_date.isoformat() + "T00:00:00Z"
    pushed_since = (since_date - timedelta(weeks=args.pushed_buffer_weeks)).isoformat()

    session = github.make_session(token)

    in_scope_lower: set[str] = set()
    if github_teams or extra_members:
        if not args.quiet and github_teams:
            print(
                f"Resolving {len(github_teams)} GitHub team(s)...", file=sys.stderr
            )
        for qslug in github_teams:
            members = github.list_team_members(session, qslug)
            if not args.quiet:
                print(f"  {qslug}: {len(members)} members", file=sys.stderr)
            in_scope_lower.update(m.lower() for m in members)
        in_scope_lower.update(m.lower() for m in extra_members)
        in_scope_lower -= ignored_lower
        if not args.quiet:
            print(
                f"In-scope contributors: {len(in_scope_lower)}", file=sys.stderr
            )

    if not args.quiet:
        print(
            f"Discovering repos (pushed >= {pushed_since}, non-archived)...",
            file=sys.stderr,
        )

    repos: set[str] = set(extra_repos)
    for org in orgs:
        org_repos = github.list_org_repos(session, org, pushed_since)
        if not args.quiet:
            print(f"  {org}: {len(org_repos)} active repos", file=sys.stderr)
        repos.update(org_repos)
    repo_list = sorted(repos)

    if not args.quiet:
        print(f"Window: PRs created since {since_date}", file=sys.stderr)
        print(
            f"Repos: {len(repo_list)} (workers={args.workers})", file=sys.stderr
        )

    all_prs: list[dict] = []
    completed = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {
            ex.submit(github.fetch_repo_prs, session, r, since_iso): r
            for r in repo_list
        }
        for fut in as_completed(futures):
            repo = futures[fut]
            completed += 1
            try:
                all_prs.extend(fut.result())
            except Exception as e:
                print(f"  ERR {repo}: {e}", file=sys.stderr)
            if not args.quiet and completed % 25 == 0:
                print(
                    f"  ...{completed}/{len(repo_list)}", file=sys.stderr
                )

    agg = stats.aggregate(all_prs, ignored_lower, in_scope_lower or None)

    if not args.quiet:
        print(
            f"Fetching display names for {len(agg.logins)} contributors...",
            file=sys.stderr,
        )
    names = github.fetch_display_names(session, sorted(agg.logins))

    renderer = RENDERERS[args.format]
    output = renderer(agg, names, since_date.isoformat(), args.top)

    if args.output:
        Path(args.output).write_text(output + "\n", encoding="utf-8")
        if not args.quiet:
            print(f"Wrote {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(output + "\n")


if __name__ == "__main__":
    main()
