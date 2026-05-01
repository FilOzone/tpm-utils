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

## R-SL-001: PRs with approved reviews should be "Approved by reviewer"

**When:** A PR has at least one approving review from a user **with write access to the repo** and no outstanding blocking "changes requested" reviews from a write-access reviewer, but its status is "🔎 Awaiting review" or "⌨️ In Progress".
**Action:** Set Status to `✔️ Approved by reviewer`.
**Verification:** Before moving, confirm the approving reviewer has write (or admin) access to the repository. An approval from someone without merge permissions doesn't unblock the PR — it still needs a maintainer review. Use `gh api repos/{owner}/{repo}/collaborators/{username}/permission --jq '.permission'` to check (look for `write` or `admin`). When evaluating "changes requested" — only changes requested by reviewers with write access block the transition. A "changes requested" from a read-only reviewer doesn't prevent moving to Approved if a write-access reviewer has approved.
**Superseding changes requested:** A more recent write-access approval can supersede an older write-access "changes requested" review. Treat the changes requested as resolved if *either* condition is met: (1) new commits were pushed after the "changes requested" review and before the approval — this implies the feedback was addressed; or (2) the approval is unconditional (i.e., does not contain language like "approving assuming you incorporate X's feedback" or "approve pending changes from [reviewer]"). If the approving comment defers to the previous reviewer's feedback, the "changes requested" is still blocking — flag for human review rather than auto-transitioning.
**Flagging context:** When flagging a PR where an approval doesn't have sufficient permissions, always report the full reviewer picture — not just the insufficient approval. Include who else is requested or has reviewed, and whether any of them *do* have write access. The flag should help the human understand whether action is needed, not just that a permission check failed.
**Why:** PRs with maintainer-level approval are ready for merge regardless of their current board status. A PR in "In Progress" can receive an approval while the author is still pushing commits — the board should reflect that the review gate has passed. Only write-access reviewer objections ("changes requested") should block this transition.

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

**When:** A PR has status "🔎 Awaiting review" or "✔️ Approved by reviewer" and receives a "changes requested" review from a user **with write access to the repo**.
**Action:** Set Status to `⌨️ In Progress`.
**Why:** A write-access reviewer requesting changes means the PR needs rework before it can proceed. The board should reflect that it's back in active development, not waiting for review. This is the counterpart to R-SL-001 — just as an approval advances the status, a changes-requested pushes it back. Only write-access reviewer objections trigger this; a "changes requested" from a read-only reviewer doesn't warrant a status change since it doesn't block the PR.

## R-SL-008: Issues with linked PRs should be "Issue awaiting PR merge"

**When:** An issue on the board has one or more linked pull requests (visible via the "Linked pull requests" field in `list_board_items`) and its status is not already "⌚️ Issue awaiting PR merge" or "🎉 Done".
**Action:** Set Status to `⌚️ Issue awaiting PR merge`. Once a PR exists for an issue, the PR represents the active work — the issue just needs to wait for the PR to land. Also ensure field completeness: if the issue has no assignee, inherit from the linked PR's assignee (per R-FC-001); if no cycle, match the linked PR's cycle; if no milestone, check the linked PR or parent issue (per R-FC-003).
**How to check:** Include "Linked pull requests" in the `list_board_items` fields. The field returns PR metadata including number, state, assignee, and author.
**Why:** The PR is the active representation of the work. Keeping the issue in Triage, Todo, or In Progress alongside an open PR creates board clutter and double-counts the work. Moving the issue to "Issue awaiting PR merge" makes the PR the single source of truth for progress, while the issue tracks delivery completion (via R-SL-003 when all linked PRs merge).
