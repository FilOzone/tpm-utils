# Future Ideas

Ideas for improving the FOC board tooling, collected during rule application sessions.

## Augmented PR metadata endpoint in REST API

Add a REST API endpoint (or option on `GET .../items`) that returns GitHub PR metadata (author, isDraft, reviewDecision, reviewRequests) alongside board field data, so the agent doesn't need to make separate `gh pr list` calls per repo.

**Why it would help:** In the first real sweep (2026-05-04), the `gh pr list` calls with full `reviews` bodies consumed thousands of context lines — mostly for PRs not on the board (e.g., curio has 15+ open PRs but only 1 on the board). This caused scanning errors, missed items, and incomplete follow-through on R-PR-006 candidates. The two-phase approach (general behavior rule 6) mitigates this, but the REST API could do even better:
- **Filter to board PRs only.** The server knows which items are PRs and which repos they're in. It could query GitHub for just those PRs, not every open PR in the repo.
- **Return normalized summaries.** Instead of raw review bodies, return compact fields: `isDraft`, `author`, `reviewDecision`, `reviewRequests` (names only), and optionally `lastCommitDate` / `lastHumanReviewDate` for R-PR-006 timestamp comparisons.
- **Eliminate cross-referencing.** The agent currently has to join board data with GitHub data across 70+ items via `jq`. The server could return a single unified view.

**Estimated impact:** Would replace ~10 parallel `gh pr list` calls + ~5 targeted `gh pr view` calls with a single API call, and eliminate the most error-prone step of the sweep (cross-referencing two data sources across 70 items).

## ~~Async result refs for large query results~~ — Solved

**Status: Solved by the REST API architecture.** The REST API server is accessed via `curl`, so data goes directly to disk (`curl ... > $SWEEP/file.json`) without ever entering LLM context. This eliminates the MCP context-passthrough problem entirely — no async refs needed. The Write-tool workarounds that were documented in the sweep playbook are no longer necessary.

## Remove `format=compact` from the REST API

The compact columnar format (`format=compact`) was designed for MCP responses that land in LLM context, where token count matters. With the REST API, data goes to disk via curl and gets processed by jq — standard JSON is easier to work with (`jq '.items[]'` vs the columnar reconstruction dance) and disk space isn't a constraint. If no consumer depends on it, remove it from the API and the underlying `formats.py` module.

**Triggered by:** Reviewing the value of each feature against GitHub's own tooling (project tenet). The compact format was a context-window optimization that no longer applies when data bypasses LLM context entirely.

## Remove `GET /fields/{name}/options` endpoint

`gh project field-list --format json` returns field names and option names cleanly. The `/fields/{name}/options` endpoint doesn't provide unique value over GitHub's own tooling. Per the [project tenet](../github-projects-client/README.md#project-tenet-prefer-github-supported-tools), it should be retired.

**Triggered by:** Comparing the endpoint against `gh project field-list` output — both return the same information, and the `gh` version is already available to any agent with CLI access.

## Expose built-in item properties in REST API list endpoint

The board REST API returns built-in properties like `updated_at` and `creator` on each item internally, but `GET .../items` only surfaces custom project fields (Status, Cycle Theme, etc.) and a few display fields (Repository, Id, Title). Expose `updated_at` and `creator` as requestable fields so reports like R-FC-010 (Dev Days Estimate gaps) can include "last updated" and "created by" without supplemental GitHub API calls.

**Triggered by:** Stage 6 (effort estimation gaps) wants to show when each item was last updated and who created it, but neither field is available from the API today.

