# Future Ideas

Ideas for improving the FOC board tooling, collected during rule application sessions.

## Augmented PR metadata endpoint in MCP

Add an MCP tool (or option on `list_board_items`) that returns GitHub PR metadata (author, isDraft, reviewDecision, reviewRequests) alongside board field data, so the LLM doesn't need to make separate `gh pr list` calls per repo.

**Why it would help:** In the first real sweep (2026-05-04), the `gh pr list` calls with full `reviews` bodies consumed thousands of context lines — mostly for PRs not on the board (e.g., curio has 15+ open PRs but only 1 on the board). This caused scanning errors, missed items, and incomplete follow-through on R-PR-006 candidates. The two-phase approach (general behavior rule 6) mitigates this, but the MCP server could do even better:
- **Filter to board PRs only.** The server knows which items are PRs and which repos they're in. It could query GitHub for just those PRs, not every open PR in the repo.
- **Return normalized summaries.** Instead of raw review bodies, return compact fields: `isDraft`, `author`, `reviewDecision`, `reviewRequests` (names only), and optionally `lastCommitDate` / `lastHumanReviewDate` for R-PR-006 timestamp comparisons.
- **Eliminate cross-referencing.** The LLM currently has to mentally join board data with GitHub data across 70+ items. The MCP server could return a single unified view.

**Estimated impact:** Would replace ~10 parallel `gh pr list` calls + ~5 targeted `gh pr view` calls with a single MCP call, and eliminate the most error-prone step of the sweep (cross-referencing two data sources across 70 items).

## Async result refs for large query results

Add an async mode to `list_board_items` (and `list_board_view_items`) where the server stores results and returns only a lightweight reference, rather than streaming the full dataset through the LLM's token pipeline.

**The problem:** MCP tool results flow through the LLM context as tokens. When a board query returns 61 PRs, the full JSON blob (~15K characters) is tokenized as input into the agent's context. The agent then re-emits that entire blob as a parameter to the Write tool to save it to disk. The same data is tokenized twice — once in, once out — and neither pass involves the agent actually reasoning about the content. It's pure passthrough. Multiply by 6-7 board queries per sweep, and you're burning significant token I/O on data that just needs to get to a file.

The fundamental problem: **data must pass through the LLM context as a waypoint to reach disk.** There is no "pipe MCP output directly to a file" path in the MCP protocol.

**Proposed design:**

1. Agent calls `list_board_items(query='...', fields='...', async=true)`
2. Server executes the query, stores results (on disk or in memory), auto-paginates to collect all pages, and returns only a summary:
   ```json
   {"ref": "abc123", "total_items": 62, "endpoint": "/results/abc123"}
   ```
3. Agent fetches the full data via Bash, bypassing context entirely:
   ```bash
   curl -s <server>/results/abc123 > $SWEEP/board_prs.json
   ```
4. Agent processes with `jq` as usual.

**Why not just write to disk from the server?** The MCP server will eventually be external (not running on the agent's machine), so it can't write to the agent's local filesystem. The ref-based approach works regardless of where the server runs.

**Why not a more compact format (TSV, columnar JSON)?** Format optimization helps at the margins, but the core issue is architectural: the data shouldn't pass through the LLM context at all. A compact format still gets tokenized twice (in as tool result, out as Write parameter). The ref pattern reduces the token footprint to ~30 tokens regardless of result size.

**Estimated impact:** Would eliminate ~30K+ tokens of I/O per sweep (conservative — just the main PR query round-trip; more with all board queries). Also eliminates the Write-tool workarounds currently documented in the sweep playbook (Stage 0 workspace, "immediately Write to disk" instructions, pagination merge steps).

## Expose built-in item properties in list_board_items

The board REST API returns built-in properties like `updated_at` and `creator` on each item, but `list_board_items` only surfaces custom project fields (Status, Cycle Theme, etc.) and a few display fields (Repository, Id, Title). Expose `updated_at` and `creator` as requestable fields so reports like R-FC-010 (Dev Days Estimate gaps) can include "last updated" and "created by" without supplemental GitHub API calls.

**Triggered by:** Stage 6 (effort estimation gaps) wants to show when each item was last updated and who created it, but neither field is available from the tool today.

