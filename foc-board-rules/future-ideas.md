# Future Ideas

Ideas for improving the FOC board tooling, collected during rule application sessions.

## Augmented PR metadata endpoint in MCP

Add an MCP tool that returns PR metadata (author, isDraft, reviewDecision, reviewRequests) alongside board field data, so the LLM doesn't need to make separate `gh pr list` calls per repo.

**Why it would help:** Currently the board API and GitHub PR API are separate. A full PR rule sweep requires one `gh pr list` call per repo (~10 calls) to get draft status, author, reviewers, etc. An MCP endpoint could do this server-side, reducing tool calls in the LLM conversation (1 MCP call vs ~10 `gh pr list` calls), which saves context window tokens and latency.

**Counterpoint:** The MCP server would still need to make one `gh pr list` call per repo internally — so the total GitHub API calls don't decrease. The benefit is purely in reducing LLM context consumption. Whether that's worth the added complexity is debatable.
