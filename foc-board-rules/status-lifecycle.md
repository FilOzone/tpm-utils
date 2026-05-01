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

**When:** A PR has at least one approving review from a user **with write access to the repo** and no outstanding "changes requested" reviews, but its status is "🔎 Awaiting review".
**Action:** Set Status to `✔️ Approved by reviewer`.
**Verification:** Before moving, confirm the approving reviewer has write (or admin) access to the repository. An approval from someone without merge permissions doesn't unblock the PR — it still needs a maintainer review. Use `gh api repos/{owner}/{repo}/collaborators/{username}/permission --jq '.permission'` to check (look for `write` or `admin`).
**Why:** Keeps the Awaiting Review column clean — only items that actually need reviewer attention should be there. But only maintainer-level approvals actually unblock a PR for merge.

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
