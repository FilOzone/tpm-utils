# FOC Board Rules

Rules for keeping the [FilOzone FOC project board](https://github.com/orgs/FilOzone/projects/14) consistent and up-to-date. These rules are intended to be applied by an LLM (via the FilOzzy MCP server) or by a human during board triage.

These rules will eventually move to a shared Notion document. For now they live here so they can be iterated on alongside the tooling.

## General behavior

When applying rules (whether by LLM or human):

1. **Report failures and uncertainties.** If a rule cannot be applied (e.g., missing data, ambiguous match, API error) or you're unsure what the correct action is, list the item and the issue rather than skipping silently. Unapplied rules should be surfaced, not swallowed.

2. **Summarize every change.** When setting or changing a field value, always report the old value → new value. For example: `Status: 📌 Triage → 🐱 Todo`. This applies to all mutations, not just status changes.

3. **Always include item titles.** When listing items (in summaries, flags, or reports), always include the item title alongside the `org/repo#number` reference. The number alone lacks context.

4. **Choose query strategy by scope.** When enforcing a *single rule* or verifying a *specific condition*, use targeted board queries (e.g., `is:pr -status:"🎉 Done" -has:"cycle-theme"` to find PRs missing a Cycle Theme). When doing a *full rule sweep* across all rules, fetch all open items in one query (`is:pr -status:"🎉 Done"`) and evaluate each item against every rule — this avoids redundant overlapping queries and is more efficient overall. See `list_board_items` tool docs for filter syntax.

5. **Supplement board data with GitHub PR metadata efficiently.** The project board provides field values (Status, Cycle Theme, Milestone, etc.) but not PR-specific metadata like author, draft status, or reviewer assignments. Many rules (R-PR-001, R-PR-002, R-PR-005, R-PR-007) need this metadata. Rather than querying each PR individually (`gh pr view` in a loop), use batch approaches:

   - **`gh search prs --owner FilOzone --owner filecoin-project --state open`** — one call returns author, isDraft, and state for all open PRs across both orgs. Covers R-PR-001 (author for assignment), R-PR-002 (dependabot detection), and R-PR-005 (draft detection).
   - **`gh pr list -R <repo> --state open`** — per-repo but returns reviews and reviewRequests. Use this only for repos that have PRs in "Awaiting Review" status to check R-PR-007.

   **Rationale:** The board API and GitHub PR API are separate systems. A full rule sweep touching 70+ items would otherwise require 70+ individual `gh pr view` calls. The search/list approach reduces this to ~3–5 calls total.

   **Limitation:** This batch approach only works when the PR set maps to a simple search filter (e.g., all open PRs in an org). For arbitrary PR lists (e.g., specific closed PRs, a hand-picked set), you'll still need individual `gh pr view` calls or a per-repo `gh pr list` with post-filtering.

6. **Use bulk operations when possible.** When applying the same field+value to multiple items, use `bulk_set_board_item_field` instead of individual `set_board_item_field` calls. This is common when applying a rule that affects many items the same way (e.g., setting Cycle Theme on several PRs from the same repo, or moving multiple dependabot PRs from Triage to Todo). Even two items is worth batching — it saves a tool call and resolves field info only once.

7. **Flag unfamiliar Cycle Theme values.** You don't need to proactively audit all Cycle Theme values, but if while processing an item you encounter a Cycle Theme that isn't in the established values list (R-FC-004), flag it. It may be a misspelling or an unauthorized new value.

8. **Reconcile counts before and after bulk operations.** When building a bulk operation from query results, verify the item count matches. For example, if a query returns 25 synapse-sdk items, the bulk call should contain exactly 25 item refs. After applying, re-query to confirm zero items remain. Manually transcribing item IDs from large result sets is error-prone — group items programmatically (e.g., by repo) rather than cherry-picking from a wall of text.

9. **External repos: try once, then move on.** The board includes items from repos outside the `FilOzone` and `filecoin-project` orgs (e.g., `ipshipyard/ipfs-deploy-action`). We typically don't have write access to these repos. When a rule requires modifying the PR itself (assigning, requesting reviewers, etc.), attempt the action once. If it fails with a permissions error (403), report it and move on — don't retry or escalate. Board-level fields (Status, Cycle Theme, etc.) can still be set regardless of repo access since those live on the project board, not the repo.

## How to use

These rules can be applied manually or referenced by an LLM when performing board maintenance tasks. Each rule file describes:

- **When** the rule applies (trigger condition)
- **What** action to take
- **Why** the rule exists

## Rule files

- [pr-hygiene.md](pr-hygiene.md) — Rules for keeping PR items well-formed
- [status-lifecycle.md](status-lifecycle.md) — Rules for status transitions
- [field-completeness.md](field-completeness.md) — Rules for required fields by status
