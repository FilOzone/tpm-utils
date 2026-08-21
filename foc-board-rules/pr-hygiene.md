# PR Hygiene Rules

Rules for keeping pull request items on the FOC board well-formed.

## R-PR-001: Unassigned PRs should be assigned to their author

**Enforced mechanically, hourly:** this rule is a pure function of observable state, so it runs automatically via [`foc-mechanical-rules`](../foc-mechanical-rules/) (see [R-PR-001's implementation](../foc-mechanical-rules/foc_mechanical_rules/rules/assignee.py)), scheduled by [`.github/workflows/foc-board-mechanical-rules.yml`](../.github/workflows/foc-board-mechanical-rules.yml). A sweep no longer needs to apply it by hand — the prose below stays canonical for *what* the rule does and *why*; the linked module is canonical for exactly how it's evaluated.

**When:** A PR on the board has no assignee.
**Action:** Set the assignee to the PR author (look up via GitHub API).
**Skip if:** The author is a bot (`app/dependabot`, `FilOzzy`, or any `app/*` author) — with one exception: **merged release PRs** (e.g., `chore(master): release ...`, `chore: release to production (main)`) should be assigned to the person who merged or approved them, since that human is accountable for the release. Use `gh api repos/{owner}/{repo}/pulls/{number} --jq '.merged_by.login'` to find the merger. Dependabot PRs can be left unassigned.

**Also skip if the assignee was deliberately removed:** Check `gh api repos/{owner}/{repo}/issues/{number}/events --jq '.[] | select(.event=="unassigned")'`. If an `unassigned` event exists for this PR (removing the author or anyone else), do **not** re-assign the author — a human intentionally cleared the assignee, and re-adding it silently overrides that decision. Flag for human review instead of auto-assigning. (Added 2026-08-20 after [filbeam/worker#323](https://github.com/filbeam/worker/pull/323) was auto-assigned to its author during a sweep. Note: that specific PR's GitHub event history had no `unassigned` event — the deprioritization signal there was a draft-conversion comment, not an assignee removal — so this check won't catch every "intentionally paused" PR. It only covers the literal case of a removed assignee.)
**Why:** Every PR should have an accountable human. The author is the natural default when no one else has been explicitly assigned. For release PRs, the bot creates the PR but a human decides to merge it — that human should be credited. But if a human already removed an assignee, that's a deliberate signal (e.g., the work is paused or reassigned) that automation shouldn't overwrite.

## R-PR-002: Dependabot PRs should have Cycle Theme "Dependency Updates"

**When:** A PR authored by dependabot (`gh pr list --json author` returns either `app/dependabot` or just `dependabot` depending on the repo — match both) has no Cycle Theme set, or has a Cycle Theme other than "Dependency Updates".
**Action:** Set Cycle Theme to `Dependency Updates`.
**Priority:** This rule overrides [R-FC-004](field-completeness.md#r-fc-004-cycle-theme-defaults-by-repository) (repo defaults). Dependabot PRs are always "Dependency Updates" regardless of which repo they're in.
**Why:** Dependency update PRs are a distinct category of work. Consistent labeling makes it easy to filter them in or out of board views.

## R-PR-003: Dependabot PRs should be in Todo status

**When:** A PR authored by dependabot (either `app/dependabot` or `dependabot` — see [R-PR-002](#r-pr-002-dependabot-prs-should-have-cycle-theme-dependency-updates)) has status "📌 Triage".
**Action:** Set Status to `🐱 Todo`.
**Why:** Dependabot PRs don't need triage — they're well-understood work items. Moving them straight to Todo reduces noise in the Triage column.

## R-PR-004: Release PRs in Triage should move to Todo

**When:** A PR in "📌 Triage" is a release PR (e.g., `chore(master): release ...` from synapse-sdk, or `chore: release to production (main)` from dealbot).
**Action:** Set Status to `🐱 Todo`.
**Detection regex:** `^chore\((master|main)\):? release|^chore: release` — match `chore(master)`/`chore(main)` release PRs and bare `chore: release` PRs. **Do not include `deps` in the scope alternation** — `chore(deps): ...` is dependabot's pattern and belongs to [R-PR-002](#r-pr-002-dependabot-prs-should-have-cycle-theme-dependency-updates) / [R-PR-003](#r-pr-003-dependabot-prs-should-be-in-todo-status). Mixing them ends in the same final state (Todo) but routes the wrong rule and can hide a real Cycle Theme bug. (Tightened 2026-06-18 after `^chore\((master|main|deps)\)` falsely matched dependabot PRs in playbook examples.)
**Why:** Release PRs are a known, mechanical step that the engineering team needs to execute. They don't need triage — they just need to get done.

## R-PR-005: Draft PRs should be In Progress

**When:** A PR is a draft and its status is "📌 Triage", "🔎 Awaiting review", "✔️ Approved by reviewer", or "⌚️ Issue awaiting PR merge".
**Action:** Set Status to `⌨️ In Progress`.
**Why:** A draft PR is not ready for review or approval. If it's in Triage, it should move to In Progress since someone is actively working on it. If it's in Awaiting Review or later, the author likely converted it back to draft after feedback — the board should reflect that it's back in active development. Draft PRs in Todo or In Progress are fine as-is.

## R-PR-006: Non-draft, non-bot PRs in Triage or In Progress — determine correct status

**When:** A PR is not a draft, not authored by a bot, not a release PR, and its status is "📌 Triage" or "⌨️ In Progress".
**Action:** Compute the derived inputs and apply the [PR status determination table](pr-status-table.md); it is the canonical routing logic (this rule's former prose cases 1-4, the comments-count-as-reviews paragraph, and the carve-outs from pdp-explorer#118, dealbot#638, and filecoin-services#522 all live there now, alongside the R-SL-001/007 routing they interact with).
**How to check:** Use `gh pr view -R <repo> <number> --json reviews,commits,comments --jq '{reviews: [.reviews[] | {author: .author.login, state: .state, submittedAt: .submittedAt}], comments: [.comments[] | {author: .author.login, authorAssociation: .authorAssociation, body: .body, createdAt: .createdAt}], lastCommit: .commits[-1].committedDate}'` to get the timestamps and comment data the table's `last_feedback` input needs — Phase 1 (`gh pr list`) never includes `comments`, so this Phase 2 call is required for every R-PR-006 candidate, not just ones where Phase 1 shows formal review engagement. A PR with only substantive comments and no formal review looks identical to a PR with zero engagement in Phase 1 data, and skipping Phase 2 there would miss it.
**Why:** Non-draft, non-bot PRs should always leave Triage, and In Progress PRs may need re-evaluation. But the destination depends on review state; not every PR goes to Awaiting Review. A PR with unaddressed feedback belongs in In Progress, a PR with a merge-authority approval belongs in Approved, and a PR with no feedback or addressed feedback belongs in Awaiting Review. This is the counterpart to R-PR-005: when a draft PR becomes non-draft, it advances, but the destination depends on what reviewers have already said.

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
