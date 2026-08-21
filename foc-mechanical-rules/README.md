# foc-mechanical-rules

Scripted judgment-free enforcement of a growing subset of the [FOC board rules](../foc-board-rules/README.md).

Some board rules are pure functions of observable state (an unassigned PR should be assigned to its author, a merged PR should move to Done) with no human judgment involved. Rather than spend an LLM sweep's budget re-deriving these every time, this tool applies them directly and leaves the sweep to focus on the rules that actually need judgment. See [future-ideas.md](../foc-board-rules/future-ideas.md#move-the-mechanical-rules-out-of-the-llm-entirely) for the motivation.

## Design

Each rule targets a single board field (assignee, status, cycle theme, ...) and is implemented as a `Rule` subclass in `foc_mechanical_rules/rules/`:

- `select(session)` — find candidate board items via a targeted board query
- `apply_one(session, item, dry_run=...)` — evaluate the rule against one item and (unless dry-run) mutate it, returning an `ActionResult` (`applied` / `skipped` / `flagged` / `error`)

Rules are registered in `registry.py`. Adding a new rule means adding a new module under `rules/` and one line in the registry — the runner, audit logging, and CLI are shared.

**The English rule description stays canonical in `foc-board-rules/*.md`.** Each rule module's docstring links back to its markdown section, and the markdown links back to the module, so the prose and the implementation can't silently drift apart. If you change what a rule does, update both.

Every `applied`, `flagged`, or `error` outcome is written to the shared [`action_log.jsonl`](../github-projects-client/action_log.jsonl) audit log used by LLM sweeps, so a sweep report stays complete even when some of the work happened here instead.

## Rules implemented

| Rule | Field | Description |
| --- | --- | --- |
| [R-PR-001](../foc-board-rules/pr-hygiene.md#r-pr-001-unassigned-prs-should-be-assigned-to-their-author) | assignee | Unassigned open PRs are assigned to their author (skipping bots, with a merged-release-PR carve-out, and skipping PRs where a human explicitly removed the assignee) |

## Usage

```bash
uv run foc-mechanical-rules --dry-run          # preview, no mutations
uv run foc-mechanical-rules                    # apply
uv run foc-mechanical-rules -o "$GITHUB_STEP_SUMMARY"
```

Requires a `GITHUB_TOKEN` (or `--token`) with `read:project` (board reads) and issue/PR write access (`repo` scope, or fine-grained `Issues: write` + `Pull requests: write`) on the blessed orgs. CI uses the org's `FILOZZY_CI_ADD_TO_PROJECT` secret (also used by [`add-issues-and-prs-to-fs-project-board.yml`](../.github/workflows/add-issues-and-prs-to-fs-project-board.yml)).

## Testing

```bash
uv sync --group dev
uv run pytest -m "not integration"
```
