# Sweep Playbook

Prescribed stage-by-stage workflow for a full board sweep. Each stage uses targeted queries — never fetch all non-Done items in one shot.

Work through stages in order. Complete all actions and reporting for one stage before moving to the next.

## Stage 1: Open PRs

**Goal:** Apply PR hygiene, status lifecycle, and field completeness rules to all open PRs.

**Queries:**
- Board: `is:pr -status:"🎉 Done"` (all open PRs)
- Board: `is:pr is:merged -status:"🎉 Done"` (merged PRs not yet Done — R-PR-008)
- Board: `is:pr is:closed -status:"🎉 Done"` (closed PRs not yet Done — R-PR-009)
- GitHub: `gh pr list -R <repo> --state open --json number,author,isDraft,reviewDecision,reviewRequests,reviews` (one call per repo with open PRs on the board)
- GitHub (for R-PR-006 In Progress candidates only): `gh pr view -R <repo> <number> --json reviews,commits` to compare last human review timestamp vs last commit timestamp

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
- R-SL-001: PRs with write-access approval (in Awaiting Review or In Progress) → Approved by reviewer
- R-SL-007: PRs with write-access changes requested (in Awaiting Review or Approved) → In Progress
- R-SL-006: PRs in "Issue awaiting PR merge" → flag (almost always a mistake)
- R-FC-004: Set Cycle Theme from repo defaults
- R-FC-005: All PRs should have a Cycle Theme
- R-FC-006: In-flight PRs + dependabot/release Todo PRs without a Cycle → current cycle

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

## Stage 3: Open issues — field completeness

**Goal:** Ensure all open issues have Cycle Theme and Milestone.

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
- `is:issue -status:"🎉 Done" -status:"🐱 Todo" -status:"📌 Triage" -status:"⌚️ Issue awaiting PR merge"` with "Linked pull requests" field (active issues that should be in "Issue awaiting PR merge")
- `status:"⌚️ Issue awaiting PR merge" no:cycle` (issues awaiting PR merge without a cycle)

**Rules applied:**
- R-FC-001: Active items must have an assignee
- R-PR-001: For unassigned PRs, assign to the PR author (skip bots)
- R-SL-008: Active issues with linked PRs should be in "Issue awaiting PR merge"
- R-SL-009: Stale items in In Progress / Awaiting Review / Approved (no update in 2+ weeks on both board and GitHub) should move back to Todo
- R-FC-009: Issues in "Issue awaiting PR merge" with active milestones should have a cycle

**How to investigate unassigned issues (per R-FC-001):**
1. Batch-fetch issue metadata using GraphQL (general behavior rule 12): author, comments, closedByPullRequestsReferences, and timelineItems(CROSS_REFERENCED_EVENT) for linked PRs
2. If a linked PR exists, use the PR's assignee
3. Otherwise, infer from the comment stream (who is actively working on it)
4. If uncertain, propose with justification and flag for human confirmation

**How to check for linked PRs (per R-SL-008):**
1. Include "Linked pull requests" in the `list_board_items` fields
2. Any active issue with a non-empty linked PR list should move to "Issue awaiting PR merge"
3. Also inherit assignee, cycle, and milestone from the linked PR if missing (per R-SL-008)

**How to report stale items (per R-SL-009):**
1. Exclude zOrganizing Items and "Issue awaiting PR merge" items
2. For each candidate, fetch GitHub `updatedAt` and recent comments — if GitHub shows recent activity, the item is not stale (board fields just haven't been touched)
3. Present a table of confirmed-stale items: item ref + title, current status, board last updated, GitHub last updated, who last updated (from GitHub)
4. Human confirms which items to move back to Todo

**Automated vs. flagged:**
- Automated: PR assignees set to author (R-PR-001), issues with linked PRs → Issue awaiting PR merge (R-SL-008)
- Flagged for human: Issues where assignee can't be confidently determined, stale active items (R-SL-009), issues awaiting PR merge without a cycle (confirm current cycle assignment)

## Stage 5: Recently-done items — reporting readiness

**Goal:** Ensure recently-completed items have Cycle Theme, Cycle, and Assignee so they show up correctly in periodic reporting.

**Query:** `status:"🎉 Done" updated:>YYYY-MM-DD` (where date is 7 days ago)

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
