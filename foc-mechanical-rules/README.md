# foc-mechanical-rules

Scripted judgment-free enforcement of a growing subset of the [FOC board rules](../foc-board-rules/README.md).

Some board rules are pure functions of observable state (an unassigned PR should be assigned to its author, a merged PR should move to Done) with no human judgment involved. Rather than spend an LLM sweep's budget re-deriving these every time, this tool applies them directly and leaves the sweep to focus on the rules that actually need judgment. See [future-ideas.md](../foc-board-rules/future-ideas.md#move-the-mechanical-rules-out-of-the-llm-entirely) for the motivation.

## Design

Each rule targets a single board field (assignee, status, cycle theme, ...) and is implemented as a `Rule` subclass in `foc_mechanical_rules/rules/`:

- `select(session)` — find candidate board items via a targeted board query
- `apply_one(session, item, dry_run=..., mutation_log=...)` — evaluate the rule against one item and (unless dry-run) mutate it, returning an `ActionResult` (`applied` / `skipped` / `flagged` / `error`)

Rules are registered in `registry.py`. Adding a new rule means adding a new module under `rules/` and one line in the registry — the runner, audit logging, and CLI are shared.

**The English rule description stays canonical in `foc-board-rules/*.md`.** Each rule module's docstring links back to its markdown section, and the markdown links back to the module, so the prose and the implementation can't silently drift apart. If you change what a rule does, update both.

Every `applied`, `flagged`, or `error` outcome is written to the shared [`action_log.jsonl`](../github-projects-client/action_log.jsonl) audit log used by LLM sweeps, so a sweep report stays complete even when some of the work happened here instead.

## Mutation log

Some rules need to know what this tool has already done to an item — R-FC-012 (cycle) is the first example: it won't re-add a cycle it previously set if the item now has no cycle, because that's a human's deliberate signal to descope it, not something to silently override. R-FC-013 uses the same log the other direction: it won't re-move an item off a past cycle if this tool already moved it off that exact cycle once and the item is back there now — that's a human's deliberate signal to leave it, not something to fight. Getting that from GitHub directly isn't possible: GitHub has no change-history API for Projects v2 custom fields other than Status (confirmed by GraphQL schema introspection — `ProjectV2ItemStatusChangedEvent` is the only such timeline event that exists; a separate, similarly-named `IssueFieldChangedEvent` family turned out to belong to an unrelated "Issue Fields" GitHub feature and returned nothing when checked against a real item with a multi-cycle history).

So this tool keeps its own record instead, and treats it explicitly as an *input* to rules rather than an assumption baked into how they run: `mutation_log.py` defines `MutationLog`, an item -> mutations multimap (`for_item(item_ref)` for O(1) lookup, `record(...)` to append). The base `Rule.run()` builds one record per real (non-dry-run) `applied` outcome automatically and adds it to whatever `MutationLog` it's given; any rule's `apply_one` can read it back via `mutation_log.for_item(...)` (see `rules/cycle.py`). **It is not guaranteed comprehensive** — it only knows what was fed in plus what's happened this run — so a rule using it should treat a miss as "no known history," not as proof nothing happened.

Neither `mutation_log.py` nor any rule module knows or cares how the log survives between separate runs of the CLI — that's a runtime decision, made by whoever invokes `foc-mechanical-rules`, not something the library assumes. Today: `cli.py` reads a TSV file at start and writes it back at the end (`--mutation-log`, defaulting to `state/mutations.tsv`), and in CI that file is restored/saved across hourly runs via GitHub Actions cache (see the workflow file) — a cache is not truly durable (eviction after ~7 days unused), which is an acceptable v1 tradeoff; see `future-ideas.md` if it needs to move somewhere sturdier later. None of that is visible to a rule — it just gets handed a `MutationLog`.

## Rules implemented

| Rule | Field | Description |
| --- | --- | --- |
| [R-PR-001](../foc-board-rules/pr-hygiene.md#r-pr-001-unassigned-prs-should-be-assigned-to-their-author) | assignee | Unassigned open PRs are assigned to their author (skipping bots, with a merged-release-PR carve-out, and skipping PRs where a human explicitly removed the assignee) |
| [R-FC-012](../foc-board-rules/field-completeness.md#r-fc-012-recently-active-items-without-a-cycle-get-the-current-cycle) | cycle | Issues/PRs updated in the last 3 days with no Cycle get the current cycle, unless this tool previously set that item's Cycle to the current one and a human has since cleared it |
| [R-FC-013](../foc-board-rules/field-completeness.md#r-fc-013-open-items-in-a-past-cycle-should-move-to-the-current-cycle) | cycle | Open issues/PRs whose Cycle is a past iteration move to the current cycle, unless this tool previously moved that item off the same past cycle and a human has since moved it back |

## Usage

```bash
uv run foc-mechanical-rules --dry-run          # preview, no mutations
uv run foc-mechanical-rules                    # apply
uv run foc-mechanical-rules -o "$GITHUB_STEP_SUMMARY"
uv run foc-mechanical-rules --dry-run --rule R-FC-013                # only this rule
uv run foc-mechanical-rules --dry-run --rule R-FC-013 --rule R-PR-001  # or a few
```

Requires a `GITHUB_TOKEN` (or `--token`) with `read:project` (board reads) and issue/PR write access (`repo` scope, or fine-grained `Issues: write` + `Pull requests: write`) on the blessed orgs. CI uses the org's `FILOZZY_CI_ADD_TO_PROJECT` secret (also used by [`add-issues-and-prs-to-fs-project-board.yml`](../.github/workflows/add-issues-and-prs-to-fs-project-board.yml)).

## Testing

```bash
uv sync --group dev
uv run pytest -m "not integration"
```
