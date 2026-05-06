# Status Lifecycle Rules

Rules governing how items should transition through board statuses.

## Board statuses (in order)

1. **📌 Triage** — New items that need to be categorized and prioritized
2. **🐱 Todo** — Accepted work, not yet started
3. **⌨️ In Progress** — Actively being worked on
4. **🔎 Awaiting review** — Work complete, waiting for reviewer feedback
5. **✔️ Approved by reviewer** — Review passed, waiting for merge or follow-up
6. **⌚️ Issue awaiting PR merge** — Issue is done pending its linked PR(s) merging
7. **🎉 Done** — Complete

### Terminology

**Item** — Anything on the project board: an issue, a pull request, or a draft item (note). All board rules apply to items generically unless a rule specifies "issue" or "PR" explicitly.

**Blessed orgs** — `FilOzone` and `filecoin-project`. These are the GitHub orgs where we have write access and can manage assignees, milestones, reviewers, etc. Items from repos outside these orgs are **external items** — board-level fields (Status, Cycle Theme, Cycle) can be set, but repo-level fields (assignees, milestones, reviewers) cannot.

**Active items** — Items in statuses 3–6: "⌨️ In Progress", "🔎 Awaiting review", "✔️ Approved by reviewer", or "⌚️ Issue awaiting PR merge". These represent work that is supposedly happening right now. Items in Triage, Todo, and Done are not active.

## R-SL-001: PRs with approved reviews should be "Approved by reviewer"

**When:** A PR has at least one approving review from a user **with write/maintain/admin access to the repo** and no outstanding blocking "changes requested" reviews from a reviewer with merge authority, but its status is "🔎 Awaiting review" or "⌨️ In Progress".
**Action:** Set Status to `✔️ Approved by reviewer`.
**Verification:** Before moving, confirm the approving reviewer has write, maintain, or admin access to the repository. An approval from someone without merge permissions doesn't unblock the PR — it still needs a maintainer review. Use `gh api repos/{owner}/{repo}/collaborators/{username}/permission --jq '.permission'` to check (look for `write`, `maintain`, or `admin`). When evaluating "changes requested" — only changes requested by reviewers with write access block the transition. A "changes requested" from a read-only reviewer doesn't prevent moving to Approved if a write-access reviewer has approved.
**Superseding changes requested:** A more recent write-access approval can supersede an older write-access "changes requested" review. Treat the changes requested as resolved if *either* condition is met: (1) new commits were pushed after the "changes requested" review and before the approval — this implies the feedback was addressed; or (2) the approval is unconditional (i.e., does not contain language like "approving assuming you incorporate X's feedback" or "approve pending changes from [reviewer]"). If the approving comment defers to the previous reviewer's feedback, the "changes requested" is still blocking — flag for human review rather than auto-transitioning.
**Exception — re-requested reviewer:** Even when superseding conditions are met, if the reviewer who requested changes has been **re-requested** for review (appears in `reviewRequests`), their objection is NOT superseded. A re-request signals the author explicitly wants that reviewer's sign-off before merging. The PR should remain in "🔎 Awaiting review" until the re-requested reviewer submits a new review. (Added after filecoin-pin-website#154 was incorrectly treated as Approved despite juliangruber being re-requested.)
**Flagging context:** When flagging a PR where an approval doesn't have sufficient permissions, always report the full reviewer picture — not just the insufficient approval. Include who else is requested or has reviewed, and whether any of them *do* have merge authority (write/maintain/admin). The flag should help the human understand whether action is needed, not just that a permission check failed.
**Why:** PRs with maintainer-level approval are ready for merge regardless of their current board status. A PR in "In Progress" can receive an approval while the author is still pushing commits — the board should reflect that the review gate has passed. Only objections from reviewers with merge authority ("changes requested") should block this transition.

## R-SL-002: Items should not skip backwards without reason

**When:** An item moves from a later status to an earlier one (e.g., "Approved by reviewer" back to "In Progress").
**Action:** This is allowed but should have a reason. If done by an LLM, log why.
**Why:** Backward transitions usually indicate rework or a process problem. Tracking them helps identify systemic issues.

## R-SL-003: Issues with all linked PRs merged should usually be marked as Done

**When:** An issue has status "⌚️ Issue awaiting PR merge" and all of its linked PRs are merged.
**Action:** Ask if its Status should be set to `🎉 Done`. It likely should be, but it's possible there are additional things in the issue that need to be completed out of PR.
**Why:** Usually the issue's work is complete once its PRs land.

## R-SL-004: Triage issues with Cycle Theme and Milestone can move to Todo

**When:** An issue has status "📌 Triage" (or no status, which is treated as equivalent to Triage) and has both a Cycle Theme and a Milestone set.
**Action:** Set Status to `🐱 Todo`.
**Why:** An issue with both a Cycle Theme and a Milestone has been sufficiently categorized and scoped — it's no longer "unsorted" and belongs in the Todo backlog. This reduces triage column noise and makes it easier to see what truly needs initial review.

## R-SL-006: PRs should never be in "Issue awaiting PR merge"

**When:** A PR on the board has status "⌚️ Issue awaiting PR merge".
**Action:** Flag for human review. The intended status is almost always "🔎 Awaiting review" — the person likely picked the wrong status. Do not auto-transition, but report it prominently.
**Why:** "Issue awaiting PR merge" is semantically an *issue* status — it means the issue's work is done and it's just waiting for its linked PR(s) to land. A PR being in this status is a data entry error that makes the board confusing to read.

## R-SL-005: New items from Triage should get a status within one cycle

**When:** An item has been in "📌 Triage" for more than 2 weeks.
**Action:** Flag for human review. Do not auto-transition.
**Why:** Stale triage items indicate either forgotten work or items that should be removed from the board. A human should decide.

## R-SL-007: PRs with changes requested should move back to In Progress

**When:** A PR has status "🔎 Awaiting review" or "✔️ Approved by reviewer" and receives a "changes requested" review from a user **with write/maintain/admin access to the repo**.
**Action:** Set Status to `⌨️ In Progress`.
**Why:** A reviewer with merge authority requesting changes means the PR needs rework before it can proceed. The board should reflect that it's back in active development, not waiting for review. This is the counterpart to R-SL-001 — just as an approval advances the status, a changes-requested pushes it back. Only objections from reviewers with merge authority trigger this; a "changes requested" from a read-only reviewer doesn't warrant a status change since it doesn't block the PR.

## R-SL-008: Issues with linked PRs should be "Issue awaiting PR merge"

**When:** An issue on the board has one or more linked pull requests (visible via the "Linked pull requests" field in `list_board_items`), **at least one linked PR is actively in flight** (board status is one of "⌨️ In Progress", "🔎 Awaiting review", "✔️ Approved by reviewer", or "⌚️ Issue awaiting PR merge"), and the issue's status is not already "⌚️ Issue awaiting PR merge" or "🎉 Done".
**Action:** Set Status to `⌚️ Issue awaiting PR merge`. Once a PR is actively in flight for an issue, the PR represents the active work — the issue just needs to wait for the PR to land. Also ensure field completeness: if the issue has no assignee, inherit from the linked PR's assignee (per [R-FC-001](field-completeness.md#r-fc-001-in-flight-and-done-items-must-have-an-assignee)); if no cycle, match the linked PR's cycle; if no milestone, check the linked PR or parent issue (per [R-FC-003](field-completeness.md#r-fc-003-all-open-issues-should-have-a-milestone)).
**Skip if:** All linked PRs are in "📌 Triage" or "🐱 Todo" (including drafts in backlog). A PR that hasn't started active work doesn't make the issue "awaiting merge" — both the issue and PR are still in planning/backlog. The issue should stay in its current status until the PR moves to In Progress or beyond.
**Cycle inheritance for existing "Issue awaiting PR merge" items:** Even if R-SL-008 doesn't trigger a status change (because the issue is already in "Issue awaiting PR merge"), cycle inheritance still applies. When checking items in this status that lack a cycle, look up the linked PR's cycle and inherit it — this applies regardless of the issue's milestone. (Added after dealbot#427 was missed because its MX milestone excluded it from R-FC-009, but its linked PR dealbot#487 was in the current cycle.)
**How to check:** Include "Linked pull requests" in the `list_board_items` fields. The field returns PR metadata including number, state, assignee, and author. Cross-reference with board data to confirm the PR's status is In Progress or later before moving the issue.
**Why:** The PR is the active representation of the work. Keeping the issue in Triage, Todo, or In Progress alongside an actively in-flight PR creates board clutter and double-counts the work. Moving the issue to "Issue awaiting PR merge" makes the PR the single source of truth for progress, while the issue tracks delivery completion (via R-SL-003 when all linked PRs merge). However, if the PR is itself still in backlog (Todo/Triage/draft), neither the issue nor the PR represents active work — moving the issue prematurely would misrepresent the board state.

## R-SL-009: Stale active items should move back to Todo

**When:** An item in "⌨️ In Progress", "🔎 Awaiting review", or "✔️ Approved by reviewer" has not been updated in 2+ weeks. Exclude items with Cycle Theme "zOrganizing Item" (meta/tracking items) and items in "⌚️ Issue awaiting PR merge" (those are waiting on a PR, not stale — the PR's activity is what matters and is tracked separately).
**Action:** Flag for human review. Present a table of stale items showing: item reference and title, current status, board last updated date, GitHub last updated date, who last updated it (from GitHub comments). The human should be able to quickly scan and confirm which items to move back to Todo.
**How to check:** Two-pass approach — the board `updated` field and GitHub `updatedAt` track different things and don't necessarily match. The board `updated` reflects when board-level fields were last changed; GitHub `updatedAt` reflects when the issue/PR itself had activity (comments, commits, label changes, etc.). Use the board filter `updated:<YYYY-MM-DD` (where date is 2 weeks ago) as a first pass to find candidates. Then verify each candidate against GitHub's `updatedAt` and recent comments — if the item has recent GitHub activity, it's not actually stale (the board fields just haven't been touched). Only flag items that are stale on *both* the board and GitHub.
**Why:** Items sitting in active statuses with no recent activity are not actually active — they create a false picture of what the team is working on. Moving them back to Todo keeps the active columns honest and makes it easier to see what's really in flight. They can always be moved back to In Progress when work actually resumes.
