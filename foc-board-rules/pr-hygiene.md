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
**Priority:** This rule overrides [R-FC-004](field-completeness.md#r-fc-004-cycle-theme-defaults-by-repository) (repo defaults). Dependabot PRs are always "Dependency Updates" regardless of which repo they're in.
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

1. **Write-access approval, no blocking changes_requested** → `✔️ Approved by reviewer` (per [R-SL-001](status-lifecycle.md#r-sl-001-prs-with-approved-reviews-should-be-approved-by-reviewer)).
2. **Last human review is more recent than last commit** (`lastHumanReview > lastCommit`) → `⌨️ In Progress`. The reviewer left feedback and the author hasn't responded with new commits yet.
3. **Last commit is more recent than last human review** (`lastCommit > lastHumanReview`) → `🔎 Awaiting review`. The author pushed after the feedback, likely addressing it — the PR is ready for re-review. (A re-requested reviewer further confirms this — the author explicitly asked the reviewer to look again.)
4. **No human reviewer has engaged yet** (only bot reviews or no reviews at all) → `🔎 Awaiting review`. The PR needs initial review.

**Note on R-SL-001 re-request exception:** The [R-SL-001](status-lifecycle.md#r-sl-001-prs-with-approved-reviews-should-be-approved-by-reviewer) re-request exception only prevents moving to *Approved* — it does not affect R-PR-006 routing. A re-requested reviewer who previously requested changes means the PR is awaiting their re-review, which is consistent with case 3 (→ Awaiting Review), not a reason to keep the PR in In Progress.

**How to check:** Use `gh pr view -R <repo> <number> --json reviews,commits --jq '{reviews: [.reviews[] | {author: .author.login, state: .state, submittedAt: .submittedAt}], lastCommit: .commits[-1].committedDate}'` to compare timestamps. The key comparison: if `lastHumanReview > lastCommit`, the author hasn't responded yet (case 2); if `lastCommit > lastHumanReview`, the author addressed feedback (case 3). Only needed for PRs where the per-repo `gh pr list` data shows human review engagement.
**Why:** Non-draft, non-bot PRs should always leave Triage, and In Progress PRs may need re-evaluation. But the destination depends on review state — not every PR goes to Awaiting Review. A PR with unaddressed feedback belongs in In Progress, a PR with a merge-authority approval belongs in Approved, and a PR with no feedback or addressed feedback belongs in Awaiting Review. This is the counterpart to R-PR-005: when a draft PR becomes non-draft, it advances — but the destination depends on what reviewers have already said.

## R-PR-007: Awaiting Review PRs must have human reviewer engagement

**When:** A PR has status "🔎 Awaiting review" (including PRs just routed there by R-PR-006) but has no human reviewer — neither a pending request nor a submitted review from a human.
**Exclude:** [External items](status-lifecycle.md#terminology) — we can't request reviewers on repos outside the blessed orgs, so flagging them is noise. (Added after ipshipyard/ipfs-deploy-action PRs were flagged every sweep with no possible action.)
**Action:** Flag for human review. Suggest the PR author request a reviewer. Do not auto-assign reviewers — the author or team lead should decide who reviews.
**How to check:** Phase 1 `reviewRequests` only shows *pending* review requests — it does not show reviews already submitted. **Empty `reviewRequests` is ambiguous:** it could mean no reviewer was ever requested, or it could mean a reviewer was requested, submitted their review, and the pending request was consumed. **Always Phase 2** (`gh pr view --json reviews,commits,reviewRequests`) **before flagging** — check both `reviewRequests` (pending) and `reviews` (submitted). A PR has human reviewer engagement if *either* list contains a non-bot entry. Filter out bot reviewers (`copilot-pull-request-reviewer`, any `app/*` author). Do not flag based on Phase 1 data alone.
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
