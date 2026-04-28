# PR Hygiene Rules

Rules for keeping pull request items on the FOC board well-formed.

## R-PR-001: Unassigned PRs should be assigned to their author

**When:** A PR on the board has no assignee.
**Action:** Set the assignee to the PR author (look up via GitHub API).
**Skip if:** The author is a bot (`app/dependabot`, `FilOzzy`, or any `app/*` author).
**Why:** Every PR should have an accountable human. The author is the natural default when no one else has been explicitly assigned.

## R-PR-002: Dependabot PRs should have Cycle Theme "Dependency Updates"

**When:** A PR authored by `app/dependabot` has no Cycle Theme set, or has a Cycle Theme other than "Dependency Updates".
**Action:** Set Cycle Theme to `Dependency Updates`.
**Why:** Dependency update PRs are a distinct category of work. Consistent labeling makes it easy to filter them in or out of board views.

## R-PR-003: Dependabot PRs should be in Todo status

**When:** A PR authored by `app/dependabot` has status "📌 Triage".
**Action:** Set Status to `🐱 Todo`.
**Why:** Dependabot PRs don't need triage — they're well-understood work items. Moving them straight to Todo reduces noise in the Triage column.

## R-PR-004: Release PRs in Triage should move to Todo

**When:** A PR in "📌 Triage" is a release PR (e.g., `chore(master): release ...` from synapse-sdk, or `chore: release to production (main)` from dealbot).
**Action:** Set Status to `🐱 Todo`.
**Why:** Release PRs are a known, mechanical step that the engineering team needs to execute. They don't need triage — they just need to get done.

## R-PR-005: Draft PRs in Triage should be In Progress

**When:** A PR in "📌 Triage" is a draft PR.
**Action:** Set Status to `⌨️ In Progress`.
**Why:** A draft PR means someone is actively working on it. It shouldn't sit in Triage — it's already in flight.

## R-PR-006: Non-draft PRs in Triage should be Awaiting Review

**When:** A PR in "📌 Triage" is not a draft, not authored by a bot, and not a release PR.
**Action:** Set Status to `🔎 Awaiting review`.
**Why:** A non-draft, non-bot PR that's been opened is ready for review. The default assumption is that the author considers it review-ready unless they marked it as draft.

## R-PR-007: Awaiting Review PRs must have a human reviewer requested

**When:** A PR has status "🔎 Awaiting review" but has no reviewer requested, or the only reviewer is `@copilot` (not a human).
**Action:** Flag for human review. Suggest the PR author request a reviewer. Do not auto-assign reviewers — the author or team lead should decide who reviews.
**Why:** A PR sitting in Awaiting Review with no human reviewer assigned will never actually get reviewed. It's a silent bottleneck.

## R-PR-008: Merged PRs should be marked Done

**When:** A PR on the board has been merged (GitHub state: `merged`) but its board status is not "🎉 Done".
**Action:** Set Status to `🎉 Done`.
**Why:** The board should reflect reality. A merged PR is done.

## R-PR-009: Closed-without-merge PRs should be marked Done

**When:** A PR on the board has been closed without merging (GitHub state: `closed`, not `merged`) but its board status is not "🎉 Done".
**Action:** Set Status to `🎉 Done`.
**Note:** Consider adding a comment or label to distinguish "closed without merge" from "merged" if this distinction matters for reporting.
**Why:** Closed PRs are no longer active work. Leaving them in non-Done columns clutters the board.
