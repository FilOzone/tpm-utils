# PR Hygiene Rules

Rules for keeping pull request items on the FOC board well-formed.

## R-PR-001: Unassigned PRs should be assigned to their author

**When:** A PR on the board has no assignee.
**Action:** Set the assignee to the PR author (look up via GitHub API).
**Skip if:** The author is a bot (`app/dependabot`, `FilOzzy`, or any `app/*` author) — with one exception: **merged release PRs** (e.g., `chore(master): release ...`, `chore: release to production (main)`) should be assigned to the person who merged or approved them, since that human is accountable for the release. Use `gh api repos/{owner}/{repo}/pulls/{number} --jq '.merged_by.login'` to find the merger. Dependabot PRs can be left unassigned.
**Why:** Every PR should have an accountable human. The author is the natural default when no one else has been explicitly assigned. For release PRs, the bot creates the PR but a human decides to merge it — that human should be credited.

## R-PR-002: Dependabot PRs should have Cycle Theme "Dependency Updates"

**When:** A PR authored by `app/dependabot` has no Cycle Theme set, or has a Cycle Theme other than "Dependency Updates".
**Action:** Set Cycle Theme to `Dependency Updates`.
**Priority:** This rule overrides R-FC-004 (repo defaults). Dependabot PRs are always "Dependency Updates" regardless of which repo they're in.
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

## R-PR-006: Non-draft, non-bot PRs in Triage or In Progress — determine correct status

**When:** A PR is not a draft, not authored by a bot, not a release PR, and its status is "📌 Triage" or "⌨️ In Progress".
**Action:** Determine the correct status based on the PR's review state. Check the PR's reviews, commits, and reviewer permissions to pick the right destination:

1. **Write-access approval, no blocking changes_requested** → `✔️ Approved by reviewer` (per R-SL-001).
2. **Human reviewer left comments/questions/changes_requested and the author has NOT pushed new commits after** → `⌨️ In Progress`. The author still needs to respond to feedback.
3. **Human reviewer left comments but the author HAS pushed new commits after** → `🔎 Awaiting review`. The author likely addressed the feedback and is ready for re-review.
4. **No human reviewer has engaged yet** (only bot reviews or no reviews at all) → `🔎 Awaiting review`. The PR needs initial review.

**How to check:** Use `gh pr view -R <repo> <number> --json reviews,commits --jq '{reviews: [.reviews[] | {author: .author.login, state: .state, submittedAt: .submittedAt}], lastCommit: .commits[-1].committedDate}'` to compare the last human review timestamp against the last commit timestamp. Only needed for PRs where the per-repo `gh pr list` data shows human review engagement.
**Why:** Non-draft, non-bot PRs should always leave Triage, and In Progress PRs may need re-evaluation. But the destination depends on review state — not every PR goes to Awaiting Review. A PR with unaddressed feedback belongs in In Progress, a PR with a write-access approval belongs in Approved, and a PR with no feedback or addressed feedback belongs in Awaiting Review. This is the counterpart to R-PR-005: when a draft PR becomes non-draft, it advances — but the destination depends on what reviewers have already said.

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
