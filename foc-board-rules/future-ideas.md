# Future Ideas

Ideas for improving the FOC board tooling, collected during rule application sessions.

## Augmented PR metadata endpoint in MCP

Add an MCP tool (or option on `list_board_items`) that returns GitHub PR metadata (author, isDraft, reviewDecision, reviewRequests) alongside board field data, so the LLM doesn't need to make separate `gh pr list` calls per repo.

**Why it would help:** In the first real sweep (2026-05-04), the `gh pr list` calls with full `reviews` bodies consumed thousands of context lines — mostly for PRs not on the board (e.g., curio has 15+ open PRs but only 1 on the board). This caused scanning errors, missed items, and incomplete follow-through on R-PR-006 candidates. The two-phase approach (general behavior rule 6) mitigates this, but the MCP server could do even better:
- **Filter to board PRs only.** The server knows which items are PRs and which repos they're in. It could query GitHub for just those PRs, not every open PR in the repo.
- **Return normalized summaries.** Instead of raw review bodies, return compact fields: `isDraft`, `author`, `reviewDecision`, `reviewRequests` (names only), and optionally `lastCommitDate` / `lastHumanReviewDate` for R-PR-006 timestamp comparisons.
- **Eliminate cross-referencing.** The LLM currently has to mentally join board data with GitHub data across 70+ items. The MCP server could return a single unified view.

**Estimated impact:** Would replace ~10 parallel `gh pr list` calls + ~5 targeted `gh pr view` calls with a single MCP call, and eliminate the most error-prone step of the sweep (cross-referencing two data sources across 70 items).

## Expose built-in item properties in list_board_items

The board REST API returns built-in properties like `updated_at` and `creator` on each item, but `list_board_items` only surfaces custom project fields (Status, Cycle Theme, etc.) and a few display fields (Repository, Id, Title). Expose `updated_at` and `creator` as requestable fields so reports like R-FC-010 (Dev Days Estimate gaps) can include "last updated" and "created by" without supplemental GitHub API calls.

**Triggered by:** Stage 6 (effort estimation gaps) wants to show when each item was last updated and who created it, but neither field is available from the tool today.
