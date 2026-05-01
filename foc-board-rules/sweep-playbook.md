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

## Stage 4: In-flight items — assignee check

**Goal:** Ensure every item that has progressed beyond Triage/Todo has an accountable owner.

**Query:** `-status:"🎉 Done" -status:"🐱 Todo" -status:"📌 Triage" no:assignee`

**Rules applied:**
- R-FC-001: In-flight items must have an assignee
- R-PR-001: For unassigned PRs, assign to the PR author (skip bots)

**How to investigate issues (per R-FC-001):**
1. Batch-fetch issue metadata using GraphQL (general behavior rule 12): author, comments, closedByPullRequestsReferences, and timelineItems(CROSS_REFERENCED_EVENT) for linked PRs
2. If a linked PR exists, use the PR's assignee
3. Otherwise, infer from the comment stream (who is actively working on it)
4. If uncertain, propose with justification and flag for human confirmation

**Automated vs. flagged:**
- Automated: PR assignees set to author (R-PR-001)
- Flagged for human: Issues where assignee can't be confidently determined

## Stage 5: Recently-done items — reporting readiness

**Goal:** Ensure recently-completed items have Cycle Theme, Cycle, and Assignee so they show up correctly in periodic reporting.

**Query:** `status:"🎉 Done" updated:>YYYY-MM-DD` (where date is 7 days ago)

**Rules applied:**
- R-FC-008: Recently-done items should have Cycle Theme, Cycle, and Assignee
- R-FC-004: Infer Cycle Theme from repository and title
- R-PR-001: For unassigned PRs, assign to the PR author (skip bots)

**Automated vs. flagged:**
- Automated: Cycle Theme from repo defaults (R-FC-004), Cycle set to current cycle, PR assignees set to author
- Flagged for human: Issues without assignees (investigate linked PRs and comment stream, propose assignee with justification), items where Cycle Theme can't be inferred from R-FC-004

**Note:** Dependabot PRs are skipped for assignee per R-PR-001. Use the GitHub API (`gh api repos/{owner}/{repo}/issues/{number}/assignees`) for assignments — `gh pr edit --add-assignee` may fail on repos with Projects Classic enabled.
