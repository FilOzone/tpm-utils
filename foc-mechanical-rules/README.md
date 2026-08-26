# foc-mechanical-rules

Scripted judgment-free enforcement of a growing subset of the [FOC board rules](../foc-board-rules/README.md).

Some board rules are pure functions of observable state (an unassigned PR should be assigned to its author, a merged PR should move to Done) with no human judgment involved. Rather than spend an LLM sweep's budget re-deriving these every time, this tool applies them directly and leaves the sweep to focus on the rules that actually need judgment. See [future-ideas.md](../foc-board-rules/future-ideas.md#move-the-mechanical-rules-out-of-the-llm-entirely) for the motivation.

## Design

Each rule targets a single board field (assignee, status, cycle theme, ...) and is implemented as a `Rule` subclass in `foc_mechanical_rules/rules/`:

- `select(session)` — find candidate board items via a targeted board query
- `apply_one(session, item, dry_run=..., mutation_log=...)` — decide what to do with one item, returning an `ActionResult` (`applied` / `skipped` / `flagged` / `error`). It may mutate immediately and return `applied`, or return `pending` to have the write batched (see below and "API call pattern per rule")
- `mutate_pending(session, pending)` — optional; only needed if `apply_one` ever returns `pending`. Executes every pending mutation from the run, ideally batched, and returns one finished result per input

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
| [R-FC-014](../foc-board-rules/field-completeness.md#r-fc-014-recently-completed-items-without-a-cycle-get-the-current-cycle) | cycle | Issues/PRs moved to Done and updated in the last 3 days with no Cycle get the current cycle (same guard against re-adding a human-cleared cycle as R-FC-012) |
| [R-PR-010](../foc-board-rules/pr-hygiene.md#r-pr-010-triage-prs-should-be-routed-to-the-correct-status) | status | PRs in Triage are routed to In Progress / Todo / Approved by reviewer / Awaiting review per the [PR status determination table](../foc-board-rules/pr-status-table.md), unless GitHub's real Status-field history shows a human explicitly moved the PR back to Triage |

## API call pattern per rule

Board size (~180 open items and growing) makes it easy for a rule to accidentally turn an O(1)-per-run cost into an O(items) one. Four conventions keep that in check, and every rule should follow them:

1. **`select()` issues exactly one board query**, paginated via `list_items`'s cursor — never a query per candidate.
2. **Anything that's the same for the whole run (e.g. "what's the current cycle?") is resolved once and memoized** on the rule instance (see `CycleRule`/`PastCycleRule`'s `_resolve*` methods), not refetched in every `apply_one` call.
3. **Mutations pass the item's node ID** (`item.get("_node_id")` — `list_items` always includes it, regardless of the requested `fields`), not an `"owner/repo#number"` ref. `github_projects_client`'s `set_field_value`/`set_field_value_bulk` silently does an extra `get_item` read per plain ref to resolve it to a node ID; a node ID skips that lookup entirely and also gets its `old_value` from a batched API read instead of whatever `select()` saw earlier (which can be stale by the time the mutation runs).
4. **When many items would get the same write, batch the mutation.** `apply_one` can return `status="pending"` (with `node_id` set) instead of mutating immediately; `Rule.run()` collects every "pending" result across the whole rule and calls the rule's `mutate_pending(session, pending)` once at the end, so the rule itself decides how to batch (see `_CycleFieldRule.mutate_pending` in `rules/cycle.py`, which groups by target value and calls `set_field_value_bulk` — 25 items per GraphQL request instead of 1). A rule whose writes are cheap or heterogeneous enough that batching isn't worth it can just keep mutating inline in `apply_one` and return "applied" directly, like `AssigneeRule` does — `mutate_pending` only needs implementing if `apply_one` ever returns "pending".

| Rule | `select()` (once per run) | Per-run, memoized | Per-item reads | Writes |
| --- | --- | --- | --- | --- |
| R-PR-001 (assignee) | 1 paginated board query | — | 1 REST `GET` (PR metadata) per candidate; **+1 REST `GET`** (issue events, paginated) unless skipped as a bot author | 1 REST `POST` per applied item (not batched — see gap below) |
| R-FC-012 (cycle) | 1 paginated board query | 1 GraphQL query (iterations) | none | Batched: all applied items in the run share 1 GraphQL mutation per 25 items (`_CycleFieldRule.mutate_pending`) |
| R-FC-013 (cycle) | 1 paginated board query (Cycle field included, so no separate read is needed to know an item's current cycle) | 1 GraphQL query (iterations, shared helper with R-FC-012) | none | Batched, same mechanism as R-FC-012 (via the shared `_CycleFieldRule.mutate_pending`) |
| R-FC-014 (cycle) | 1 paginated board query (Done items only, same 3-day window as R-FC-012) | 1 GraphQL query (iterations, shared helper with R-FC-012) | none | Batched, same mechanism as R-FC-012 (`DoneCycleRule` subclasses `CycleRule`, overriding only the `_STATUS_FILTER` class attribute) |
| R-PR-010 (status) | 1 paginated board query (Triage items only) | — | 1 GraphQL query per candidate (`get_pr_review_context`: draft/author/commits/reviews/reviewRequests/comments/status history in one round trip); **+1 REST `GET`** (collaborator permission) per unique reviewer login with a qualifying review, cached per (owner, repo, login) for the run | Batched: all applied items grouped by target status, 1 GraphQL mutation per 25 items per group (same `mutate_pending` pattern as `_CycleFieldRule`) |

**Known gap, not yet worth fixing:** R-PR-001's 1-2 REST reads per candidate PR are real per-item calls with no batched equivalent used today, unlike the two cycle rules. At current volume (dozens of candidates per hourly run, most REST GETs) it's well within GitHub's rate limits and not worth the complexity, but if candidate volume grows a lot, `github_projects_client`'s `nodes(ids: [ID!]!)` batching pattern (used by `set_field_value_bulk`'s old-value fetch) generalizes: a GraphQL `nodes()` query keyed by PR node IDs could fetch author + merge state for many PRs in one call, cutting the metadata `GET` to near-zero; issue-events (used only to detect a human `unassigned` event) would need a similar `timelineItems` batch to fully close the gap.

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
