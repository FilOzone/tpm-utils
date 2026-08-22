#!/usr/bin/env python3
"""CLI: apply every registered mechanical rule to the FOC board."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from .github_api import FILOZ_ORG, PROJECT_NUMBER, build_session
from .mutation_log import MutationLog, read_tsv, write_tsv
from .registry import default_rules
from .runner import render_summary, run_all

# Default path for the persisted mutation log. Read at start, written at
# end. *How* this file survives between separate CLI invocations (e.g.
# hourly CI runs) is entirely up to whoever runs this command -- see
# README.md's "Mutation log" section. In CI that's GitHub Actions cache
# restoring/saving this same path; that's a workflow-file concern, not
# something this module needs to know about.
_DEFAULT_MUTATION_LOG_PATH = (
    Path(__file__).resolve().parent.parent / "state" / "mutations.tsv"
)


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
    parser.add_argument(
        "--mutation-log",
        default=str(_DEFAULT_MUTATION_LOG_PATH),
        help="Path to the persisted mutation-history TSV, read at start and "
        "written at end (default: %(default)s)",
    )
    parser.add_argument(
        "--rule",
        action="append",
        metavar="RULE_ID",
        help="Only run this rule (e.g. R-FC-013). Repeatable to run several. "
        "Default: run every registered rule.",
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

    if args.rule:
        known_ids = {rule.id for rule in rules}
        unknown = sorted(set(args.rule) - known_ids)
        if unknown:
            print(
                f"Error: unknown rule id(s): {', '.join(unknown)}. "
                f"Known rules: {', '.join(sorted(known_ids))}",
                file=sys.stderr,
            )
            sys.exit(1)
        rules = [rule for rule in rules if rule.id in args.rule]

    for rule in rules:
        rule.org = args.org
        rule.project_number = args.project_number

    mutation_log_path = Path(args.mutation_log)
    mutation_log = MutationLog(read_tsv(mutation_log_path))

    runs = run_all(session, rules, dry_run=args.dry_run, mutation_log=mutation_log)
    summary = render_summary(rules, runs)
    print(summary)

    if args.output:
        with open(args.output, "a", encoding="utf-8") as f:
            f.write(summary)

    if not args.dry_run:
        write_tsv(mutation_log_path, mutation_log.all())

    if any(r.status == "error" for run in runs for r in run.results):
        sys.exit(1)


if __name__ == "__main__":
    main()
