"""Runs every registered rule and reports what happened."""

from __future__ import annotations

import re
from typing import List

import requests
from github_projects_client.audit_log import log_action

from .mutation_log import MutationLog
from .rule import Rule, RuleRun

CALLER = "foc-mechanical-rules"


def run_all(
    session: requests.Session,
    rules: List[Rule],
    *,
    dry_run: bool,
    mutation_log: MutationLog,
) -> List[RuleRun]:
    runs = []
    for rule in rules:
        run = rule.run(session, dry_run=dry_run, mutation_log=mutation_log)
        for result in run.results:
            if result.status not in ("applied", "flagged", "error"):
                continue
            log_action(
                caller=CALLER,
                endpoint=f"rule:{rule.id}",
                params={
                    "item_ref": result.item_ref,
                    "field": rule.field_name,
                    "dry_run": dry_run,
                },
                result=result.status,
                old_value=result.old_value or None,
                new_value=result.new_value or None,
                error=result.reason if result.status == "error" else None,
            )
        runs.append(run)
    return runs


_ITEM_REF_RE = re.compile(r"^([\w.-]+/[\w.-]+)#(\d+)$")


def _link_item_ref(item_ref: str) -> str:
    """Render `owner/repo#123` as a markdown link to the issue/PR on GitHub.

    GitHub's `/issues/{n}` URL resolves for both issues and PRs, so this
    doesn't need to know which one `item_ref` points to.
    """
    match = _ITEM_REF_RE.match(item_ref)
    if not match:
        return f"`{item_ref}`"
    repo, number = match.groups()
    return f"[`{item_ref}`](https://github.com/{repo}/issues/{number})"


def render_summary(rules: List[Rule], runs: List[RuleRun]) -> str:
    lines: List[str] = []
    for rule, run in zip(rules, runs):
        counts = run.counts()
        counts_str = (
            ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "no candidates"
        )
        lines.append(f"## {rule.id} ({rule.field_name}) — {counts_str}")
        lines.append(f"Rule: {rule.doc_url}")
        lines.append("")
        for result in run.results:
            if result.status == "skipped":
                continue
            detail = f"- {_link_item_ref(result.item_ref)} **{result.status}**"
            if result.old_value or result.new_value:
                detail += f": `{result.old_value}` -> `{result.new_value}`"
            if result.reason:
                detail += f" ({result.reason})"
            lines.append(detail)
        lines.append("")
    return "\n".join(lines)
