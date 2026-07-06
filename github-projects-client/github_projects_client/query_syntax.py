"""Query syntax reference for GitHub Projects v2 filter syntax.

Single source of truth — used by the REST API endpoint descriptions
and the MCP coordinator's get_board_context output.
"""

QUERY_SYNTAX_REFERENCE = """
The `query` parameter uses GitHub Projects v2 filter syntax —
the same syntax as the board UI search bar. It is passed directly to the REST API
endpoint `GET /orgs/{org}/projectsV2/{project_number}/items?q=...`

Docs: https://docs.github.com/en/issues/planning-and-tracking-with-projects/customizing-views-in-your-project/filtering-projects

### Custom Project Fields (use kebab-case of the field display name)
- `status:"⌨️ In Progress"` — match a Status value
- `cycle-theme:"Contract Upgrade"` — match a Cycle Theme value
- `dev-days-estimate:>1` — numeric comparison
- `cycle:"202604-2"` — match iteration by title
- Use `gh project field-list` to discover field names.

### Item Type & State
- `is:issue` / `is:pr`
- `is:open` / `is:draft` / `is:closed` / `is:merged`

### People
- `assignee:rjan90` — assigned to user
- `assignee:rjan90,biglep` — assigned to either (OR)
- `reviewers:biglep` — PR reviewer
- `assignee:@me` — current authenticated user

### Milestones
- `milestone:"M4.2: mainnet GA"` — match a Milestone value

### Repository
- `repo:FilOzone/dealbot` — items from a specific repo
- `repo:FilOzone/dealbot,filecoin-project/curio` — items from either repo

### Labels
- `label:bug` / `label:"help wanted"` — labels with spaces need quotes

### Time-Based — prefer `updated:` over `last-updated:`

GitHub Projects introduced built-in `Created` / `Updated` / `Closed` timestamp
fields on 2026-05-15 (see https://github.blog/changelog/2026-05-15-timestamp-fields-in-github-projects/),
and the docs now recommend the `updated:` family. The older `last-updated:Ndays`
syntax still works on most queries but has known bugs for date ranges greater
than ~17 days (community discussion #108039). Use `updated:` for anything new.

**Recommended — `updated:` with comparison operators:**
- `updated:@today` — items updated today
- `updated:>@today-7d` — items updated within the last 7 days
- `-updated:>@today-2w` — items NOT updated in the last 2 weeks (stale)
- `updated:>2026-04-01` — items updated after a specific date
- `updated:2026-04-01..2026-05-01` — items updated within a date range

**Legacy — `last-updated:` (avoid for new queries):**
- `last-updated:1days` — items NOT updated within 1 day (stale; counterintuitive — no negation)
- `-last-updated:1days` — items updated within the last day (recent)
- Known to silently return zero results for windows beyond ~17 days.

To find RECENTLY updated items: `updated:>@today-Nd` or `updated:>YYYY-MM-DD`.
To find STALE items (not updated recently): `-updated:>@today-Nd`.

### Relationships
- `blocking:FilOzone/dealbot#470` — items blocking a specific issue
- `blocked-by:FilOzone/filecoin-pay-explorer#77` — items blocked by a specific issue
- `parent-issue:FilOzone/synapse-sdk#3` — sub-issues of a parent

### Close Reason
- `reason:completed` / `reason:"not planned"`

### Text Search
- `"search text"` — free text search across fields
- `title:"*API*"` — title contains text
- `title:API*` — prefix matching (wildcards)

### Presence / Absence
- `has:assignee` — items with at least one assignee
- `has:milestone` — items with a milestone set
- `has:"cycle-theme"` — items where Cycle Theme IS set
- `has:linked-pull-requests` — issues with formally linked PRs
- Works with any project field name (use kebab-case).
- `no:milestone` — items with no milestone set
- `no:assignee` — items with no assignee

### Negation (prefix any filter with -)
- `-status:"🎉 Done"` — exclude Done items
- `-assignee:rjan90` — not assigned to rjan90
- `-is:draft` — exclude drafts

### Combining Filters (space-separated = implicit AND)
- `is:pr assignee:rjan90 -status:"🎉 Done"`
- `cycle-theme:"Contract Upgrade" -updated:>@today-1d`

### OR (comma-separated values within one filter)
- `assignee:rjan90,biglep`
- `status:"⌨️ In Progress","🔍 Review"`

### Quoting
Use double quotes around values with spaces or special chars:
- `status:"⌨️ In Progress"` / `milestone:"M4.2: mainnet GA"`

### Tips — prefer targeted queries
When looking for items that need a specific fix (e.g., missing field, wrong status),
build the query to match the rule condition directly rather than fetching all items.

Examples:
- `is:pr -status:"🎉 Done" -has:"cycle-theme"` → PRs missing Cycle Theme
- `is:pr no:assignee -status:"🎉 Done"` → unassigned open PRs
- `is:pr status:"📌 Triage"` → PRs still in Triage
- `is:pr is:merged -status:"🎉 Done"` → merged PRs not yet marked Done

NOTE: Invalid filters return 0 results (they are not silently ignored).
Default query: `-status:"🎉 Done"` (excludes completed items).
""".strip()
