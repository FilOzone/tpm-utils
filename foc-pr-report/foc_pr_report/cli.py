#!/usr/bin/env python3
"""CLI: fetch FilOzone Project 14 and print Markdown workload table."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import requests

from foc_pr_report.foc_project14_client import (
    enrich_pull_items_with_submitted_reviewers,
    fetch_project_board_items_rest_filtered,
)
from foc_pr_report.report import (
    BASE_FILTER,
    aggregate_rows,
    render_full_markdown,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate Markdown table of FOC (Project 14) PR counts by person and status",
    )
    parser.add_argument(
        "--token",
        help="GitHub token (or set GITHUB_TOKEN)",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Write Markdown to this file (default: stdout)",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Less progress output from the GitHub client",
    )
    args = parser.parse_args()

    token = args.token or os.environ.get("GITHUB_TOKEN")
    if not token:
        print("Error: set GITHUB_TOKEN or pass --token", file=sys.stderr)
        sys.exit(1)

    session = requests.Session()
    session.headers.update(
        {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
    )

    items = fetch_project_board_items_rest_filtered(
        session,
        filter_query=BASE_FILTER,
        verbose=not args.quiet,
    )
    enrich_pull_items_with_submitted_reviewers(
        session,
        items,
        verbose=not args.quiet,
    )
    md = render_full_markdown(items, aggregate_rows(items))

    if args.output:
        Path(args.output).write_text(md, encoding="utf-8")
        if not args.quiet:
            print(f"Wrote {args.output}")
    else:
        sys.stdout.write(md)


if __name__ == "__main__":
    main()
