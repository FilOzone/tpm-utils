# FOC Board Rules

Rules for keeping the [FilOzone FOC project board](https://github.com/orgs/FilOzone/projects/14) consistent and up-to-date. These rules are intended to be applied by an LLM (via the FilOzzy MCP server) or by a human during board triage.

These rules will eventually move to a shared Notion document. For now they live here so they can be iterated on alongside the tooling.

## General behavior

When applying rules (whether by LLM or human):

1. **Report failures and uncertainties.** If a rule cannot be applied (e.g., missing data, ambiguous match, API error) or you're unsure what the correct action is, list the item and the issue rather than skipping silently. Unapplied rules should be surfaced, not swallowed.

2. **Summarize every change.** When setting or changing a field value, always report the old value → new value. For example: `Status: 📌 Triage → 🐱 Todo`. This applies to all mutations, not just status changes.

3. **Always include item titles.** When listing items (in summaries, flags, or reports), always include the item title alongside the `org/repo#number` reference. The number alone lacks context.

4. **Choose query strategy by scope.** When enforcing a *single rule* or verifying a *specific condition*, use targeted board queries (e.g., `is:pr -status:"🎉 Done" -has:"cycle-theme"` to find PRs missing a Cycle Theme). When doing a *full rule sweep* across all rules, fetch all open items in one query (`is:pr -status:"🎉 Done"`) and evaluate each item against every rule — this avoids redundant overlapping queries and is more efficient overall. See `list_board_items` tool docs for filter syntax.

5. **Supplement board data with GitHub PR metadata efficiently.** The project board provides field values (Status, Cycle Theme, Milestone, etc.) but not PR-specific metadata like author, draft status, reviewer assignments, or review decisions. Many rules (R-PR-001, R-PR-002, R-PR-005, R-PR-006, R-PR-007, R-SL-001) need this metadata. Use a two-tier approach:

   **Primary: per-repo `gh pr list`** — For each repo that has open PRs on the board, run `gh pr list -R <repo> --state open --json number,author,isDraft,reviewDecision,reviewRequests,reviews`. This returns the metadata needed for PR hygiene rules in one call per repo. Group PRs by repo first, then make one call per repo. Include `reviews` (not just `reviewRequests`) so you can detect human reviewer engagement from submitted reviews, not just pending requests (see R-PR-007).

   **Detecting merged/closed PRs (R-PR-008, R-PR-009):** The per-repo `gh pr list --state open` call won't find merged or closed PRs. Instead, use board-side filters to detect these directly:
   - `is:pr is:merged -status:"🎉 Done"` — merged PRs not yet marked Done
   - `is:pr is:closed -status:"🎉 Done"` — closed (not merged) PRs not yet marked Done

   This is more efficient than querying `--state all` per repo (which returns hundreds of results) and directly targets the items that need action.

   **Fallback: individual `gh pr view`** — For PRs not covered by list results (e.g., external repos, or when you need detailed review data like individual reviewer permissions).

   **Avoid: `gh search prs`** — The search index has lag (newly created PRs may not appear) and a 200-result limit that can silently truncate results. Prefer `gh pr list` per-repo which hits the REST API directly and is always up-to-date.

   **Rationale:** The board API and GitHub PR API are separate systems. A full rule sweep touching 70+ items would otherwise require 70+ individual `gh pr view` calls. The per-repo list approach reduces this to ~5–10 calls total (one per repo with open PRs) while being reliable.

   **Limitation:** The per-repo approach requires knowing which repos have PRs on the board. Extract the repo list from the board query results before making API calls.

6. **Use bulk operations when possible.** When applying the same field+value to multiple items, use `bulk_set_board_item_field` instead of individual `set_board_item_field` calls. This is common when applying a rule that affects many items the same way (e.g., setting Cycle Theme on several PRs from the same repo, or moving multiple dependabot PRs from Triage to Todo). Even two items is worth batching — it saves a tool call and resolves field info only once.

7. **Flag unfamiliar Cycle Theme values.** You don't need to proactively audit all Cycle Theme values, but if while processing an item you encounter a Cycle Theme that isn't in the established values list (R-FC-004), flag it. It may be a misspelling or an unauthorized new value.

8. **Reconcile counts before and after bulk operations.** When building a bulk operation from query results, verify the item count matches. For example, if a query returns 25 synapse-sdk items, the bulk call should contain exactly 25 item refs. After applying, re-query to confirm zero items remain. Manually transcribing item IDs from large result sets is error-prone — group items programmatically (e.g., by repo) rather than cherry-picking from a wall of text.

9. **Prefer `list_board_items` with extra fields over individual `get_board_item` calls.** When you need additional fields (e.g., Parent issue, Milestone) for a set of items, re-query with `list_board_items` including those fields rather than calling `get_board_item` on each item individually. One call with `fields: "Repository, Id, Title, Status, Parent issue, Milestone"` replaces N individual lookups. Reserve `get_board_item` for when you need the full detail on a single specific item.

   **Note:** `list_board_items` returns relationship fields (Parent issue, Linked pull requests) as display strings (e.g., `"Cleanup epic"`, not `"dealbot#271"`). To get a durable identifier (repo#number), search for the item by title on the board. Don't treat a title-only string as a dead end — it's enough to look up the item.

10. **Check reviewer permissions before acting on approvals.** Some rules (R-SL-001) require confirming that a reviewer has sufficient access (write or admin) before treating their approval as authoritative. Use `gh api repos/{owner}/{repo}/collaborators/{username}/permission --jq '.permission'` to check — look for `write` or `admin`. An approval from a user with only `read` or `triage` access doesn't unblock a PR for merge. When checking multiple reviewers across repos, batch by repo to minimize API calls (one permission check per unique reviewer-repo pair).

11. **External repos: try once, then move on.** The board includes items from repos outside the `FilOzone` and `filecoin-project` orgs (e.g., `ipshipyard/ipfs-deploy-action`). We typically don't have write access to these repos. When a rule requires modifying the PR itself (assigning, requesting reviewers, etc.), attempt the action once. If it fails with a permissions error (403), report it and move on — don't retry or escalate. Board-level fields (Status, Cycle Theme, etc.) can still be set regardless of repo access since those live on the project board, not the repo.

## How to use

These rules can be applied manually or referenced by an LLM when performing board maintenance tasks. Each rule file describes:

- **When** the rule applies (trigger condition)
- **What** action to take
- **Why** the rule exists

## Rule files

- [sweep-playbook.md](sweep-playbook.md) — Stage-by-stage workflow for a full board sweep
- [pr-hygiene.md](pr-hygiene.md) — Rules for keeping PR items well-formed
- [status-lifecycle.md](status-lifecycle.md) — Rules for status transitions
- [field-completeness.md](field-completeness.md) — Rules for required fields by status
- [future-ideas.md](future-ideas.md) — Ideas for improving the tooling
