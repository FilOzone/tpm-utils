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

## R-FC-001: In Progress items must have an assignee

**When:** An item has status "⌨️ In Progress" but no assignee.
**Action:** Flag for human assignment. If it's a PR, suggest the PR author. Otherwise see if you can make an assignee suggestion based on the item's comment stream.
**Why:** Active work must have someone accountable. Unassigned in-progress items are a planning gap.

## R-FC-002: In Progress items should have a Cycle Theme

**When:** An item has status "⌨️ In Progress" but no Cycle Theme.
**Action:** Flag for human review. Suggest a Cycle Theme based on the item's repository and title if possible.
**Why:** Cycle Theme is how the team groups related work for planning. Items without one fall through the cracks in cycle reviews.

## R-FC-003: All open issues should have a Milestone

**When:** An **issue** on the board (any status except "🎉 Done") has no milestone set. Exclude items with Cycle Theme "zOrganizing Item" (these are meta/tracking items, not real work).
**Action:** First, check if the issue has a parent issue (via `get_board_item` — look for "Parent issue" field). If the parent has a milestone, inherit it. Otherwise, flag for human review, grouped by Cycle Theme or repository. Report the item's current status, assignee, and Cycle Theme to help the human decide.
**Scope:** Issues only. **Milestones on PRs are optional** — PRs often inherit their delivery context from the issue they close, and many repos don't milestone PRs at all.
**Why:** Every real issue should be tied to a delivery milestone so it's tracked against a timeline. Issues without milestones fall through the cracks during planning. Even Triage items benefit from early milestone assignment — it helps prioritize what to triage first.

## R-FC-004: Cycle Theme defaults by repository

**When:** An item has no Cycle Theme set.
**Action:** Infer the Cycle Theme from the item's repository and title:

| Repository | Default Cycle Theme | Notes |
|---|---|---|
| `FilOzone/dealbot` | Dealbot | |
| `FilOzone/filecoin-pay-explorer` | Filecoin Pay Explorer | |
| `FilOzone/synapse-sdk` | SDK Changes | |
| `filecoin-project/filecoin-pin` | Filecoin Pin | |
| `filecoin-project/filecoin-pin-website` | Filecoin Pin | Website for filecoin-pin |
| `FilOzone/filecoin-pay` | Filecoin Pay | |
| `FilOzone/pdp-explorer` | PDP Explorer | |
| `FilOzone/filecoin-cloud` | filecoin.cloud | |
| `filecoin-project/curio` | Curio Hardening | |
| `FilOzone/tpm-utils` | Maintainer Experience | Usually, but not always |
| `FilOzone/foc-devnet` | Maintainer Experience | Dev tooling |
| `FilOzone/infra` | Other | Unless a better theme applies (see below) |

For repositories not listed above, check the item title and description for context clues. In particular:
- **infra** items that reference a specific product in the title or description (e.g., "dealbot" in the title) should inherit that product's Cycle Theme. Otherwise default to "Other".
- **Stacked PRs**: Check if the item's description or comments reference related PRs/issues. If it's stacked on or related to another item that already has a Cycle Theme, use the same theme.

If no reasonable inference can be made, flag for human review — do not invent a new Cycle Theme value.

**Existing Cycle Theme values** (as of 2026-04-27):

> Contract Upgrade, Curio Hardening, Dealbot, Dependency Updates, Docs, filecoin.cloud, Filecoin Pay, Filecoin Pay Explorer, Filecoin Pay Tools, Filecoin Pin, GA Durability, Maintainer Experience, Operational Readiness, Other, PDP Explorer, SDK Changes, zOrganizing Item

**Never create a new Cycle Theme.** Always use one of the existing values above. If none fit, flag for human review.

**Why:** Most items naturally belong to the Cycle Theme of their repository. Automating the obvious cases reduces manual triage work and keeps the board consistent. Using only established values prevents theme sprawl.

## R-FC-005: All PRs should have a Cycle Theme

**When:** A PR on the board (any status except "🎉 Done") has no Cycle Theme set.
**Action:** Apply R-FC-004 to infer a Cycle Theme. If no inference can be made, flag for human review.
**Why:** PRs represent concrete work. Every PR should be attributable to a theme so it shows up in cycle reviews and workload tracking. Unlike issues (which may be speculative), PRs are always real work in progress.

## R-FC-006: In-flight PRs without a cycle should be in the current cycle

**When:** A PR on the board has no Cycle set and is **actively in flight** — meaning its status is "⌨️ In Progress", "🔎 Awaiting review", or "✔️ Approved by reviewer".
**Action:** Set the Cycle to the current active cycle. Use `list_board_field_options("Cycle")` to find the current iteration.
**Scope:** Does **not** apply to PRs in "🐱 Todo" or "📌 Triage". Todo PRs — especially those with future milestones (MX, M4.5) — are backlog items. Forcing them into the current cycle overstates what's actually being worked on this cycle. They'll get a cycle when they move to In Progress.
**Why:** PRs actively being worked on or reviewed should be visible in cycle planning. But the cycle field should reflect *when work is happening*, not just that the PR exists.

## R-FC-009: In-flight items in active milestones should have a cycle

**When:** An item (PR or issue) has a milestone that is currently active, has no Cycle set, and is **actively in flight** — meaning its status is "⌨️ In Progress", "🔎 Awaiting review", "✔️ Approved by reviewer", or "⌚️ Issue awaiting PR merge".
**Action:** Set the Cycle to the current active cycle. Use `list_board_field_options("Cycle")` to find the current iteration.
**Scope:** Does **not** apply to items in "📌 Triage" or "🐱 Todo" — those are backlog items planned for the milestone but not yet started. Adding them to the current cycle would overstate the cycle's scope. They'll get a cycle when work begins.

**Active milestones** (update this list as milestones are retired/created):
- `M4.1: mainnet ready`
- `M4.2: mainnet GA`

**Why:** Items actively being worked on should appear in cycle planning views so nothing slips. But a milestone like M4.2 may contain dozens of Todo items that span multiple future cycles — pulling them all into the current cycle creates noise. Items in future or retired milestones (e.g., `M4.5`, `MX`) don't need a cycle yet — they'll get one when their milestone becomes active.

## R-FC-007: Items in Triage need minimal fields (except PRs)

**When:** An item is in "📌 Triage".
**Action:** No field requirements beyond Status. Triage is the intake column — items are expected to be incomplete.
**Why:** Requiring fields on triage items creates friction for capturing new work quickly.

## R-FC-008: Done items don't need field enforcement

**When:** An item is in "🎉 Done".
**Action:** No field auditing. Don't flag missing fields on completed items.
**Why:** Retroactively filling in fields on done items has low value and high annoyance.
