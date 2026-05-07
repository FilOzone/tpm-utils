# Sweep Playbook

Prescribed stage-by-stage workflow for a full board sweep. Each stage uses targeted queries — never fetch all non-Done items in one shot.

Work through stages in order. Complete all actions and reporting for one stage before moving to the next.

## Stage 1: Open PRs

**Goal:** Apply PR hygiene, status lifecycle, and field completeness rules to all open PRs.

**Queries:**
- Board: `is:pr -status:"🎉 Done"` (all non-Done PRs)
- Board: `is:pr is:merged -status:"🎉 Done"` (merged PRs not yet Done — R-PR-008)
- Board: `is:pr is:closed -status:"🎉 Done"` (closed PRs not yet Done — R-PR-009)
- Board (field gaps): `is:pr -status:"🎉 Done" no:assignee`, `is:pr -status:"🎉 Done" no:cycle-theme`, `is:pr -status:"🎉 Done" -status:"🐱 Todo" -status:"📌 Triage" no:cycle` — use these targeted queries for field-gap checks (R-PR-001, R-FC-005, R-FC-006) instead of scanning the bulk PR list
- GitHub Phase 1 (lightweight): `gh pr list -R <repo> --state open --json number,author,isDraft,reviewDecision,reviewRequests` (one call per repo — **no `reviews` field**)
- GitHub Phase 2 (targeted): `gh pr view -R <repo> <number> --json reviews,commits,reviewRequests` — only for PRs needing deep analysis (R-PR-006 status determination, R-SL-001 approval verification, R-SL-007 changes-requested check). See general behavior rule 6 for trigger conditions.

**Rules applied:**
- R-PR-001: Assign unassigned PRs to their author
- R-PR-002: Dependabot PRs → Cycle Theme "Dependency Updates"
- R-PR-003: Dependabot PRs in Triage → Todo
- R-PR-004: Release PRs in Triage → Todo
- R-PR-005: Draft PRs in review/approval statuses → In Progress
- R-PR-006: Non-draft, non-bot PRs in Triage or In Progress → correct status (Awaiting Review, In Progress, or Approved based on review state)
- R-PR-007: Awaiting Review PRs must have human reviewer engagement (flag if not)
- R-PR-008: Merged PRs → Done
- R-PR-009: Closed PRs → Done
- R-SL-001: PRs with merge-authority approval (in Awaiting Review or In Progress) → Approved by reviewer
- R-SL-007: PRs with merge-authority changes requested (in Awaiting Review or Approved) → In Progress
- R-SL-006: PRs in "Issue awaiting PR merge" → flag (almost always a mistake)
- R-FC-004: Set Cycle Theme from repo defaults
- R-FC-005: All PRs should have a Cycle Theme
- R-FC-006: In-flight PRs + dependabot/release Todo PRs without a Cycle → current cycle

**Ordering note — Cycle gaps after status changes:** Run the `no:cycle` field-gap queries *after* completing status mutations, not before. PRs that move from Triage/Todo into in-flight statuses (R-PR-003→Todo for dependabot, R-PR-005/006→In Progress or Awaiting Review) also need cycles per R-FC-006, but they won't appear in the pre-mutation `no:cycle` in-flight query. Either re-query after status changes or track the newly in-flight items from your status mutations and include them in the cycle bulk update. (Added after a sweep where cycle gaps for newly in-flight items had to be re-derived manually.)

**Cross-referencing board data with GitHub metadata:**

The main bottleneck in Stage 1 is joining board query results (65+ items) with GitHub Phase 1 metadata (14+ repos). Do this programmatically with `jq`, not by manually scanning JSON walls.

**`list_board_items` output is JSONL.** Each line after the "Found N items:" header is a valid JSON object. To build a JSON array for `jq` joins: `echo "$RESULT" | tail -n +2 | grep '^{' | jq -s '.'`. Do NOT hand-transcribe board items into JSON — parse the output directly. Include `"Node ID"` in the fields parameter to get project item node IDs (`PVTI_...`), which can be passed directly to `bulk_set_board_item_field` to skip per-item re-resolution.

After fetching both datasets:

1. **Filter Phase 1 to board-only PRs.** Extract the PR numbers from the board query, then use `jq` to select only matching entries from each repo's Phase 1 output. This drops the noise (e.g., curio has 18 open PRs but only 3 are on the board).

2. **Produce action lists per rule.** After the join (step 1), each entry should have both GitHub fields (`.isDraft`, `.reviewDecision`, `.author`) and a `.board_status` field added during the join. Pipe through `jq` selects to identify rule violations:
   - R-PR-005: `select(.isDraft and (.board_status | IN("Triage","Awaiting review","Approved","Issue awaiting PR merge")))`
   - R-PR-006 Phase 2 candidates: `select(.isDraft == false and .author.is_bot == false and (.board_status | IN("Triage","In Progress")))`
   - R-SL-007: `select(.reviewDecision == "CHANGES_REQUESTED" and (.board_status | IN("Awaiting review","Approved")))`

3. **Treat `reviewDecision: ""` as ambiguous.** Empty means GitHub produced no formal verdict — not that no reviews exist. Always Phase 2 before changing status on these PRs. See general behavior rule 6.

Example — build a joined dataset in one bash call:
```bash
# After fetching board PRs into $BOARD_ITEMS and Phase 1 per-repo into files:
for repo_file in /tmp/phase1_*.json; do
  repo=$(basename "$repo_file" .json | sed 's/phase1_//')
  jq --argjson board "$BOARD_ITEMS" --arg repo "$repo" '
    [.[] | select(.number as $n | $board | any(.repo == $repo and .number == $n))]
  ' "$repo_file"
done
```

This gives you a clean, small dataset to reason about — typically 15-30 items instead of 100+.

**Automated vs. flagged:**
- Automated: Status transitions (R-PR-002–009, R-SL-001, R-SL-007), Cycle Theme (R-FC-004/005), Cycle (R-FC-006), assignee (R-PR-001 for PRs)
- Flagged for human: Missing reviewers (R-PR-007), R-SL-001 when permissions are unclear, R-SL-006 PRs in wrong status

## Stage 2: Triage issues

**Goal:** Get issues out of Triage by ensuring they have Cycle Theme and Milestone, and by detecting issues that already have linked PRs.

**Query:** `is:issue status:"📌 Triage"` (include "Linked pull requests" and "Parent issue" in fields)

**Rules applied:**
- R-SL-008: Issues with linked PRs → set status based on PR state (Issue awaiting PR merge, In Progress, or Done), inherit assignee/cycle/milestone
- R-FC-004: Set Cycle Theme from repo defaults
- R-FC-003: Ensure Milestone is set (check parent issue for inheritance)
- R-SL-004: Move to Todo if both Cycle Theme and Milestone are set (and no linked PRs)

**Automated vs. flagged:**
- Automated: Cycle Theme (R-FC-004), Status → Todo (R-SL-004 when both fields are set), linked-PR status transitions (R-SL-008)
- Flagged for human: Missing Milestone when no parent to inherit from

## Stage 3: Non-Done issues — field completeness

**Goal:** Ensure all non-Done issues have Cycle Theme and Milestone.

**Queries:**
- `is:issue -status:"🎉 Done" no:cycle-theme`
- `is:issue -status:"🎉 Done" no:milestone`

**Exclude:** Items with Cycle Theme "zOrganizing Item" (meta/tracking items, not real work).

**Rules applied:**
- R-FC-003: All open issues should have a Milestone
- R-FC-004: Infer Cycle Theme from repository

**Automated vs. flagged:**
- Automated: Cycle Theme from repo defaults (R-FC-004)
- Flagged for human: Missing Milestone on items without a parent to inherit from, items in external repos where milestone can't be set

## Stage 4: Active items — health check

**Goal:** Ensure every active item (see status-lifecycle.md Terminology) has an accountable owner, is actually being worked on, has correct status relative to linked PRs, and has a cycle set when appropriate.

**Queries:**
- `-status:"🎉 Done" -status:"🐱 Todo" -status:"📌 Triage" no:assignee` (unassigned active items)
- `-status:"🎉 Done" -status:"🐱 Todo" -status:"📌 Triage" -status:"⌚️ Issue awaiting PR merge" updated:<YYYY-MM-DD` (stale active items, where date is 2 weeks ago; excludes "Issue awaiting PR merge" — those are waiting on PRs, not stale)
- `is:issue -status:"🎉 Done" -status:"⌚️ Issue awaiting PR merge"` with "Linked pull requests" field (issues with linked PRs that might need to move to "Issue awaiting PR merge" — but only if the linked PR is In Progress or later, per R-SL-008)
- `status:"⌚️ Issue awaiting PR merge" no:cycle` (issues awaiting PR merge without a cycle — inherit from linked PR per R-SL-008, not just R-FC-009)

**Rules applied:**
- R-FC-001: Active items must have an assignee
- R-PR-001: For unassigned PRs, assign to the PR author (skip bots)
- R-SL-008: Not-done issues with linked PRs **where at least one PR is In Progress or later** should be in "Issue awaiting PR merge"; also inherit cycle from linked PR for items already in this status
- R-SL-009: Stale items in In Progress / Awaiting Review / Approved (no update in 2+ weeks on both board and GitHub) should move back to Todo
- R-FC-009: Issues in "Issue awaiting PR merge" with active milestones should have a cycle

**How to investigate unassigned issues (per R-FC-001):**
1. Batch-fetch issue metadata using GraphQL (general behavior rule 12): author, comments, closedByPullRequestsReferences, and timelineItems(CROSS_REFERENCED_EVENT) for linked PRs
2. If a linked PR exists, use the PR's assignee
3. Otherwise, infer from the comment stream (who is actively working on it)
4. If uncertain, propose with justification and flag for human confirmation

**How to check for linked PRs (per R-SL-008):**
1. Include "Linked pull requests" in the `list_board_items` fields
2. Cross-reference linked PRs with board data to check their status — only move the issue to "Issue awaiting PR merge" if at least one linked PR is In Progress or later (not in Todo/Triage)
3. Also inherit assignee, cycle, and milestone from the linked PR if missing (per R-SL-008)

**How to discover unlinked PRs (per R-SL-008):**
After processing formal linked PRs, check for In Progress issues that have **no** linked PRs — these may have cross-referencing PRs that weren't formally linked. See R-SL-008 "Discovering unlinked PRs" for the procedure. Only fetch timeline data for this targeted set (typically 5-15 issues), not all issues — the GraphQL `timelineItems` query returns verbose data and shouldn't be run broadly. Flag findings for human rather than auto-transitioning.

**How to report stale items (per R-SL-009):**
1. Exclude zOrganizing Items and "Issue awaiting PR merge" items
2. For each candidate, fetch GitHub `updatedAt` and recent comments — if GitHub shows recent activity, the item is not stale (board fields just haven't been touched)
3. Present a table of confirmed-stale items: item ref + title, current status, board last updated, GitHub last updated, who last updated (from GitHub)
4. Human confirms which items to move back to Todo

**Automated vs. flagged:**
- Automated: PR assignees set to author (R-PR-001), issues with linked PRs where at least one PR is In Progress or later → Issue awaiting PR merge (R-SL-008)
- Flagged for human: Issues where assignee can't be confidently determined, stale active items (R-SL-009), issues awaiting PR merge without a cycle (confirm current cycle assignment)

## Stage 5: Recently-done items — reporting readiness

**Goal:** Ensure recently-completed items have Cycle Theme, Cycle, and Assignee so they show up correctly in periodic reporting.

**Queries — use targeted gap queries, not a bulk fetch:**
- `status:"🎉 Done" updated:>YYYY-MM-DD no:cycle-theme` (missing Cycle Theme)
- `status:"🎉 Done" updated:>YYYY-MM-DD no:cycle` (missing Cycle)
- `status:"🎉 Done" updated:>YYYY-MM-DD no:assignee -cycle-theme:"Dependency Updates"` (missing assignee, excluding dependabot — those are expected to be unassigned per R-PR-001)

where date is 7 days ago. Do **not** fetch all recently-done items first — that returns 100+ items and wastes context. The gap queries surface only the items that need action. (Added after a sweep where the bulk fetch consumed a full page of results before the gap queries found only ~20 actionable items.)

**Rules applied:**
- R-FC-008: Recently-done items should have Cycle Theme, Cycle, and Assignee
- R-FC-004: Infer Cycle Theme from repository and title
- R-PR-001: For unassigned PRs, assign to the PR author. For merged release PRs (bot-authored), assign to the person who merged/approved them. Dependabot PRs can be left unassigned.

**Automated vs. flagged:**
- Automated: Cycle Theme from repo defaults (R-FC-004), Cycle set to current cycle, PR assignees set to author (or merger for release PRs)
- Flagged for human: Issues without assignees (investigate linked PRs and comment stream, propose assignee with justification), items where Cycle Theme can't be inferred from R-FC-004

**Note:** Use the GitHub API (`gh api repos/{owner}/{repo}/issues/{number}/assignees`) for assignments — `gh pr edit --add-assignee` may fail on repos with Projects Classic enabled. For release PRs, use `gh api repos/{owner}/{repo}/pulls/{number} --jq '.merged_by.login'` to find who merged.

## Stage 6: Effort estimation gaps

**Goal:** Surface issues in active milestones that are missing a Dev Days Estimate, so effort remaining and work completed calculations are accurate.

**Rules applied:**
- R-FC-010: Issues in active milestones should have a Dev Days Estimate

**Queries:** See R-FC-010 for the full filter syntax (open issues + recently-done issues).

**Fields to include:** Repository, Id, Title, Status, Assignees, Milestone, Cycle Theme

**Output:** Present results as a single markdown table sorted by repository, suitable for pasting into Slack. Every item reference should be a hyperlink (e.g., `[dealbot#209](https://github.com/FilOzone/dealbot/issues/209)`).

```
| Item | Title | Status | Assignee | Milestone | Cycle Theme |
|------|-------|--------|----------|-----------|-------------|
| [dealbot#209](https://github.com/FilOzone/dealbot/issues/209) | We need to be able to view jobs | 🎉 Done | SgtPooki | M4.2: mainnet GA | Dealbot |
```

**Automated vs. flagged:**
- This stage is **report-only** — no automated mutations. The human decides whether to backfill estimates or accept the gaps.
