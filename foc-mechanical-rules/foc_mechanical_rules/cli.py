#!/usr/bin/env python3
"""CLI: apply every registered mechanical rule to the FOC board."""

from __future__ import annotations

import argparse
import logging
import os
import sys

from .github_api import FILOZ_ORG, PROJECT_NUMBER, build_session
from .registry import default_rules
from .runner import render_summary, run_all


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply mechanical FOC board rules (e.g. R-PR-001 assignee).",
    )
    parser.add_argument("--token", help="GitHub token (or set GITHUB_TOKEN)")
    parser.add_argument(
        "--org", default=FILOZ_ORG, help=f"GitHub org (default: {FILOZ_ORG})"
    )
    parser.add_argument(
        "--project-number",
        type=int,
        default=PROJECT_NUMBER,
        help=f"Project number (default: {PROJECT_NUMBER})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Evaluate and report what would change, without mutating anything",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Write the Markdown summary to this file in addition to stdout "
        "(e.g. $GITHUB_STEP_SUMMARY)",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress per-item progress logging (only print the final summary)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(message)s",
        stream=sys.stderr,
    )

    token = args.token or os.environ.get("GITHUB_TOKEN")
    if not token:
        print("Error: --token or GITHUB_TOKEN is required", file=sys.stderr)
        sys.exit(1)

    session = build_session(token)
    rules = default_rules()
    for rule in rules:
        rule.org = args.org
        rule.project_number = args.project_number

    runs = run_all(session, rules, dry_run=args.dry_run)
    summary = render_summary(rules, runs)
    print(summary)

    if args.output:
        with open(args.output, "a", encoding="utf-8") as f:
            f.write(summary)

    if any(r.status == "error" for run in runs for r in run.results):
        sys.exit(1)


if __name__ == "__main__":
    main()
