# FOC PR report (Project 14)

Generates a Markdown table of pull requests on [FilOzone Project 14](https://github.com/orgs/FilOzone/projects/14), grouped by GitHub user and board **Status**. PRs in **Done** or **Todo** are excluded. All PR states (open/closed/draft) are included if they remain on the board with a qualifying status.

Requested **team** reviewers are not attributed to user rows (same as other tpm-utils tooling).

## Token

You need credentials that can read FilOzone org data and **GitHub Projects (classic + v2)**. The GraphQL API requires the **`read:project`** scope. (`repo` and `read:org` alone are not enough.)

### GitHub CLI (recommended)

1. Ensure Project scope is on your login (default host `github.com` must be an account that can see FilOzone Project 14):

```bash
gh auth refresh -s read:project
```

2. Pass the token to this tool:

```bash
GITHUB_TOKEN=$(gh auth token) uv run foc-pr-report -o foc-report.md
```

Or export it for the shell session:

```bash
export GITHUB_TOKEN=$(gh auth token)
uv run foc-pr-report
```

If you see an **INSUFFICIENT_SCOPES** / **read:project** error, run `gh auth refresh -s read:project` (or `gh auth login` and include project read when asked). For org-owned projects, accept **organization** access for FilOzone if prompted.

### Personal access token

Alternatively set `GITHUB_TOKEN` to a classic PAT from [GitHub → Settings → Developer settings → Tokens](https://github.com/settings/tokens) and enable **`read:project`** (plus **`read:org`** and repo read as needed).

## Run with uv

```bash
cd foc-pr-report
uv sync
GITHUB_TOKEN=$(gh auth token) uv run foc-pr-report -o foc-report.md
```

Or print to stdout:

```bash
GITHUB_TOKEN=$(gh auth token) uv run foc-pr-report
```

## How fetching works

The tool uses the **REST** [List project items](https://docs.github.com/en/rest/projects/items#list-items-for-an-organization-owned-project) endpoint with the same **`q`** filter string as the board (for example `is:pr` plus `-status:"…"`). GitHub applies that filter **server-side**, so only matching cards are returned and paginated—unlike listing the entire project via GraphQL when the board is very large.

### Reviewer column vs GitHub APIs

The **project table’s “Reviewers” column** in the GitHub UI is a single place to show review-related people, but the data comes from more than one backend concept:

| Concept | What it is | Typical API |
|--------|------------|-------------|
| **Requested reviewers** | Users (or teams) currently asked to review **this PR**; this is what powers “awaiting review” for those names. | On each card, the REST payload exposes this as `requested_reviewers` (often the same as [`requested_reviewers` on the pull request](https://docs.github.com/en/rest/pulls/pulls#get-a-pull-request)). |
| **Submitted pull request reviews** | A formal review action: **Comment**, **Approve**, or **Request changes** (and related states), as listed under [List reviews for a pull request](https://docs.github.com/en/rest/pulls/reviews#list-reviews-for-a-pull-request). A **COMMENTED** submission is still a review, not the same as a random **issue comment** on the conversation tab. | `GET /repos/{owner}/{repo}/pulls/{pull_number}/reviews` |

Those two can diverge. For example, you might **submit a review** (so the UI can list you under **Reviewers**), while newer requests go to other people—so you are **no longer** in `requested_reviewers`, but you still appear on the board and match filters like a bare `username`.

**What this tool does:** For each PR in the report, the **reviewer** counts use the **union** of (1) `requested_reviewers` on the card and (2) human users who have submitted at least one non-`PENDING` pull request review (same review list as above), **excluding the PR author**. That is meant to stay close to how filtering by person on the board behaves and what you see in the **Reviewers** column—not “everyone who left an issue comment.”

## Output tables

1. **Workload by person** — rows are GitHub users × board status; assignee and reviewer counts match the semantics above. Rows labeled **empty** (after all named users) count PRs with **no assignee** in the **assignee** column and PRs with **no reviewer** in the **reviewer** column (same reviewer union as above—only user logins; team-only review requests still show as empty here). The **assignee** cell links add `no:assignee`; the **reviewer** cell links add GitHub’s `review:none` (no submitted pull request reviews), which can differ slightly from this row’s count when a user is requested but has not submitted a review yet. The **empty** label itself links to the base filter only.
2. **PR count by repository and status** — rows are repositories (`owner/repo`), columns are statuses present in the filtered set, plus a **Total** column (row sums) and **Total** row (column sums). Repository names link to the base filter plus `repo:owner/name`. Status column headers link to the base filter plus `status:"…"` only. Each non-zero cell links to that repo and status combined. The **Total** column header and the bottom-right grand total link to the base filter only; row totals link like the repo row; the total row’s status cells link like the status column headers.

## Links

[View 2](https://github.com/orgs/FilOzone/projects/14/views/2) `filterQuery` values use the same base filter as the tool (`is:pr` excluding Done/Todo), plus qualifiers per cell as described above.
