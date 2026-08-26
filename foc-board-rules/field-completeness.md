# Field Completeness Rules

Rules for ensuring board items have the right fields populated based on their status and type.

## Board fields

| Field | Type | Notes |
|---|---|---|
| Status | Single-select | 7 options (Triage → Done) |
| Assignees | People | GitHub assignees |
| Milestone | Milestone | From the item's repo |
| Cycle Theme | Text | Free-text grouping (e.g., "Dealbot", "SDK Changes") |
| Cycle | Iteration | Sprint/cycle iteration |
| Dev Days Estimate | Number | Estimated effort |
| Prio | Single-select | P1, P2, P3 |
| Owner | Text | DRI for the item |

## R-FC-001: In-flight and done items must have an assignee

**When:** An [active item](status-lifecycle.md#terminology) or recently-done item (per R-FC-008) has no assignee.
**Exclude:** Items with Cycle Theme "zOrganizing Item" (meta/tracking items), [external items](status-lifecycle.md#terminology) (assignees can't be set), and bot-created Done items (automated reports/releases with no human DRI — unassigned is fine).
**Action:** Determine the assignee using this priority order:
1. **PRs:** Assign to the PR author (per [R-PR-001](pr-hygiene.md#r-pr-001-unassigned-prs-should-be-assigned-to-their-author)). Skip if the author is a bot.
2. **Issues with linked PRs:** Assign to the assignee of the linked PR. Fetch the item via `GET .../items/{ref}` to find "Linked pull requests", then look up the PR's assignee.
3. **Issues without linked PRs:** Investigate the issue's comment stream and description for who is doing the work. Look for patterns like: who opened it, who is actively commenting with progress updates, who was mentioned as the DRI, who posted the closing comment.
4. **If still uncertain:** Propose an assignee with justification and flag for human confirmation. Do not leave it blank — always make a best-effort proposal.

**After assigning, verify it persisted.** The GitHub API silently succeeds even when the user lacks sufficient repo permissions (write/triage). If the inferred assignee is a contributor without write access (common on blessed-org repos), the assignment won't stick. Flag for human — the user may need elevated access or a different assignee.

**Why:** Every item that has progressed beyond Triage should have someone accountable. Unassigned in-flight items are a planning gap, and unassigned done items get missed in workload reporting.

## R-FC-002: In Progress items should have a Cycle Theme

**When:** An item has status "⌨️ In Progress" but no Cycle Theme.
**Action:** Flag for human review. Suggest a Cycle Theme based on the item's repository and title if possible.
**Why:** Cycle Theme is how the team groups related work for planning. Items without one fall through the cracks in cycle reviews.

## R-FC-003: All open issues should have a Milestone

**Status: paused (2026-08-19).** Do not flag Milestone gaps during sweeps until this note is removed — milestones can be ignored for now.

**When:** An **issue** on the board (any status except "🎉 Done") has no milestone set. Exclude items with Cycle Theme "zOrganizing Item" (meta/tracking items), [external items](status-lifecycle.md#terminology) (milestones can't be set), and **project notes** (draft items with no repository — milestones are a repo-level field and don't exist for notes).
**Action:** First, check if the issue has a parent issue (via `GET .../items/{ref}` — look for "Parent issue" field). If the parent has a milestone, inherit it. Otherwise, flag for human review, grouped by Cycle Theme or repository. Report the item's current status, assignee, and Cycle Theme to help the human decide.
**Scope:** Issues only. **Milestones on PRs are optional** — PRs often inherit their delivery context from the issue they close, and many repos don't milestone PRs at all.
**Why:** Every real issue should be tied to a delivery milestone so it's tracked against a timeline. Issues without milestones fall through the cracks during planning. Even Triage items benefit from early milestone assignment — it helps prioritize what to triage first.

## R-FC-004: Cycle Theme defaults by repository

**When:** An item has no Cycle Theme set.
**Action:** Infer the Cycle Theme from the item's repository and title:

**Note:** These defaults do not apply to dependabot PRs — those are always "Dependency Updates" per [R-PR-002](pr-hygiene.md#r-pr-002-dependabot-prs-should-have-cycle-theme-dependency-updates).

| Repository | Default Cycle Theme | Notes |
|---|---|---|
| `FilOzone/dealbot` | Dealbot | |
| `FilOzone/filecoin-pay-explorer` | Filecoin Pay Explorer | |
| `FilOzone/synapse-sdk` | SDK Changes | |
| `filecoin-project/filecoin-pin` | Filecoin Pin | |
| `filecoin-project/filecoin-pin-website` | Filecoin Pin | Website for filecoin-pin |
| `FilOzone/SessionKeyRegistry` | Contract Upgrade | |
| `FilOzone/filecoin-pay` | Filecoin Pay | |
| `FilOzone/pdp-explorer` | PDP Explorer | |
| `FilOzone/filecoin-cloud` | filecoin.cloud | |
| `filecoin-project/curio` | Curio Hardening | |
| `FilOzone/foc-observer` | Maintainer Experience | For now |
| `FilOzone/tpm-utils` | Maintainer Experience | Usually, but not always |
| `FilOzone/foc-devnet` | Maintainer Experience | Dev tooling |
| `FilOzone/filecoin-services` | Contract Upgrade | Often but not always — flag for human review |
| `FilOzone/early-repair` | GA Durability | |
| `FilOzone/pdp` | Contract Upgrade | |
| `FilOzone/security-triage` | Security | |
| `FilOzone/infra` | Other | Unless a better theme applies (see below) |
| `FilOzone/github-mgmt` | Maintainer Experience | GitHub org/project management tooling |
| `FilOzone/foc-gh` | Maintainer Experience | GitHub helper tooling (added 2026-07-07; confirm) |
| `filbeam/*` | filbeam | Anything in the `filbeam` GitHub org. |

For repositories not listed above, check the item title and description for context clues. In particular:
- **Docs**: If the title contains "docs" or "docs:" (e.g., `docs: add some details about...`) and no better product-specific theme applies, use "Docs". **Exception:** `FilOzone/infra` items keep their repo default ("Other") even when the title has a `docs:` prefix — the infra-repo rule wins over the generic Docs heuristic. The "Docs" theme is for product-facing documentation work, not infra-side docs. (Clarified 2026-06-29 after infra#275 `docs: address #112 review feedback` was incorrectly flagged as theme-ambiguous.)
- **infra** items that reference a specific product in the title or description (e.g., "dealbot" in the title) should inherit that product's Cycle Theme. Otherwise default to "Other" — including for `docs:`-prefixed PRs (see above).
- **Stacked PRs**: Check if the item's description or comments reference related PRs/issues. If it's stacked on or related to another item that already has a Cycle Theme, use the same theme.

If no reasonable inference can be made, **leave Cycle Theme blank** — do not invent a new Cycle Theme value, and do not propose adding a new value to the established list (even for high-volume new repos). It's fine for items to have no Cycle Theme. (Clarified 2026-08-19: a sweep should not treat unrecognized repos as a decision the human needs to make — just leave the field empty and move on.)

**Existing Cycle Theme values** (as of 2026-06-18):

> Contract Upgrade, Curio Hardening, Dealbot, Dependency Updates, Docs, filbeam, filecoin.cloud, Filecoin Pay, Filecoin Pay Explorer, Filecoin Pay Tools, Filecoin Pin, GA Durability, Maintainer Experience, Operational Readiness, Other, PDP Explorer, SDK Changes, Security, zOrganizing Item

**Never create a new Cycle Theme.** Always use one of the existing values above. If none fit, leave Cycle Theme blank per the no-inference guidance above — do not flag for human review just because no established value matches. **Capitalization matters** — `filbeam` (not `Fil Beam` or `Filbeam`) is the canonical spelling for CDN/bandwidth-rail work; flag any variant (this is a data-quality issue, not a no-inference case).

**Why:** Most items naturally belong to the Cycle Theme of their repository. Automating the obvious cases reduces manual triage work and keeps the board consistent. Using only established values prevents theme sprawl.

## R-FC-005: All PRs should have a Cycle Theme

**When:** A PR on the board (any status except "🎉 Done") has no Cycle Theme set.
**Action:** Apply [R-FC-004](#r-fc-004-cycle-theme-defaults-by-repository) to infer a Cycle Theme. If no inference can be made, leave it blank per R-FC-004's no-inference guidance — do not flag for human review.
**Why:** PRs represent concrete work. Every PR should be attributable to a theme so it shows up in cycle reviews and workload tracking. Unlike issues (which may be speculative), PRs are always real work in progress.

## R-FC-006: In-flight PRs without a cycle should be in the current cycle

**When:** A PR on the board has no Cycle set and is **actively in flight** — meaning its status is "⌨️ In Progress", "🔎 Awaiting review", or "✔️ Approved by reviewer". Also applies to **dependabot and release PRs in "🐱 Todo"** — these are known mechanical work items that will get done in the current cycle, not speculative backlog.
**Action:** Set the Cycle to the current active cycle. Use `gh project field-list` (with the org and project number from `get_board_context`) to find the current iteration.
**Scope:** Does **not** apply to non-bot Todo PRs or Triage PRs. Todo PRs from humans — especially those with future milestones (MX, M4.5) — are backlog items. Forcing them into the current cycle overstates what's actually being worked on. They'll get a cycle when they move to In Progress.
**Why:** PRs actively being worked on or reviewed should be visible in cycle planning. Dependabot and release PRs in Todo are different from human-authored Todo PRs — they represent known, bounded work that belongs in the current cycle for tracking purposes.

## R-FC-009: In-flight items in active milestones should have a cycle

**When:** An item (PR or issue) has a milestone that is currently active, has no Cycle set, and is **actively in flight** — meaning its status is "⌨️ In Progress", "🔎 Awaiting review", "✔️ Approved by reviewer", or "⌚️ Issue awaiting PR merge".
**Action:** Set the Cycle to the current active cycle. Use `gh project field-list` (with the org and project number from `get_board_context`) to find the current iteration.
**Scope:** Does **not** apply to items in "📌 Triage" or "🐱 Todo" — those are backlog items planned for the milestone but not yet started. Adding them to the current cycle would overstate the cycle's scope. They'll get a cycle when work begins.

**Active milestones** (update this list as milestones are retired/created):
- `202608 Contract Release`

(Updated 2026-08-18 sweep: `M4.1: mainnet ready` and `M4.2: mainnet GA` no longer appear on any open board item — a board-wide scan for `has:milestone` on open issues returned only `202608 Contract Release`, `M4.5: GA Fast Follows`, and `MX: Priority and sequencing TBD`. Both M4.1 and M4.2 appear to have been retired/closed and superseded. If M4.1/M4.2 return in a future milestone cycle, re-add them here.)

**Why:** Items actively being worked on should appear in cycle planning views so nothing slips. But an active milestone may contain dozens of Todo items that span multiple future cycles — pulling them all into the current cycle creates noise. Items in future or retired milestones (e.g., `M4.5`, `MX`) don't need a cycle yet — they'll get one when their milestone becomes active.

## R-FC-007: Items in Triage need minimal fields (except PRs)

**When:** An item is in "📌 Triage".
**Action:** No field requirements beyond Status. Triage is the intake column — items are expected to be incomplete.
**Why:** Requiring fields on triage items creates friction for capturing new work quickly.

## R-FC-008: Recently-done items should have Cycle Theme, Cycle, and Assignee

**When:** An item is in "🎉 Done" and was updated within the last 7 days (use `updated:>YYYY-MM-DD` filter).
**Action:** Ensure the item has a Cycle Theme (apply [R-FC-004](#r-fc-004-cycle-theme-defaults-by-repository)), a Cycle (set to the current cycle if missing), and an Assignee (for PRs, use the PR author per [R-PR-001](pr-hygiene.md#r-pr-001-unassigned-prs-should-be-assigned-to-their-author)). Skip bot-authored PRs for assignee (R-PR-001 skip rules apply).
**Guard — verify the close is real and recent before backfilling Cycle/Assignee:** The board `updated` timestamp reflects board-row touches, not the GitHub close. Before backfilling, batch-check `closedAt` and `stateReason` via GraphQL:
- **`closedAt` outside the window** (item closed long ago but board row touched recently, e.g., by a project-automation workflow) → skip backfill; the reporting window for that work has passed.
- **`stateReason` of `NOT_PLANNED` or `DUPLICATE`** → skip Cycle and Assignee backfill; these represent no actual effort and backfilling attributes phantom work to the current cycle. Cycle Theme is still fine to set.
(Added 2026-07-07 after a backlog-cleanup wave: ~20 old issues bulk-closed showed up as "recently done"; github-mgmt#10 had `closedAt` 2025-07-18, and dealbot#415 / filecoin-pay-explorer#52 were NOT_PLANNED/DUPLICATE.)
**Why:** Recently-completed items need proper tagging so periodic reporting captures the work. Without Cycle Theme, Cycle, and Assignee, done items fall through the cracks in cycle reviews and workload summaries. Older done items (beyond the 7-day window) are not worth backfilling — the reporting window has passed.

## R-FC-010: Issues in active milestones should have a Dev Days Estimate

**When:** An **issue** on the board has an active milestone (see list below) but no Dev Days Estimate set. Includes both open issues and recently-done issues (updated within last 3 days). Exclude items with Cycle Theme "zOrganizing Item". Also exclude issues closed as "not planned" (includes duplicates) — these represent no actual effort and don't belong in estimation reporting.
**Action:** Flag for human review. Present a table of items sorted by repository showing: item reference (hyperlinked), title, status, assignee, milestone, and Cycle Theme.
**Scope:** Issues only — PRs inherit effort context from their parent issue.

**Active milestones** (keep in sync with [R-FC-009](#r-fc-009-in-flight-items-in-active-milestones-should-have-a-cycle)):
- `202608 Contract Release`

**Query:** Build the milestone filter from the active-milestones list above rather than a fixed pattern — the old `milestone:"M4*"` prefix match no longer covers `202608 Contract Release` and must be updated whenever that list changes.
- Open: `milestone:"202608 Contract Release" -cycle-theme:"zOrganizing Item" -status:"🎉 Done" is:issue no:dev-days-estimate`
- Recently done: `milestone:"202608 Contract Release" -cycle-theme:"zOrganizing Item" status:"🎉 Done" is:issue no:dev-days-estimate reason:completed updated:>YYYY-MM-DD` (where date is 3 days ago; `reason:completed` excludes duplicates and "not planned" closures)

**Why:** Issues without a Dev Days Estimate are unaccounted effort — they distort both "effort remaining" and "work completed" calculations. Every milestoned issue should have an estimate so planning and reporting are accurate.

## R-FC-011: All Cycle Theme values must match the established list

**When:** Any item on the board (non-Done or recently-done within the last 7 days) has a Cycle Theme value that is not in the established values list above (R-FC-004).
**Action:** Flag for human review. Present the unrecognized value, the items that have it, and suggest the closest match from the established list (likely a typo or variant — e.g., "Filecoin-Pin" vs "Filecoin Pin").
**How to check:** Query all non-Done items and recently-done items that have a Cycle Theme set. Extract distinct Cycle Theme values and diff against the established list. Any value not in the list is flagged.
**Why:** Cycle Theme is a free-text field with no server-side validation — typos and ad-hoc variants silently create theme sprawl that fragments reporting and filtering. A proactive check catches these before they accumulate.

## R-FC-012: Recently-active items without a Cycle get the current cycle

**Enforced mechanically, hourly:** this rule runs automatically via [`foc-mechanical-rules`](../foc-mechanical-rules/) (see [its implementation](../foc-mechanical-rules/foc_mechanical_rules/rules/cycle.py)), scheduled by [`.github/workflows/foc-board-mechanical-rules.yml`](../.github/workflows/foc-board-mechanical-rules.yml). The prose below stays canonical for *what* and *why*; the linked module is canonical for exactly how it's evaluated.

**When:** Any **issue or PR** on the board (any status except "🎉 Done") has no Cycle set and was updated within the last 3 days (`updated:>@today-3d`).
**Action:** Set the Cycle to the current active cycle (the iteration whose date range contains today).
**Skip if the current cycle was previously set and then removed:** If this rule (or any mutation this tool made) previously set the item's Cycle to the *current* cycle and the item now has no Cycle, do not re-add it — flag for human review instead. A human clearing a cycle assignment is a deliberate signal (the work was descoped or deferred) that automation shouldn't overwrite.
**How the removal check works, and its limit:** see [`foc-mechanical-rules`'s "Mutation log" section](../foc-mechanical-rules/README.md#mutation-log) for why GitHub can't answer this directly and how the tool tracks it instead. The short version: this rule can only detect a removal it itself witnessed. A cycle a human cleared *before* this rule ever set it (or before that history existed) won't be caught — the item will just look like any other item missing a Cycle and will get (re-)assigned.
**Relationship to [R-FC-006](#r-fc-006-in-flight-prs-without-a-cycle-should-be-in-the-current-cycle) / [R-FC-009](#r-fc-009-in-flight-items-in-active-milestones-should-have-a-cycle):** Those rules are status/milestone-gated and remain the sweep's judgment-call fallback for items this rule's 3-day activity window doesn't reach (e.g. an in-flight item that's gone quiet for a week). This rule is the broader, simpler, purely time-based mechanical subset — any issue or PR, not just in-flight PRs or active-milestone items.
**Why:** Items with recent activity and no Cycle are a planning gap — they're clearly live work but invisible in cycle views. A 3-day activity window catches this quickly without pulling in stale backlog the way an unconditional "everything gets a cycle" rule would.

## R-FC-013: Open items in a past cycle should move to the current cycle

**Enforced mechanically, hourly:** this rule runs automatically via [`foc-mechanical-rules`](../foc-mechanical-rules/) (see [its implementation](../foc-mechanical-rules/foc_mechanical_rules/rules/cycle.py)), scheduled by [`.github/workflows/foc-board-mechanical-rules.yml`](../.github/workflows/foc-board-mechanical-rules.yml). The prose below stays canonical for *what* and *why*; the linked module is canonical for exactly how it's evaluated.

**When:** Any **issue or PR** on the board (any status except "🎉 Done") has its Cycle set to an iteration whose date range has already ended (a "past cycle").
**Action:** Set the Cycle to the current active cycle (the iteration whose date range contains today).
**Scope:** Only applies when the item's Cycle is a *past* iteration. An item with no Cycle at all is [R-FC-012](#r-fc-012-recently-active-items-without-a-cycle-get-the-current-cycle)'s concern, not this one's. An item whose Cycle is a *future* iteration (deliberately planned ahead) is left alone.
**Skip if a human has since moved it back:** If this rule (or any mutation this tool made under this rule's id) previously moved the item's Cycle *away from* the past-cycle value it currently holds, do not re-apply — flag for human review instead. A human moving an item back to a past cycle after this tool moved it forward is a deliberate signal (e.g. correcting a mistaken auto-move, or intentionally leaving it attributed to the cycle where the work actually happened) that automation shouldn't fight. See [`foc-mechanical-rules`'s "Mutation log" section](../foc-mechanical-rules/README.md#mutation-log) for how this is tracked and its limits (only reversions this tool's own history witnessed are caught).
**Why:** An item still open once its cycle has ended almost always means the cycle ended before the work did — the Cycle value is now stale and understates what's actually in flight this cycle. Leaving it in the old iteration hides the work from current cycle planning and reporting.

## R-FC-014: Recently-completed items without a Cycle get the current cycle

**Enforced mechanically, hourly:** this rule runs automatically via [`foc-mechanical-rules`](../foc-mechanical-rules/) (see [its implementation](../foc-mechanical-rules/foc_mechanical_rules/rules/cycle.py)), scheduled by [`.github/workflows/foc-board-mechanical-rules.yml`](../.github/workflows/foc-board-mechanical-rules.yml). The prose below stays canonical for *what* and *why*; the linked module is canonical for exactly how it's evaluated.

**When:** Any **issue or PR** on the board in "🎉 Done" has no Cycle set and was updated within the last day (`updated:>@today-1d`).
**Action:** Set the Cycle to the current active cycle (the iteration whose date range contains today).
**Relationship to [R-FC-012](#r-fc-012-recently-active-items-without-a-cycle-get-the-current-cycle):** Same "no cycle -> assign current cycle" logic, but R-FC-012 explicitly excludes Done items — this rule is that gap's Done-side counterpart, catching items that moved straight to Done without ever getting a Cycle (e.g. via R-PR-008/R-PR-009's merged/closed-to-Done moves).
**Why a 1-day window, not 3:** An item moved to Done is finished — the window only needs to be wide enough to catch the mechanical Done-move rules' own hourly cadence, not to account for ongoing activity the way R-FC-012's 3-day window does for still-open items.
**Why:** A completed item with no Cycle is invisible in cycle-based reporting (velocity, burndown, "what shipped this cycle") even though the work is done and attributable. Left uncorrected, this silently undercounts every cycle's completed work.
