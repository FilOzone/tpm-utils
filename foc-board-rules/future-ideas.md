# Future Ideas

Ideas for improving the FOC board tooling, collected during rule application sessions.

## Augmented PR metadata endpoint in MCP

Add an MCP tool that returns PR metadata (author, isDraft, reviewDecision, reviewRequests) alongside board field data, so the LLM doesn't need to make separate `gh pr list` calls per repo.

**Why it would help:** Currently the board API and GitHub PR API are separate. A full PR rule sweep requires one `gh pr list` call per repo (~10 calls) to get draft status, author, reviewers, etc. An MCP endpoint could do this server-side, reducing tool calls in the LLM conversation (1 MCP call vs ~10 `gh pr list` calls), which saves context window tokens and latency.

**Counterpoint:** The MCP server would still need to make one `gh pr list` call per repo internally — so the total GitHub API calls don't decrease. The benefit is purely in reducing LLM context consumption. Whether that's worth the added complexity is debatable.

## Expose built-in item properties in list_board_items

The board REST API returns built-in properties like `updated_at` and `creator` on each item, but `list_board_items` only surfaces custom project fields (Status, Cycle Theme, etc.) and a few display fields (Repository, Id, Title). Expose `updated_at` and `creator` as requestable fields so reports like R-FC-010 (Dev Days Estimate gaps) can include "last updated" and "created by" without supplemental GitHub API calls.

**Triggered by:** Stage 6 (effort estimation gaps) wants to show when each item was last updated and who created it, but neither field is available from the tool today.
