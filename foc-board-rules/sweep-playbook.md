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

**Rules applied:**
- R-PR-001: Assign unassigned PRs to their author
- R-PR-002: Dependabot PRs → Cycle Theme "Dependency Updates"
- R-PR-003: Dependabot PRs in Triage → Todo
- R-PR-004: Release PRs in Triage → Todo
- R-PR-005: Draft PRs in review/approval statuses → In Progress
- R-PR-006: Non-draft, non-bot PRs in Triage → Awaiting Review
- R-PR-007: Awaiting Review PRs must have human reviewer engagement (flag if not)
- R-PR-008: Merged PRs → Done
- R-PR-009: Closed PRs → Done
- R-SL-001: PRs with maintainer-level approval → Approved by reviewer (check permissions)
- R-FC-004: Set Cycle Theme from repo defaults
- R-FC-005: All PRs should have a Cycle Theme
- R-FC-006: In-flight PRs without a Cycle → current cycle

**Automated vs. flagged:**
- Automated: Status transitions (R-PR-002–009), Cycle Theme (R-FC-004/005), Cycle (R-FC-006), assignee (R-PR-001 for PRs)
- Flagged for human: Missing reviewers (R-PR-007), R-SL-001 when permissions are unclear

## Stage 2: Triage issues

**Goal:** Get issues out of Triage by ensuring they have Cycle Theme and Milestone.

**Query:** `is:issue status:"📌 Triage"`

**Rules applied:**
- R-FC-004: Set Cycle Theme from repo defaults
- R-FC-003: Ensure Milestone is set (check parent issue for inheritance)
- R-SL-004: Move to Todo if both Cycle Theme and Milestone are set

**Automated vs. flagged:**
- Automated: Cycle Theme (R-FC-004), Status → Todo (R-SL-004 when both fields are set)
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
