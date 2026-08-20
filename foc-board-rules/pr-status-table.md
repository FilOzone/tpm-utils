# PR Status Determination Table

Canonical decision logic for what board status an open PR should have. This table is the single source of truth for PR status routing; [R-PR-006](pr-hygiene.md#r-pr-006-non-draft-non-bot-prs-in-triage-or-in-progress--determine-correct-status) is its primary consumer, and it also encodes the routing halves of R-PR-005, R-SL-001, and R-SL-007 (those rules keep their trigger scopes, verification procedures, and rationale in their own files).

The logic here is a pure function: derived inputs in, target status out. That makes it testable by hand against the worked examples below, and it is the spec for the eventual mechanical-rules script (see [future-ideas.md](future-ideas.md)).

## Derived inputs

Compute these once per PR from Phase 1 / Phase 2 data (see [general behavior rule 6](README.md#general-behavior)):

| Input | Definition |
|-------|------------|
| `draft` | The PR is a draft (Phase 1 `isDraft`). |
| `bot` | Authored by dependabot (`app/dependabot` or `dependabot`), `FilOzzy`, any other `app/*` author (per [R-PR-001](pr-hygiene.md#r-pr-001-unassigned-prs-should-be-assigned-to-their-author)'s bot-author list), or a release PR (per R-PR-004 title regex: `^chore\((master\|main)\):? release\|^chore: release`; never include `deps` in the alternation). Note this is broader than R-PR-002/003's dependabot-only matching — R-PR-002/003 only ever apply to dependabot, but any bot author should skip the human-routing rows below. |
| `authoritative_approval` | An APPROVED review from a human with write/maintain/admin access that is unconditional and not superseded. Full verification, superseding, and conditional-approval logic: [R-SL-001](status-lifecycle.md#r-sl-001-prs-with-approved-reviews-should-be-approved-by-reviewer). An approval from a read/triage-access reviewer never sets this input; it triggers the insufficient-permission flag instead (see flag checks below). |
| `blocking_cr` | An unresolved CHANGES_REQUESTED review from a human with write/maintain/admin access. Resolved per R-SL-001's superseding conditions, except: if the CR reviewer has been re-requested (appears in `reviewRequests`), the CR stays blocking regardless (R-SL-001 re-request exception). CRs from read/triage-access reviewers never count. |
| `last_commit` | Timestamp of the PR's most recent commit. |
| `last_feedback` | Timestamp of the most recent *actionable* human feedback: CHANGES_REQUESTED or COMMENTED reviews, plus substantive PR-level comments from humans with verified write/maintain/admin repo access. `authorAssociation` of OWNER/MEMBER/COLLABORATOR is only a cheap candidate filter to shortlist commenters worth checking — it is not a permission level (a MEMBER/COLLABORATOR can still have only read/triage access) and must not substitute for the actual collaborator-permission lookup ([R-SL-001](status-lifecycle.md#r-sl-001-prs-with-approved-reviews-should-be-approved-by-reviewer)'s verification step: `gh api repos/{owner}/{repo}/collaborators/{username}/permission`). Excludes: APPROVED reviews (an approval is not feedback the author must act on), the PR author's own reviews and comments (self-reviews are not reviewer engagement), bot and `app/*` authors, and pure coordination chatter (merge timing, status updates). `null` if no such feedback exists. |

## Decision table

Evaluate top-down; the first matching row wins.

| # | Condition | Target status | Encodes |
|---|-----------|---------------|---------|
| 1 | `draft` | ⌨️ In Progress | R-PR-005 |
| 2 | `bot` | 🐱 Todo (only moves the PR if currently in 📌 Triage; otherwise leave as-is) | R-PR-003, R-PR-004 |
| 3 | `authoritative_approval` and not `blocking_cr` | ✔️ Approved by reviewer | R-SL-001 |
| 4 | `last_feedback` is not null and `last_feedback > last_commit` | ⌨️ In Progress (see comment-only caveat below) | R-SL-007; R-PR-006 case 2 |
| 5 | `last_feedback` is not null and `last_commit > last_feedback` | 🔎 Awaiting review | R-PR-006 case 3; R-SL-007 skip condition |
| 6 | `last_feedback` is null | 🔎 Awaiting review | R-PR-006 case 4 |

Notes:

- **Row 1 vs. row 2 precedence (draft bots):** a draft dependabot/release PR matches row 1 (In Progress), not row 2 (Todo). This is intentional: R-PR-003/R-PR-004 don't themselves exclude drafts, but a draft signals someone is actively iterating on the PR regardless of author, and R-PR-005's rationale ("not ready for review") applies just as much to bot-authored PRs. In practice this case is rare (dependabot/release PRs are almost never drafts).
- A blocking CR that is the latest activity lands in row 4 (the CR counts in `last_feedback`); a blocking CR followed by author commits lands in row 5 (author addressed feedback, awaiting re-review). Both match R-SL-007 and its skip condition exactly.
- **`authoritative_approval` and `blocking_cr` together:** row 3 requires `not blocking_cr`, so this combination never matches row 3 and always falls through to the timestamp rows (4-6) — there is no separate flag-instead-of-auto-route branch. The [applicability table](#applicability-by-current-status) below governs whether that timestamp-row result is auto-applied or flagged for the PR's current status; there is no additional flag solely because an approval and a CR coexist.
- **Tie-breaker for `last_feedback == last_commit`:** GitHub timestamps are second-granularity, so an exact match is possible (e.g., a review submitted via the same API call sequence as a commit push, or clock-synced automation). Treat a tie as `last_feedback > last_commit` (row 4 wins) — unaddressed feedback should never be presumed resolved just because it wasn't strictly *before* the commit.
- **Comment-only caveat for row 4:** when the post-commit feedback is *only* substantive comments (no formal review) and the PR is currently in 🔎 Awaiting review, do not auto-move it to In Progress; flag it per [R-SL-010](status-lifecycle.md#r-sl-010-prs-in-awaiting-review-with-unaddressed-reviewer-comments-should-be-flagged) instead (informal comments are too noisy to auto-transition on). For PRs currently in 📌 Triage or ⌨️ In Progress, comments count fully; in particular an In Progress PR with a substantive maintainer comment after the last commit stays In Progress (filecoin-services#522).

## Applicability by current status

The table computes the *target*; the current board status decides whether to auto-apply, flag, or leave alone:

| Current status | Handling |
|----------------|----------|
| 📌 Triage, ⌨️ In Progress | Auto-apply the table result (R-PR-006). |
| 🐱 Todo | Rows 1-2 only (drafts and bots are fine in Todo; leave them). Human non-draft PRs parked in Todo are backlog by choice; do not auto-route. |
| 🔎 Awaiting review | Auto-apply rows 1 (R-PR-005), 3 (R-SL-001), and 4 when the feedback includes a formal CR (R-SL-007). Comment-only row 4: flag per R-SL-010. |
| ✔️ Approved by reviewer | Auto-apply rows 1 (R-PR-005) and 4 with a formal CR (R-SL-007). If the table yields Awaiting review because the recorded approval turns out insufficient or superseded, flag with full reviewer context (R-SL-001 flagging guidance) rather than auto-demoting. |
| ⌚️ Issue awaiting PR merge | Never a valid PR status. Drafts auto-move to In Progress (row 1, per R-PR-005); everything else is flagged per R-SL-006, with the table's computed target included in the flag as the suggested fix. |
| 🎉 Done | Out of scope; merged/closed handling is R-PR-008/R-PR-009. |

## Post-table flag checks

After routing, for every PR whose (new or unchanged) status is 🔎 Awaiting review:

- **No human engagement** (no pending review request and no submitted human review): flag per [R-PR-007](pr-hygiene.md#r-pr-007-awaiting-review-prs-must-have-human-reviewer-engagement). Excludes external items.
- **Comment-only feedback after last commit**: flag per R-SL-010 (see row 4 caveat).
- **Insufficient-permission approval** (an APPROVED review that did not set `authoritative_approval` because the reviewer lacks merge authority): flag with the full reviewer picture per R-SL-001's flagging guidance.

## Worked examples (regression cases from sweep history)

These incidents drove the input definitions above; any change to this table should keep them routing correctly.

| PR | Situation | Correct routing |
|----|-----------|-----------------|
| pdp-explorer#118 (2026-07-07) | Read-access approval submitted after the last commit. | Approval is excluded from `last_feedback` and does not set `authoritative_approval`; rows 5/6 give 🔎 Awaiting review, plus the insufficient-permission flag. (A literal reading of the old case 2 prose routed it to In Progress.) |
| dealbot#638 (2026-07-07) | Author's own COMMENTED reviews after the last commit. | Self-reviews are excluded from `last_feedback`; row 6 gives 🔎 Awaiting review. |
| filecoin-services#522 (2026-06-24) | In Progress PR, no formal review, substantive maintainer comment after the last commit. | Comment counts in `last_feedback`; row 4 keeps it ⌨️ In Progress (no bounce to Awaiting review that R-SL-010 would re-flag next sweep). |
| filecoin-pin-website#154 | Write-access CR, later approval, but the CR reviewer was re-requested. | Re-request keeps `blocking_cr` true; row 3 does not fire, PR stays 🔎 Awaiting review. |
