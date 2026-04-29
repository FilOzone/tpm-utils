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

## R-PR-005: Draft PRs should be In Progress

**When:** A PR is a draft and its status is "📌 Triage", "🔎 Awaiting review", "✔️ Approved by reviewer", or "⌚️ Issue awaiting PR merge".
**Action:** Set Status to `⌨️ In Progress`.
**Why:** A draft PR is not ready for review or approval. If it's in Triage, it should move to In Progress since someone is actively working on it. If it's in Awaiting Review or later, the author likely converted it back to draft after feedback — the board should reflect that it's back in active development. Draft PRs in Todo or In Progress are fine as-is.

## R-PR-006: Non-draft PRs in Triage should be Awaiting Review

**When:** A PR in "📌 Triage" is not a draft, not authored by a bot, and not a release PR.
**Action:** Set Status to `🔎 Awaiting review`.
**Why:** A non-draft, non-bot PR that's been opened is ready for review. The default assumption is that the author considers it review-ready unless they marked it as draft.

## R-PR-007: Awaiting Review PRs must have human reviewer engagement

**When:** A PR has status "🔎 Awaiting review" (including PRs just routed there by R-PR-006) but has no human reviewer — neither a pending request nor a submitted review from a human.
**Action:** Flag for human review. Suggest the PR author request a reviewer. Do not auto-assign reviewers — the author or team lead should decide who reviews.
**How to check:** Look at both `reviewRequests` (pending requests) and `reviews` (already submitted). A PR has human reviewer engagement if *either* list contains a non-bot entry. Filter out bot reviewers (`copilot-pull-request-reviewer`, any `app/*` author). Use `gh pr list -R <repo> --state open --json number,reviewRequests,reviews` to batch-check per repo.
**Check this every sweep:** This rule must be checked for *all* PRs in Awaiting Review status, not just newly routed ones.
**Why:** A PR sitting in Awaiting Review with no human reviewer engaged will never actually get reviewed. It's a silent bottleneck.

## R-PR-008: Merged PRs should be marked Done

**When:** A PR on the board has been merged (GitHub state: `merged`) but its board status is not "🎉 Done".
**Action:** Set Status to `🎉 Done`.
**Why:** The board should reflect reality. A merged PR is done.

## R-PR-009: Closed-without-merge PRs should be marked Done

**When:** A PR on the board has been closed without merging (GitHub state: `closed`, not `merged`) but its board status is not "🎉 Done".
**Action:** Set Status to `🎉 Done`.
**Note:** Consider adding a comment or label to distinguish "closed without merge" from "merged" if this distinction matters for reporting.
**Why:** Closed PRs are no longer active work. Leaving them in non-Done columns clutters the board.
