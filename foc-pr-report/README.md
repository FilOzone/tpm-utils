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

**What this tool does:** For each PR in the report, named-user **reviewer** counts use the union of (1) requested user reviewers and (2) human users who submitted at least one non-`PENDING` pull request review (excluding the PR author). For the synthetic **empty** reviewer row, the tool uses board-aligned emptiness semantics: any requested non-user reviewer (for example teams) or submitted non-user review (for example bots) is treated as non-empty, so the row aligns with the `no:reviewers` drill-down links.

## Output tables

1. **PR count by individual** — rows are GitHub users × board status; assignee and reviewer counts match the semantics above. Rows labeled **empty** (after all named users) count PRs with **no assignee** in the **assignee** column and PRs with no board-visible reviewer activity in the **reviewer** column (including non-user actors), aligned with the `no:reviewers` filter. The **assignee** cell links add `no:assignee`; the **reviewer** cell links add `no:reviewers`. The **empty** label itself links to the base filter only. For **named users** only, a **👀** may appear after the **reviewer** count link (not inside it) when status is **Awaiting review** and that count is non-zero, and a **🏁** after the **assignee** count link when status is **Approved by reviewer** and that count is non-zero; a legend under the table explains both.
2. **PR count by repository and status** — rows are repositories (`owner/repo`), columns are statuses present in the filtered set, plus a **Total** column (row sums) and **Total** row (column sums). Repository names link to the base filter plus `repo:owner/name`. Status column headers link to the base filter plus `status:"…"` only. Each non-zero cell links to that repo and status combined. The **Total** column header and the bottom-right grand total link to the base filter only; row totals link like the repo row; the total row’s status cells link like the status column headers.

## Slack “review / merge” nudge

Use this when you want a short team message (e.g. Slack) instead of pasting the Markdown tables. Regenerate the report, then use the **prompt** below with an assistant or drop the rules into your own template.

### 1. Regenerate the report

From this directory:

```bash
GITHUB_TOKEN=$(gh auth token) uv run foc-pr-report
```

Or write to a file and paste its **PR count by individual** section into the prompt.

### 2. Prompt template (paste report + fill in gist URL)

Copy everything in the fence below. Replace `PASTE_REPORT_HERE` with the tool output (at least through the person table and legend). Replace `GIST_URL` with your published gist for the full report, if you use one.

```text
You are helping draft a short team message for Slack about FOC Project 14 PRs (View 2).

Input: the Markdown output from `foc-pr-report` (person table + optional matrix totals). Here it is:

PASTE_REPORT_HERE

Write a message that:

1. States that we have many open PRs in **Awaiting review** and **Approved by reviewer** (use the matrix totals from the report if present; otherwise infer from the person table). Ask people to clear review/merge duty before taking on more in-progress or new work.

2. Under a heading like **By person**, emit a **bulleted list** (•) sorted alphabetically by GitHub login. Skip the synthetic **empty** row. Skip people who only appear in **In Progress** / **Triage** with no Awaiting-review or Approved action below.

3. For each **named user**, include **only** these link types, using the **exact** `filterQuery` URLs from the report cells (keep hyperlinks as Markdown `[label](url)` for copy-paste):
   - **Awaiting your review (n)** — use the **reviewer** column link for the row where **state** is **🔎 Awaiting review** and the cell has the 👀 marker (or equivalently non-zero reviewer count on that row). Use the count *n* from that cell. Label must be exactly `Awaiting your review (n)`.
   - **Approved by your reviewers (n)** — use the **assignee** column link for the row where **state** is **✔️ Approved by reviewer** and the cell has the 🏁 marker (or non-zero assignee count on that row). Use the count *n* from that cell. Label must be exactly `Approved by your reviewers (n)`.

4. **Do not** include a separate bullet fragment like “Awaiting review · assignee (n)” when the same person also has an **Awaiting your review** link for that lane. If the person has **only** assignee work in **Awaiting review** (reviewer count 0, assignee count > 0 on that status), include one link labeled **Your PRs in Awaiting review (n)** using the **assignee** column URL for that row.

5. Separate multiple links for the same person with ` · ` (space middle dot space).

6. End with a line: **Full report:** [description](GIST_URL) — use a sensible description (e.g. date + “FOC PRs”).

Tone: concise, friendly, imperative. No Markdown tables in the Slack body.
```

## Links

[View 2](https://github.com/orgs/FilOzone/projects/14/views/2) `filterQuery` values use the same base filter as the tool (`is:pr` excluding Done/Todo), plus qualifiers per cell as described above.
