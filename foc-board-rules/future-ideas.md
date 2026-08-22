# Future Ideas

Ideas for improving the FOC board tooling, collected during rule application sessions.

## Move the mechanical rules out of the LLM entirely

**Status: In progress.** [`foc-mechanical-rules`](../foc-mechanical-rules/) now runs hourly via GitHub Actions: R-PR-001 (unassigned PR -> author), R-FC-012 (recently-active item with no Cycle -> current cycle), and R-FC-013 (open item in a past cycle -> current cycle). The rule-per-field, decision-table design is meant to grow: R-PR-002/003/004 (dependabot/release-PR theme+status) and R-PR-008/009 (merged/closed -> Done) are the natural next slice, following the same `Rule` pattern (`select` + `apply_one`, registered in `registry.py`).

**New sub-problem this surfaced:** rules that need their own mutation history (see [`foc-mechanical-rules`'s "Mutation log" section](../foc-mechanical-rules/README.md#mutation-log) for why) currently get it persisted via GitHub Actions cache, which isn't a truly durable store (eviction after ~7 days unused, no cross-repo/cross-workflow access). That's an acceptable v1 tradeoff since the library itself doesn't assume any particular persistence mechanism — only the CLI/workflow-level wiring would need to change. If more rules end up depending on this history, or cache eviction ever causes a visible miss, worth moving it somewhere durable: a small persisted store the REST API server owns, for example.

Roughly 60% of the 2026-07-07 sweep's ~395 mutations (dependabot theme/status/cycle via R-PR-002/003 and R-FC-006, release-PR moves via R-PR-004, merged/closed to Done via R-PR-008/009) are pure functions of observable state with zero judgment. A small script (cron job, GitHub Action, or an endpoint on the existing REST server) could run these hourly. The LLM sweep would then start from a clean board and spend its entire budget on the judgment calls (R-PR-006 routing, staleness, flag triage), which is where it actually adds value.

**Spec already exists:** [pr-status-table.md](pr-status-table.md) defines the routing logic as a pure function (inputs in, target status out) with regression cases; the mechanical subset (rows 1-2 plus R-PR-008/009) is the natural first slice to script.

**Consistency note:** this matches the repo tenet of retiring custom LLM-driven capability when a simpler tool suffices. It should still log old → new values to the audit log so sweep reports stay complete.

**Triggered by:** agent feedback after the 2026-07-07 full sweep (~395 mutations across 6 stages).

## ~~Batch mutations in foc-mechanical-rules~~ — Solved

**Status: Done.** `github_projects_client`'s `set_field_value_bulk` already batched GraphQL mutations 25-at-a-time via aliased queries, but every rule called `set_field_value`, a thin wrapper that always passed a 1-item list, so the batching path never actually batched anything. A live R-FC-013 dry-run against the real board (2026-08-22) found 179 items needing a mutation; at 1 GraphQL request per item that's 179 round trips in one run, versus ~8 batched.

**Fix:** `apply_one` can now return `status="pending"` (with `node_id` set) instead of mutating immediately; `Rule.run()` collects every "pending" result across the whole rule and calls the rule's `mutate_pending(session, pending)` once at the end. `CycleRule` (R-FC-012) and `PastCycleRule` (R-FC-013) share this via a new `_CycleFieldRule` base class, which groups pending mutations by target value and batches each group through `set_field_value_bulk`. `AssigneeRule` (R-PR-001) is untouched — it never returns "pending", so `mutate_pending` is never called for it; see README.md's "API call pattern per rule" section for the current shape.

## Sweep journal for incremental sweeps

Each sweep re-derives the whole board from scratch. Persist the final item-state snapshot at the end of each sweep (one JSON file per sweep, ~200 bytes/item: ref, status, cycle, theme, assignee, board `updated`, GitHub `updatedAt`, flags raised). The next sweep can then run incrementally: only items whose GitHub/board `updated` changed since the snapshot need evaluation.

**Second benefit, regression detection:** the journal records what was flagged last sweep. If an item was flagged and a human dismissed the flag (no state change), the next sweep can skip re-flagging it instead of re-litigating. Today only R-SL-008's comment-check guidance protects against re-flagging things a human consciously left alone.

**Open questions:** where snapshots live (repo, `$SWEEP` archive dir, or served by the REST server), and how to avoid trusting a stale snapshot after board schema changes.

**Triggered by:** agent feedback after the 2026-07-07 full sweep.

## Augmented PR metadata endpoint in REST API

Add a REST API endpoint (or option on `GET .../items`) that returns GitHub PR metadata (author, isDraft, reviewDecision, reviewRequests) alongside board field data, so the agent doesn't need to make separate `gh pr list` calls per repo.

**Why it would help:** In the first real sweep (2026-05-04), the `gh pr list` calls with full `reviews` bodies consumed thousands of context lines — mostly for PRs not on the board (e.g., curio has 15+ open PRs but only 1 on the board). This caused scanning errors, missed items, and incomplete follow-through on R-PR-006 candidates. The two-phase approach (general behavior rule 6) mitigates this, but the REST API could do even better:
- **Filter to board PRs only.** The server knows which items are PRs and which repos they're in. It could query GitHub for just those PRs, not every open PR in the repo.
- **Return normalized summaries.** Instead of raw review bodies, return compact fields: `isDraft`, `author`, `reviewDecision`, `reviewRequests` (names only), and optionally `lastCommitDate` / `lastHumanReviewDate` for R-PR-006 timestamp comparisons.
- **Eliminate cross-referencing.** The agent currently has to join board data with GitHub data across 70+ items via `jq`. The server could return a single unified view.

**Estimated impact:** Would replace ~10 parallel `gh pr list` calls + ~5 targeted `gh pr view` calls with a single API call, and eliminate the most error-prone step of the sweep (cross-referencing two data sources across 70 items).

**Update (2026-07-09, post-sweep feedback):** still the single highest-leverage server change. Concretely: an `enrich=pr` query parameter on `GET .../items` that adds `isDraft`, `reviewDecision`, `author`, `reviewRequests`, `closedAt`, and `stateReason` to PR items. The server already holds a GitHub token. This would collapse Stage 1 from ~10 orchestrated tool calls to 2 and delete roughly a third of the playbook's prose (Phase 1 per-repo `gh pr list`, the Phase 2/2b batch jq join, and three pitfalls about parallel output interleaving exist solely because the board API lacks these fields). `closedAt`/`stateReason` would also remove the GraphQL side-trip Stage 5's R-FC-008 guard requires.

## ~~Async result refs for large query results~~ — Solved

**Status: Solved by the REST API architecture.** The REST API server is accessed via `curl`, so data goes directly to disk (`curl ... > $SWEEP/file.json`) without ever entering LLM context. This eliminates the MCP context-passthrough problem entirely — no async refs needed. The Write-tool workarounds that were documented in the sweep playbook are no longer necessary.

## Remove `format=compact` from the REST API

The compact columnar format (`format=compact`) was designed for MCP responses that land in LLM context, where token count matters. With the REST API, data goes to disk via curl and gets processed by jq — standard JSON is easier to work with (`jq '.items[]'` vs the columnar reconstruction dance) and disk space isn't a constraint. If no consumer depends on it, remove it from the API and the underlying `formats.py` module.

**Triggered by:** Reviewing the value of each feature against GitHub's own tooling (project tenet). The compact format was a context-window optimization that no longer applies when data bypasses LLM context entirely.

## Remove `GET /fields/{name}/options` endpoint

`gh project field-list --format json` returns field names and option names cleanly. The `/fields/{name}/options` endpoint doesn't provide unique value over GitHub's own tooling. Per the [project tenet](../github-projects-client/README.md#project-tenet-prefer-github-supported-tools), it should be retired.

**Triggered by:** Comparing the endpoint against `gh project field-list` output — both return the same information, and the `gh` version is already available to any agent with CLI access.

## Expose built-in item properties in REST API list endpoint

The board REST API returns built-in properties like `updated_at` and `creator` on each item internally, but `GET .../items` only surfaces custom project fields (Status, Cycle Theme, etc.) and a few display fields (Repository, Id, Title). Expose `updated_at` and `creator` as requestable fields so reports like R-FC-010 (Dev Days Estimate gaps) can include "last updated" and "created by" without supplemental GitHub API calls.

**Triggered by:** Stage 6 (effort estimation gaps) wants to show when each item was last updated and who created it, but neither field is available from the API today.

