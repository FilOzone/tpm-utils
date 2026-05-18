# Sweep Playbook

Prescribed stage-by-stage workflow for a full board sweep. Each stage uses targeted queries — never fetch all non-Done items in one shot.

Work through stages in order. Complete all actions and reporting for one stage before moving to the next.

## Stage 0: Create sweep workspace

Before any queries, set up the sweep workspace and discover the board API:

1. **Call `get_board_context`** (FilOzzy MCP) to get the board's org, project number, and API base URL.
2. **Set shell variables** from the response:

```bash
SWEEP=/tmp/foc-board-sweep_$(date -u +%Y-%m-%dT%H:%M:%SZ)
mkdir -p "$SWEEP/bin"

# Persist non-sensitive env so scripts and future shell invocations can source it.
# GITHUB_TOKEN is NOT written to disk — scripts resolve it at runtime via `gh auth token`.
# Values from get_board_context — example, not hardcoded:
cat > "$SWEEP/env.sh" << EOF
export SWEEP="$SWEEP"
export API=<API Base URL>/orgs/<org>/projects/<project_number>
export PATH="$SWEEP/bin:\$PATH"
EOF
source "$SWEEP/env.sh"
```

3. **Create helper scripts** for board API calls. These are executable scripts in `$SWEEP/bin/` that source `env.sh` themselves, so they work in any shell invocation:

```bash
cat > "$SWEEP/bin/foc_gh_get" << 'SCRIPT'
#!/usr/bin/env bash
source "$(dirname "$0")/../env.sh"
TOKEN=${GITHUB_TOKEN:-$(gh auth token)}
# GET with auto --data-urlencode for each arg (handles emoji, spaces, etc.)
endpoint="$1"; shift
args=()
for param in "$@"; do
  args+=(--data-urlencode "$param")
done
curl -s -G "$API/$endpoint" \
  -H "Authorization: Bearer $TOKEN" \
  "${args[@]}"
SCRIPT

cat > "$SWEEP/bin/foc_gh_put" << 'SCRIPT'
#!/usr/bin/env bash
source "$(dirname "$0")/../env.sh"
TOKEN=${GITHUB_TOKEN:-$(gh auth token)}
# PUT with JSON body
curl -s -X PUT "$API/$1" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "$2"
SCRIPT

cat > "$SWEEP/bin/foc_timer" << 'SCRIPT'
#!/usr/bin/env bash
echo "$(date +%s) $1" >> "$(dirname "$0")/../timing.log"
SCRIPT

chmod +x "$SWEEP/bin/foc_gh_get" "$SWEEP/bin/foc_gh_put" "$SWEEP/bin/foc_timer"
```

**Timing:** Use `"$SWEEP/bin/foc_timer" "phase1_start"` at the start and end of each phase/stage to capture timestamps. At the end of each stage, print the timing log to help identify whether slowness is API latency, LLM reasoning, or context processing.

**Calling the scripts:** Each Bash tool invocation is a fresh shell — `export`, `PATH`, and shell functions all reset. The scripts persist on disk but PATH won't be set, so **always call them with the absolute path** using `$SWEEP`:

```bash
# At the start of every Bash tool call, set SWEEP (paste the actual path):
SWEEP=/tmp/foc-board-sweep_2026-05-08T...
# Then call scripts with full path:
"$SWEEP/bin/foc_gh_get" items 'query=...' > "$SWEEP/output.json"
```

The scripts source `env.sh` internally so `$API` and `$GITHUB_TOKEN` are handled automatically — you only need `$SWEEP` itself.

4. **Verify the server is running:** Check the port first, then start only if needed. Use dev mode (auto-reloads on code changes):

```bash
# Check if already running
curl -sf "http://127.0.0.1:8080/openapi.json" > /dev/null && echo "Server already running" || {
  cd <repo-root>/github-projects-client
  .venv/bin/github-projects-api-dev &
  sleep 2
}
# Verify
"$SWEEP/bin/foc_gh_get" fields > /dev/null
```

The full API spec is at `<API Base URL>/openapi.json`.

5. **Discover the current cycle** using GraphQL (note: `gh project field-list` shows the Cycle field exists but does **not** list iteration values):

```bash
gh api graphql -f query='{
  organization(login: "<org>") {
    projectV2(number: <project_number>) {
      field(name: "Cycle") {
        ... on ProjectV2IterationField {
          configuration {
            iterations { id title startDate duration }
          }
        }
      }
    }
  }
}' --jq '.data.organization.projectV2.field.configuration.iterations'
```

The first iteration in the list whose date range contains today is the current cycle.

`$SWEEP` holds all working files for this run (avoids collisions with prior sweeps). `$API` is the board REST API prefix — all board queries and mutations go through it via `curl`.

All examples in this playbook use `$SWEEP/` as shorthand for this directory. Board API calls use `"$SWEEP/bin/foc_gh_get"` and `"$SWEEP/bin/foc_gh_put"` (scripts created in step 3). **Always use the full path** — each Bash tool call is a fresh shell, so `PATH` and `export` don't persist. Set `SWEEP=<path>` at the start of each Bash call (the scripts handle `$API` and `$GITHUB_TOKEN` internally via `env.sh`).

## Stage 1: Open PRs

**Goal:** Apply PR hygiene, status lifecycle, and field completeness rules to all open PRs.

**Queries:**
- Board: `is:pr -status:"🎉 Done"` (all non-Done PRs)
- Board: `is:pr is:merged -status:"🎉 Done"` (merged PRs not yet Done — R-PR-008)
- Board: `is:pr is:closed -status:"🎉 Done"` (closed PRs not yet Done — R-PR-009)
- Board (field gaps): `is:pr -status:"🎉 Done" no:assignee`, `is:pr -status:"🎉 Done" no:cycle-theme`, `is:pr -status:"🎉 Done" -status:"🐱 Todo" -status:"📌 Triage" no:cycle` — use these targeted queries for field-gap checks (R-PR-001, R-FC-005, R-FC-006) instead of scanning the bulk PR list. **Process field-gap results on disk, not in context.** Filter out known-handled cases (bots, external items) with jq before reading anything:

  ```bash
  # Example: unassigned PRs — filter out bots and external repos, keep only actionable fields
  jq '[.items[] | select(
    (.Title | test("^chore\\(deps"; "i") | not) and
    (.Repository | IN("ipshipyard/ipfs-deploy-action") | not)
  ) | {repo: .Repository, id: .Id, title: .Title, node_id: .["Node ID"]}]' "$SWEEP/prs_no_assignee.json"
  ```

  Expect ~75% of unassigned PRs to be bots (dependabot, release-please) — the bot PRs are handled by R-PR-001's skip rules and don't need investigation.
- GitHub Phase 1 (lightweight): `gh pr list -R <repo> --state open --json number,author,isDraft,reviewDecision,reviewRequests` (one call per repo — **no `reviews` field**)
- GitHub Phase 2 (targeted): `gh pr view -R <repo> <number> --json reviews,commits,reviewRequests` — only for PRs needing deep analysis (R-PR-006 status determination, R-SL-001 approval verification, R-SL-007 changes-requested check). See general behavior rule 6 for trigger conditions.
- GitHub Phase 2b (R-SL-010 comment check): `gh pr view -R <repo> <number> --json comments,commits` — for Awaiting Review PRs **not already in the main Phase 2 batch**. For PRs already in Phase 2, add `comments` to the existing `--json` field list instead of a separate call. See step 4 below for batching details.

**Rules applied:**
- R-PR-001: Assign unassigned PRs to their author
- R-PR-002: Dependabot PRs → Cycle Theme "Dependency Updates"
- R-PR-003: Dependabot PRs in Triage → Todo
- R-PR-004: Release PRs in Triage → Todo
- R-PR-005: Draft PRs in review/approval statuses → In Progress
- R-PR-006: Non-draft, non-bot PRs in Triage or In Progress → correct status (Awaiting Review, In Progress, or Approved based on review state)
- R-PR-007: Awaiting Review PRs must have human reviewer engagement (flag if not)
- R-PR-008: Merged PRs → Done
- R-PR-009: Closed PRs → Done
- R-SL-001: PRs with merge-authority approval (in Awaiting Review or In Progress) → Approved by reviewer
- R-SL-007: PRs with merge-authority changes requested (in Awaiting Review or Approved) → In Progress
- R-SL-010: Awaiting Review PRs with unaddressed human reviewer comments after last commit → flag for human
- R-SL-006: PRs in "Issue awaiting PR merge" → flag (almost always a mistake)
- R-FC-004: Set Cycle Theme from repo defaults
- R-FC-005: All PRs should have a Cycle Theme
- R-FC-006: In-flight PRs + dependabot/release Todo PRs without a Cycle → current cycle

**Ordering note — Cycle gaps after status changes:** Run the `no:cycle` field-gap queries *after* completing status mutations, not before. PRs that move from Triage/Todo into in-flight statuses (R-PR-003→Todo for dependabot, R-PR-005/006→In Progress or Awaiting Review) also need cycles per R-FC-006, but they won't appear in the pre-mutation `no:cycle` in-flight query. Either re-query after status changes or track the newly in-flight items from your status mutations and include them in the cycle bulk update. (Added after a sweep where cycle gaps for newly in-flight items had to be re-derived manually.)

**Cross-referencing board data with GitHub metadata:**

The main bottleneck in Stage 1 is joining board query results (65+ items) with GitHub Phase 1 metadata (14+ repos). Do this programmatically with `jq`, not by manually scanning JSON walls.

**Fetch board data directly to disk via `curl`.** Board queries go through the REST API — data lands on disk without entering LLM context:

```bash
"$SWEEP/bin/foc_gh_get" items \
  'query=is:pr -status:"🎉 Done"' \
  'fields=Repository,Id,url,Title,Status,Kind,Assignees,Cycle Theme,Node ID' \
  'per_page=100' \
  > "$SWEEP/board_prs.json"
```

`foc_gh_get` wraps each argument in `--data-urlencode` automatically — no manual percent-encoding of emoji statuses or field names with spaces.

The response is standard JSON with an `items` array:

```json
{
  "items": [{"Repository": "FilOzone/dealbot", "Id": "458", "Title": "Fix X", "Status": "⌨️ In Progress", ...}],
  "total_in_page": 62,
  "has_more": true,
  "next_cursor": "opaque_string"
}
```

Process with `jq` as usual: `jq '.items[]' "$SWEEP/board_prs.json"`.

**Pagination: always check `has_more`.** After fetching, check for more pages:

```bash
jq -r '.has_more' "$SWEEP/board_prs.json"  # prints "true" or "false" — do NOT use jq -e in parallel batches (exit code 1 cancels siblings)
```

If true, fetch the next page with the returned `next_cursor` and merge:

```bash
CURSOR=$(jq -r '.next_cursor' "$SWEEP/board_prs.json")
"$SWEEP/bin/foc_gh_get" items \
  'query=is:pr -status:"🎉 Done"' \
  'fields=Repository,Id,url,Title,Status,Kind,Assignees,Cycle Theme,Node ID' \
  'per_page=100' \
  "cursor=$CURSOR" \
  > "$SWEEP/board_prs_p2.json"
jq -s '{"items": [.[].items[]]}' "$SWEEP/board_prs.json" "$SWEEP/board_prs_p2.json" > "$SWEEP/board_prs_all.json"
```

**Tip:** Use `per_page=100` (the maximum) to reduce the number of pages. Most board queries fit in 1-2 pages.

Include `Node ID` in the fields parameter to get project item node IDs (`PVTI_...`), which can be passed to the bulk mutation endpoint to skip per-item re-resolution.

After fetching both datasets:

1. **Filter Phase 1 to board-only PRs.** Extract the PR numbers from the board query, then use `jq` to select only matching entries from each repo's Phase 1 output. This drops the noise (e.g., curio has 18 open PRs but only 3 are on the board).

2. **Produce action lists per rule — to disk, not context.** After the join (step 1), each entry should have both GitHub fields (`.isDraft`, `.reviewDecision`, `.author`) and a `.board_status` field added during the join. Pipe through `jq` selects to identify rule violations and **write results to files** (e.g., `> "$SWEEP/actions_pr005.json"`). Include all automatable rules in a single pass — don't make follow-up queries for rules you could have checked here:
   - R-PR-002/003: `select(.author.is_bot and (.author.login == "app/dependabot"))` — dependabot PRs needing Cycle Theme and/or Triage → Todo. **Note:** `gh pr list --json author` returns `{"login": "app/dependabot", "is_bot": true}`, not `dependabot[bot]` (the `[bot]` form appears in GitHub UI and webhooks, not in the CLI JSON output).
   - R-PR-004: `select(.title | test("^chore\\("; "i")) and (.board_status == "📌 Triage")` — release PRs in Triage → Todo
   - R-PR-005: `select(.isDraft and (.board_status | IN("📌 Triage","🔎 Awaiting review","✔️ Approved by reviewer","⌚️ Issue awaiting PR merge")))`
   - R-PR-006 Phase 2 candidates: `select(.isDraft == false and .author.is_bot == false and (.title | test("^chore\\((deps|master)\\)|^chore: release"; "i") | not) and (.board_status | IN("📌 Triage","⌨️ In Progress")))` — excludes dependabot/release PRs (which should be handled by R-PR-003/004 first). Title-based exclusion is more reliable than `.author.is_bot` since release-please isn't always flagged as a bot.
     - **Phase 2 skip for In Progress + CHANGES_REQUESTED:** PRs already in In Progress with `reviewDecision == "CHANGES_REQUESTED"` will almost always stay In Progress — the only exception is if the author pushed after the review (case 3 in R-PR-006). Check Phase 1 `reviewDecision` first: if it's `CHANGES_REQUESTED` and the PR is already In Progress, skip Phase 2 unless there's a signal the author responded (e.g., a re-requested reviewer in `reviewRequests`). This avoids wasting Phase 2 calls to confirm the status quo.
   - R-SL-007: `select(.reviewDecision == "CHANGES_REQUESTED" and (.board_status | IN("🔎 Awaiting review","✔️ Approved by reviewer")))`
   - R-PR-007 Phase 2 candidates: `select(.board_status == "🔎 Awaiting review" and (.reviewRequests | length == 0))` — empty `reviewRequests` is ambiguous (pending requests are consumed when a review is submitted), so always Phase 2 before flagging
   - R-SL-010 Phase 2b candidates: `select(.board_status == "🔎 Awaiting review")` — **all** Awaiting Review PRs need a comment check. PRs already in the main Phase 2 batch get `comments` added to their existing `--json` fields. The remainder get a lightweight Phase 2b call (`--json comments,commits` only). See step 4.
   
   **Produce all action lists in a single jq pass** rather than sequential per-rule commands:

   ```bash
   jq '{
     pr002: [.[] | select(.author.is_bot and .author.login == "app/dependabot" and .cycle_theme != "Dependency Updates")],
     pr003: [.[] | select(.author.is_bot and .author.login == "app/dependabot" and .board_status == "📌 Triage")],
     pr005: [.[] | select(.isDraft and (.board_status | IN("📌 Triage","🔎 Awaiting review","✔️ Approved by reviewer","⌚️ Issue awaiting PR merge")))],
     pr006: [.[] | select(.isDraft == false and .author.is_bot == false and (.title | test("^chore\\((deps|master)\\)|^chore: release"; "i") | not) and (.board_status | IN("📌 Triage","⌨️ In Progress")))],
     sl007: [.[] | select(.reviewDecision == "CHANGES_REQUESTED" and (.board_status | IN("🔎 Awaiting review","✔️ Approved by reviewer")))],
     pr007: [.[] | select(.board_status == "🔎 Awaiting review" and (.reviewRequests | length == 0))],
     sl010: [.[] | select(.board_status == "🔎 Awaiting review")]
   }' "$SWEEP/joined_prs.json" > "$SWEEP/action_buckets.json"
   ```

   **Read counts first, not contents.** After writing action lists to disk, verify with a single summary command:

   ```bash
   jq 'to_entries[] | "\(.key): \(.value | length)"' "$SWEEP/action_buckets.json"
   ```

   Only read individual items when you need to make a judgment call (e.g., which status to route to). Even then, use jq to select only the fields you need.

3. **Treat `reviewDecision: ""` as ambiguous — but only Phase 2 if a status change is under consideration.** Empty means GitHub produced no formal verdict — not that no reviews exist. But if the PR is already in the correct status and no rule is proposing to move it, Phase 2 is wasted work. For example, a PR in Awaiting Review with pending `reviewRequests` and empty `reviewDecision` is already in the right place — skip it. Only Phase 2 PRs where you'd actually change the status based on the result. See general behavior rule 6.

4. **Batch all Phase 2 candidates, then fetch in parallel.** Collect the union of Phase 2 candidates from step 2 (R-PR-006, R-PR-007, and any `reviewDecision: ""` PRs from step 3 **that need a status change**) into a single list. Then run all `gh pr view` calls in parallel — don't process one rule's candidates, then discover the next rule needs Phase 2 on overlapping PRs. One parallel batch of `gh pr view` calls is faster than sequential per-rule fetches, and avoids duplicate lookups when the same PR is a candidate for multiple rules.

   **Phase 2 + Phase 2b split:** Two tiers of `gh pr view` calls:
   - **Phase 2 (full):** PRs needing review analysis (R-PR-006, R-PR-007, R-SL-001, R-SL-007 candidates) — fetch `reviews,commits,reviewRequests,comments`. Add `comments` to these calls so R-SL-010 is covered for free.
   - **Phase 2b (lightweight):** Remaining Awaiting Review PRs not in the Phase 2 batch — fetch `comments,commits` only (no `reviews`). This is cheaper and only serves R-SL-010.
   
   Run both tiers in a single parallel batch.

   **Never print raw Phase 2 JSON into context.** Reviews can have 20+ entries per PR. After fetching, extract a compact summary to disk, then read only the summaries:

   ```bash
   for f in "$SWEEP"/phase2_*.json; do
     jq '{
       lastCommit: .commits[-1].committedDate,
       lastHumanReview: [.reviews[] | select(.author.login != "copilot-pull-request-reviewer" and (.author.login | startswith("app/") | not)) | .submittedAt] | sort | last,
       hasApproval: ([.reviews[] | select(.state == "APPROVED")] | length > 0),
       approvers: [.reviews[] | select(.state == "APPROVED") | .author.login],
       hasChangesRequested: ([.reviews[] | select(.state == "CHANGES_REQUESTED")] | length > 0),
       changesRequestedBy: [.reviews[] | select(.state == "CHANGES_REQUESTED") | {who: .author.login, when: .submittedAt}],
       reviewRequests: [.reviewRequests[]? | .login // .name],
       humanReviewerCount: ([.reviews[] | select(.author.login != "copilot-pull-request-reviewer" and (.author.login | startswith("app/") | not)) | .author.login] | unique | length),
       humanCommentsAfterLastCommit: ((.commits[-1].committedDate // "") as $lc | [(.comments // [])[] | select(.authorAssociation | IN("OWNER","MEMBER","COLLABORATOR")) | select(.author.login | (startswith("app/") | not)) | select(.createdAt > $lc) | {who: .author.login, association: .authorAssociation, when: .createdAt, snippet: .body[:120]}])
     }' "$f" > "${f%.json}_summary.json"
   done
   ```

   For Phase 2b files (comments+commits only, no reviews), use a simpler extraction:

   ```bash
   for f in "$SWEEP"/phase2b_*.json; do
     jq '(.commits[-1].committedDate // "") as $lc | {
       lastCommit: $lc,
       humanCommentsAfterLastCommit: [.comments[] | select(.authorAssociation | IN("OWNER","MEMBER","COLLABORATOR")) | select(.author.login | (startswith("app/") | not)) | select(.createdAt > $lc) | {who: .author.login, association: .authorAssociation, when: .createdAt, snippet: .body[:120]}]
     }' "$f" > "${f%.json}_summary.json"
   done
   ```

Example — build a joined dataset in one bash call:
```bash
# After fetching board PRs to $SWEEP/board_prs.json via curl,
# and Phase 1 per-repo results to $SWEEP/phase1_*.json:
BOARD_JSON=$(jq '[.items[] | {repo: (.Repository | split("/") | last), number: (.Id | tonumber)}]' "$SWEEP/board_prs.json")
for repo_file in "$SWEEP"/phase1_*.json; do
  repo=$(basename "$repo_file" .json | sed 's/phase1_//')
  jq --argjson board "$BOARD_JSON" --arg repo "$repo" '
    [.[] | select(.number as $n | $board | any(.repo == $repo and .number == $n))]
  ' "$repo_file"
done
```

This gives you a clean, small dataset to reason about — typically 15-30 items instead of 100+.

**Automated vs. flagged:**
- Automated: Status transitions (R-PR-002–009, R-SL-001, R-SL-007), Cycle Theme (R-FC-004/005), Cycle (R-FC-006), assignee (R-PR-001 for PRs)
- Flagged for human: Missing reviewers (R-PR-007), R-SL-001 when permissions are unclear, R-SL-006 PRs in wrong status

## Stage 2: Triage issues

**Goal:** Get issues out of Triage by ensuring they have Cycle Theme and Milestone, and by detecting issues that already have linked PRs.

**Query:** `is:issue status:"📌 Triage"` (include "Linked pull requests" and "Parent issue" in fields)

**Rules applied:**
- R-SL-008: Issues with linked PRs → set status based on PR state (Issue awaiting PR merge, In Progress, or Done), inherit assignee/cycle/milestone
- R-FC-004: Set Cycle Theme from repo defaults
- R-FC-003: Ensure Milestone is set (check parent issue for inheritance)
- R-SL-004: Move to Todo if both Cycle Theme and Milestone are set (and no linked PRs)

**Automated vs. flagged:**
- Automated: Cycle Theme (R-FC-004), Status → Todo (R-SL-004 when both fields are set), linked-PR status transitions (R-SL-008)
- Flagged for human: Missing Milestone when no parent to inherit from

## Stage 3: Non-Done issues — field completeness

**Goal:** Ensure all non-Done issues have Cycle Theme and Milestone.

**Queries:**
- `is:issue -status:"🎉 Done" no:cycle-theme`
- `is:issue -status:"🎉 Done" no:milestone`

**Exclude:** Items with Cycle Theme "zOrganizing Item" (meta/tracking items, not real work).

**Rules applied:**
- R-FC-003: All open issues should have a Milestone
- R-FC-004: Infer Cycle Theme from repository
- R-FC-011: Flag unrecognized Cycle Theme values

**Cycle Theme validation (R-FC-011):** After processing missing Cycle Themes above, run a distinct-values check on all non-Done items that *have* a Cycle Theme set. Query: `-status:"🎉 Done" has:cycle-theme`. Extract distinct Cycle Theme values with jq (`[.items[] | .["Cycle Theme"] // empty] | unique`), diff against the established list in R-FC-004. Flag any unrecognized values with the items that have them and suggest the closest match.

**Automated vs. flagged:**
- Automated: Cycle Theme from repo defaults (R-FC-004)
- Flagged for human: Missing Milestone on items without a parent to inherit from, items in external repos where milestone can't be set, unrecognized Cycle Theme values (R-FC-011)

## Stage 4: Active items — health check

**Goal:** Ensure every active item (see status-lifecycle.md Terminology) has an accountable owner, is actually being worked on, has correct status relative to linked PRs, and has a cycle set when appropriate.

**Queries:**
- `-status:"🎉 Done" -status:"🐱 Todo" -status:"📌 Triage" no:assignee` (unassigned active items)
- `-status:"🎉 Done" -status:"🐱 Todo" -status:"📌 Triage" -status:"⌚️ Issue awaiting PR merge" updated:<YYYY-MM-DD` (stale active items, where date is 2 weeks ago; excludes "Issue awaiting PR merge" — those are waiting on PRs, not stale)
- `is:issue -status:"🎉 Done" -status:"⌚️ Issue awaiting PR merge" has:linked-pull-requests` with "Linked pull requests" field (R-SL-008 — issues with formally linked PRs that might need to move to "Issue awaiting PR merge"). The `has:linked-pull-requests` filter keeps this set small — typically 5-10 items instead of 40+.
- `status:"⌚️ Issue awaiting PR merge" no:cycle` (issues awaiting PR merge without a cycle — inherit from linked PR per R-SL-008, not just R-FC-009)

**Rules applied:**
- R-FC-001: Active items must have an assignee
- R-PR-001: For unassigned PRs, assign to the PR author (skip bots)
- R-SL-008: Not-done issues with linked PRs **where at least one PR is In Progress or later** should be in "Issue awaiting PR merge"; also inherit cycle from linked PR for items already in this status
- R-SL-009: Stale items in In Progress / Awaiting Review / Approved (no update in 2+ weeks on both board and GitHub) should move back to Todo
- R-FC-009: Issues in "Issue awaiting PR merge" with active milestones should have a cycle

**How to investigate unassigned issues (per R-FC-001):**
1. Batch-fetch issue metadata using GraphQL (general behavior rule 12): author, comments, closedByPullRequestsReferences, and timelineItems(CROSS_REFERENCED_EVENT) for linked PRs
2. If a linked PR exists, use the PR's assignee
3. Otherwise, infer from the comment stream (who is actively working on it)
4. If uncertain, propose with justification and flag for human confirmation

**How to check for linked PRs (per R-SL-008):**
1. The `has:linked-pull-requests` query above returns only issues with formally linked PRs — typically 5-10 items.
2. Cross-reference linked PRs with board data to check their status — only move the issue to "Issue awaiting PR merge" if at least one linked PR is In Progress or later (not in Todo/Triage).
3. Also inherit assignee, cycle, and milestone from the linked PR if missing (per R-SL-008).

**How to discover unlinked PRs (per R-SL-008):**
After processing formal linked PRs, do a targeted check for In Progress issues **in the current cycle** that have **no** formal linked PRs — these may have cross-referencing PRs that weren't formally linked. Query the board for `is:issue status:"⌨️ In Progress" no:linked-pull-requests cycle:"<current cycle>"`, exclude zOrganizing Items, then batch-fetch `timelineItems(itemTypes: [CROSS_REFERENCED_EVENT])` via GraphQL (general behavior rule 12) for **only this set**. This is an expensive query with historically low yield (~0 actionable findings per sweep) — limiting to the current cycle keeps the scope small and targets issues most likely to have fresh PRs. See R-SL-008 "Discovering unlinked PRs" for the full procedure. Flag findings for human rather than auto-transitioning.

**Note on cross-reference GraphQL results:** The `... on PullRequest` fragment returns empty objects (`{}`) for cross-references from issues (not PRs). This is expected — filter them out with `select(.title != null)` or add `__typename` to the fragment to distinguish PR refs from issue refs.

**How to report stale items (per R-SL-009):**
1. Exclude zOrganizing Items and "Issue awaiting PR merge" items
2. For each candidate, fetch GitHub `updatedAt` and recent comments — if GitHub shows recent activity, the item is not stale (board fields just haven't been touched)
3. Present a table of confirmed-stale items: item ref + title, current status, board last updated, GitHub last updated, who last updated (from GitHub)
4. Human confirms which items to move back to Todo

**Automated vs. flagged:**
- Automated: PR assignees set to author (R-PR-001), issues with linked PRs where at least one PR is In Progress or later → Issue awaiting PR merge (R-SL-008)
- Flagged for human: Issues where assignee can't be confidently determined, stale active items (R-SL-009), issues awaiting PR merge without a cycle (confirm current cycle assignment)

## Stage 5: Recently-done items — reporting readiness

**Goal:** Ensure recently-completed items have Cycle Theme, Cycle, and Assignee so they show up correctly in periodic reporting.

**Queries — use targeted gap queries, not a bulk fetch:**
- `status:"🎉 Done" updated:>YYYY-MM-DD no:cycle-theme` (missing Cycle Theme)
- `status:"🎉 Done" updated:>YYYY-MM-DD no:cycle` (missing Cycle)
- `status:"🎉 Done" updated:>YYYY-MM-DD no:assignee -cycle-theme:"Dependency Updates"` (missing assignee, excluding dependabot — those are expected to be unassigned per R-PR-001)

where date is 7 days ago. Do **not** fetch all recently-done items first — that returns 100+ items and wastes context. The gap queries surface only the items that need action. (Added after a sweep where the bulk fetch consumed a full page of results before the gap queries found only ~20 actionable items.)

**Cycle Theme validation (R-FC-011):** Also query `status:"🎉 Done" updated:>YYYY-MM-DD has:cycle-theme` to check recently-done items that *have* a Cycle Theme. Extract distinct values with jq (`[.items[] | .["Cycle Theme"] // empty] | unique`), diff against the established list in R-FC-004, and flag any unrecognized values — same process as Stage 3.

**Rules applied:**
- R-FC-008: Recently-done items should have Cycle Theme, Cycle, and Assignee
- R-FC-004: Infer Cycle Theme from repository and title
- R-FC-011: Flag unrecognized Cycle Theme values on recently-done items
- R-PR-001: For unassigned PRs, assign to the PR author. For merged release PRs (bot-authored), assign to the person who merged/approved them. Dependabot PRs can be left unassigned.

**How to investigate unassigned Done issues:**

Batch-fetch issue metadata using GraphQL (general behavior rule 12), including **both** `closedByPullRequestsReferences` and `timelineItems(itemTypes: [CROSS_REFERENCED_EVENT])`. The `closedByPullRequestsReferences` only catches formal closing syntax (`Closes #N`, `Fixes #N`). PRs that reference an issue informally (e.g., "Addresses #765" in the PR body) show up only as cross-referenced timeline items. Priority order for inferring assignee:

1. `closedByPullRequestsReferences` → use the closing PR's assignee/author
2. `timelineItems(CROSS_REFERENCED_EVENT)` → if a cross-referencing PR is merged, use its assignee/author (merged = likely the actual fix)
3. Comment stream / issue author (fallback)

If uncertain, propose with justification and flag for human confirmation.

**Automated vs. flagged:**
- Automated: Cycle Theme from repo defaults (R-FC-004), Cycle set to current cycle, PR assignees set to author (or merger for release PRs)
- Flagged for human: Issues without assignees (propose assignee per priority order above), items where Cycle Theme can't be inferred from R-FC-004, unrecognized Cycle Theme values on recently-done items (R-FC-011)

**How to investigate unassigned Done PRs:**

Batch-fetch PR authors using a single GraphQL query instead of sequential `gh api` calls — the same pattern as general behavior rule 12, but for pull requests:

```graphql
{
  r1: repository(owner: "FilOzone", name: "infra") {
    p173: pullRequest(number: 173) { author { login } }
    p174: pullRequest(number: 174) { author { login } }
    p175: pullRequest(number: 175) { author { login } }
  }
  r2: repository(owner: "FilOzone", name: "tpm-utils") {
    p42: pullRequest(number: 42) { author { login } }
  }
}
```

Group PRs by repo, batch up to ~25 per request. One call per repo replaces N individual `gh api repos/.../pulls/N` lookups. For release PRs (bot-authored), add `mergedBy { login }` to the fragment to find who merged.

**Note:** Use the GitHub API (`gh api repos/{owner}/{repo}/issues/{number}/assignees`) for assignments — `gh pr edit --add-assignee` may fail on repos with Projects Classic enabled. For release PRs, use `mergedBy.login` from the GraphQL response (or `gh api repos/{owner}/{repo}/pulls/{number} --jq '.merged_by.login'`) to find who merged.

## Stage 6: Effort estimation gaps

**Goal:** Surface issues in active milestones that are missing a Dev Days Estimate, so effort remaining and work completed calculations are accurate.

**Rules applied:**
- R-FC-010: Issues in active milestones should have a Dev Days Estimate

**Queries:** See R-FC-010 for the full filter syntax (open issues + recently-done issues).

**Fields to include:** Repository, Id, Title, Status, Assignees, Milestone, Cycle Theme

**Output:** Present results as a single markdown table sorted by repository, suitable for pasting into Slack. Every item reference should be a hyperlink (e.g., `[dealbot#209](https://github.com/FilOzone/dealbot/issues/209)`).

```
| Item | Title | Status | Assignee | Milestone | Cycle Theme |
|------|-------|--------|----------|-----------|-------------|
| [dealbot#209](https://github.com/FilOzone/dealbot/issues/209) | We need to be able to view jobs | 🎉 Done | SgtPooki | M4.2: mainnet GA | Dealbot |
```

**Automated vs. flagged:**
- This stage is **report-only** — no automated mutations. The human decides whether to backfill estimates or accept the gaps.
