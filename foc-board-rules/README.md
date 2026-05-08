# FOC Board Rules

Rules for keeping the [FilOzone FOC project board](https://github.com/orgs/FilOzone/projects/14) consistent and up-to-date. These rules are intended to be applied by an LLM (via the FilOzzy MCP server) or by a human during board triage.

These rules will eventually move to a shared Notion document. For now they live here so they can be iterated on alongside the tooling.

## General behavior

When applying rules (whether by LLM or human):

1. **Improve the rules as you go.** These rules are a living system, not a static checklist. If you notice a rule that is ambiguous, inefficient, missing an edge case, or could be made smarter based on what you've learned during a sweep, update it. If a new pattern emerges that should be a rule, propose it. If an existing rule is wrong or outdated, fix it. The goal is a self-improving system — every sweep should leave the rules better than it found them. When you make a rule change, note what triggered it (e.g., "added after encountering X during sweep").

2. **Report failures and uncertainties.** If a rule cannot be applied (e.g., missing data, ambiguous match, API error) or you're unsure what the correct action is, list the item and the issue rather than skipping silently. Unapplied rules should be surfaced, not swallowed.

3. **Summarize every change.** When setting or changing a field value, always report the old value → new value. For example: `Status: 📌 Triage → 🐱 Todo`. This applies to all mutations, not just status changes.

4. **Always include item titles and hyperlinks.** When listing items (in summaries, flags, or reports), always include the item title alongside the `org/repo#number` reference, and render the reference as a clickable hyperlink (e.g., `[filecoin-pay-explorer#162](https://github.com/FilOzone/filecoin-pay-explorer/issues/162)`). The number alone lacks context, and non-linked references require manual navigation to act on.

5. **Choose query strategy by scope.** When enforcing a *single rule* or verifying a *specific condition*, use targeted board queries (e.g., `is:pr -status:"🎉 Done" no:cycle-theme` to find PRs missing a Cycle Theme). When doing a *full rule sweep* across all rules, fetch all open items in one query (`is:pr -status:"🎉 Done"`) and evaluate each item against every rule — this avoids redundant overlapping queries and is more efficient overall. See `list_board_items` tool docs for filter syntax. **For field-gap checks** (R-FC-005, R-FC-006, R-FC-008), always use `no:field` filter queries (e.g., `no:cycle`, `no:cycle-theme`, `no:assignee`) rather than scanning bulk results — bulk output doesn't clearly distinguish "field is empty" from "field not returned."

6. **Supplement board data with GitHub PR metadata in two phases.** The project board provides field values (Status, Cycle Theme, Milestone, etc.) but not PR-specific metadata like author, draft status, reviewer assignments, or review decisions. Many rules (R-PR-001, R-PR-002, R-PR-005, R-PR-006, R-PR-007, R-SL-001) need this metadata. Use a two-phase approach to keep context lean.

   **Phase 1 — lightweight per-repo fetch.** For each repo that has open PRs on the board, run `gh pr list -R <repo> --state open --json number,author,isDraft,reviewDecision,reviewRequests`. Run calls in parallel — one per repo. **Do NOT include `reviews`** — full review bodies are the main source of context blowout (repos like `filecoin-project/curio` have many open PRs with lengthy review threads, most of which aren't on the board). Phase 1 handles:
   - R-PR-001: `author` → assignee
   - R-PR-002/003/004: `author` → bot/release detection
   - R-PR-005: `isDraft`
   - R-PR-007: `reviewRequests` → identifies Phase 2 candidates (empty `reviewRequests` is ambiguous — pending requests are consumed when a review is submitted, so empty ≠ "no engagement")
   - Initial triage for R-PR-006, R-SL-001, R-SL-007: `reviewDecision` gives the quick signal for which PRs need Phase 2. **Caveat:** `reviewDecision: ""` (empty) is ambiguous — it does NOT mean "no reviews". COMMENTED reviews, approvals from non-CODEOWNERS, and reviews that don't satisfy branch protection all leave `reviewDecision` empty. Never treat empty as "no engagement" — always Phase 2 these PRs if a status change is under consideration.

   **Phase 2 — targeted per-PR deep dive.** For specific PRs identified by cross-referencing Phase 1 data with board status, run `gh pr view -R <repo> <number> --json reviews,commits,reviewRequests`. Phase 2 candidates:
   - **R-PR-006 (status determination):** Non-draft, non-bot PRs in Triage or In Progress — need `reviews` and `commits` to compare last human review timestamp vs last commit timestamp. **This includes PRs with `reviewDecision: ""`** — empty does NOT mean "no reviews"; it means GitHub hasn't produced a formal verdict (e.g., reviews exist but don't satisfy branch protection rules, or only COMMENTED reviews were submitted). Always Phase 2 before changing status on these PRs.
   - **R-SL-001 (approval verification):** PRs where `reviewDecision=APPROVED` but board status is not Approved — need `reviews` to identify the approving reviewer for a permission check. Also check PRs where board says Approved but `reviewDecision` is empty or non-APPROVED — verify the board status is still valid.
   - **R-SL-007 (changes requested):** PRs where `reviewDecision=CHANGES_REQUESTED` in Awaiting Review or Approved — need `reviews` to confirm the reviewer has write access
   - **R-PR-007 (review engagement):** PRs in Awaiting Review with empty `reviewRequests` — **always Phase 2 before flagging**. Empty `reviewRequests` means no *pending* requests, but reviews may already have been submitted (consuming the pending request). Need `reviews` to check for submitted human reviews.

   **Batch all Phase 2 candidates.** Collect the union of candidates from all rules above into a single list before fetching. Run all `gh pr view` calls in parallel — don't fetch per-rule sequentially. This avoids duplicate lookups when the same PR is a candidate for multiple rules (e.g., a PR in Awaiting Review with empty `reviewDecision` and empty `reviewRequests` is a candidate for both R-PR-006 and R-PR-007).

   **Why two phases?** Phase 1 data is ~5 compact fields per PR. Phase 2 adds ~3–8 individual `gh pr view` calls, but only for PRs that actually need deep analysis. This replaces the previous approach of fetching full `reviews` for every open PR in every repo, which consumed thousands of context lines — mostly for PRs not on the board — and led to scanning errors and incomplete follow-through on In Progress candidates.

   **Detecting merged/closed PRs (R-PR-008, R-PR-009):** The per-repo `gh pr list --state open` call won't find merged or closed PRs. Use board-side filters instead:
   - `is:pr is:merged -status:"🎉 Done"` — merged PRs not yet marked Done
   - `is:pr is:closed -status:"🎉 Done"` — closed (not merged) PRs not yet marked Done

   **Avoid: `gh search prs`** — The search index has lag and a 200-result limit that can silently truncate results.

7. **Use bulk operations when possible.** When applying the same field+value to multiple items, use `bulk_set_board_item_field` instead of individual `set_board_item_field` calls. This is common when applying a rule that affects many items the same way (e.g., setting Cycle Theme on several PRs from the same repo, or moving multiple dependabot PRs from Triage to Todo). Even two items is worth batching — it saves a tool call and resolves field info only once.

8. **Flag unfamiliar Cycle Theme values.** You don't need to proactively audit all Cycle Theme values, but if while processing an item you encounter a Cycle Theme that isn't in the established values list (R-FC-004), flag it. It may be a misspelling or an unauthorized new value.

9. **Reconcile counts before and after bulk operations.** When building a bulk operation from query results, verify the item count matches. For example, if a query returns 25 synapse-sdk items, the bulk call should contain exactly 25 item refs. After applying, re-query to confirm zero items remain. Manually transcribing item IDs from large result sets is error-prone — group items programmatically (e.g., by repo) rather than cherry-picking from a wall of text.

10. **Prefer `list_board_items` with extra fields over individual `get_board_item` calls.** When you need additional fields (e.g., Parent issue, Milestone) for a set of items, re-query with `list_board_items` including those fields rather than calling `get_board_item` on each item individually. One call with `fields: "Repository, Id, Title, Status, Parent issue, Milestone"` replaces N individual lookups. Reserve `get_board_item` for when you need the full detail on a single specific item.

   **Note:** `list_board_items` returns relationship fields (Parent issue, Linked pull requests) as display strings (e.g., `"Cleanup epic"`, not `"dealbot#271"`). To get a durable identifier (repo#number), search for the item by title on the board. Don't treat a title-only string as a dead end — it's enough to look up the item.

11. **Check reviewer permissions before acting on approvals.** Some rules (R-SL-001) require confirming that a reviewer has sufficient access (write, maintain, or admin) before treating their approval as authoritative. Use `gh api repos/{owner}/{repo}/collaborators/{username}/permission --jq '.permission'` to check — look for `write`, `maintain`, or `admin`. An approval from a user with only `read` or `triage` access doesn't unblock a PR for merge. When checking multiple reviewers across repos, batch by repo to minimize API calls (one permission check per unique reviewer-repo pair).

12. **Batch-fetch issue metadata with GraphQL.** When a rule sweep identifies multiple issues that need investigation (e.g., R-FC-001 assignee determination), don't look up each issue individually. Instead, use a single batched GraphQL query with aliases to fetch metadata for many issues at once:

    ```graphql
    {
      i1: repository(owner: "FilOzone", name: "dealbot") {
        issue(number: 446) {
          author { login }
          comments(last: 10) { nodes { author { login } body } }
          closedByPullRequestsReferences(first: 5) {
            nodes { number author { login } assignees(first: 3) { nodes { login } } }
          }
          timelineItems(itemTypes: [CROSS_REFERENCED_EVENT], first: 10) {
            nodes { ... on CrossReferencedEvent { source { ... on PullRequest { number author { login } assignees(first: 3) { nodes { login } } } } } }
          }
        }
      }
      i2: repository(owner: "FilOzone", name: "dealbot") {
        issue(number: 464) { ... }
      }
    }
    ```

    **Key fields to fetch:**
    - `author` — who opened the issue
    - `comments` — the comment stream (for inferring DRI)
    - `closedByPullRequestsReferences` — PRs that formally close the issue (`Closes #N`, `Fixes #N`)
    - `timelineItems(itemTypes: [CROSS_REFERENCED_EVENT])` — PRs that reference the issue without using formal closing syntax (e.g., "Related to #N", or just mentioning #N in the PR body)

    Group issues by repo first, then batch up to ~25 per GraphQL request. One call per repo replaces N individual `gh issue view` + N `closedByPullRequestsReferences` lookups.

13. **Use REST API for PR/issue mutations, not `gh pr edit`.** The `gh pr edit` command fails on repos that have (or had) Projects Classic enabled, with a `Projects (classic) is being deprecated` GraphQL error. Instead, use the REST API directly:
    - **Assignees:** `gh api repos/{owner}/{repo}/issues/{number}/assignees -X POST --input - <<< '{"assignees":["user1","user2"]}'`
    - **Reviewers:** `gh api repos/{owner}/{repo}/pulls/{number}/requested_reviewers -X POST --input - <<< '{"reviewers":["user1","user2"]}'`
    - **Note:** Reviewer requests require the user to be a collaborator on the repo. If the request fails with a 422, the user may not have access — report and move on.

14. **External items: skip repo-level mutations.** Items from repos outside the blessed orgs (`FilOzone`, `filecoin-project`) are [external items](status-lifecycle.md#terminology). Skip assignee, milestone, and reviewer mutations entirely for these items — they will always fail. Board-level fields (Status, Cycle Theme, Cycle) can still be set since those live on the project board, not the repo. Don't flag external items for missing assignees or milestones — those are expected persistent gaps, not action items.

15. **Cross-reference with relative links.** When a rule references another rule or section in a different file, use a relative markdown hyperlink (e.g., `[R-FC-004](field-completeness.md#r-fc-004-cycle-theme-defaults-by-repository)`). This removes ambiguity about where a cross-reference lives and helps both humans and LLMs navigate. Within the same file, links are optional since the reader is already there. **Exception:** `sweep-playbook.md` references rules by ID on nearly every line — don't hyperlink rule IDs there. The playbook is a dense operational checklist; adding links would hurt readability. Rule IDs are unique and searchable.

## How to use

These rules can be applied manually or referenced by an LLM when performing board maintenance tasks. Each rule file describes:

- **When** the rule applies (trigger condition)
- **What** action to take
- **Why** the rule exists

## Rule files

- [sweep-playbook.md](sweep-playbook.md) — Stage-by-stage workflow for a full board sweep
- [sweep-agent-prompt.md](sweep-agent-prompt.md) — Prompt for running sweeps in fresh LLM sessions
- [pr-hygiene.md](pr-hygiene.md) — Rules for keeping PR items well-formed
- [status-lifecycle.md](status-lifecycle.md) — Rules for status transitions
- [field-completeness.md](field-completeness.md) — Rules for required fields by status
- [future-ideas.md](future-ideas.md) — Ideas for improving the tooling
