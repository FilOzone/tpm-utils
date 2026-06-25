# FOC review stats

Per-contributor PR creation and review counts across configured GitHub orgs and
repos. The intent is to surface review balance and encourage mutual payment of
review costs.

Contributors are discovered from configured GitHub teams plus a small list of
extra logins. Display names are pulled from GitHub. Anyone in scope who had
zero activity in the window does not appear.

## Prerequisites

You need three things installed:

1. **`uv`** (the Python project manager). One-line install:
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
   See [docs.astral.sh/uv](https://docs.astral.sh/uv/) for other platforms.

2. **`gh`** (the GitHub CLI), logged in:
   ```bash
   gh auth login
   ```
   Your GitHub account must be able to read the orgs/teams listed in
   [`team.toml`](team.toml). For the default config that means membership in
   FilOzone and filecoin-project.

3. **A GitHub token** with `read:org` and `repo` scopes. The easiest source is
   the `gh` CLI:
   ```bash
   export GITHUB_TOKEN=$(gh auth token)
   ```
   If `gh auth status` shows missing scopes, run `gh auth refresh -s read:org`.

For the Google Docs paste workflow (Linux/X11), also install **`xclip`**:
```bash
sudo apt install xclip   # Debian/Ubuntu
```

## Quick start

```bash
cd tpm-utils/foc-review-stats
export GITHUB_TOKEN=$(gh auth token)
uv run foc-review-stats
```

That prints the last six weeks of activity to stdout as a table. First run takes
a minute (downloads dependencies, scans ~70-100 repos).

## Common tasks

```bash
# Last week instead of six weeks.
uv run foc-review-stats --weeks 1

# Window starting from a specific date.
uv run foc-review-stats --since 2026-04-01

# Historical window, inclusive of both dates.
uv run foc-review-stats --since 2026-03-01 --until 2026-03-31

# Markdown table for Slack or a wiki.
uv run foc-review-stats --format md -o stats.md

# HTML table with light red/green ratio shading, sized for Google Docs paste.
uv run foc-review-stats --format html -o stats.html

# Adjust the "top N" reviewers/reviewees shown per row (default 3).
uv run foc-review-stats --top 5
```

Run `uv run foc-review-stats --help` for every flag.

### Pasting the HTML output into Google Docs (Linux/X11)

```bash
xclip -selection clipboard -t text/html -i stats.html
```

Then **Ctrl+Shift+V** in the doc. Cell shading and the `<h2>` heading are
preserved; the `<h2>` adopts the doc's own H2 style on paste.

## Configuring who appears

Open [`team.toml`](team.toml) in your editor. It has three sections.

### `[scope]` — which repos to scan

```toml
[scope]
orgs = ["FilOzone", "filecoin-project"]
extra_repos = ["curiostorage/filstream", "hugomrdias/iso-repo"]
```

Every non-archived repo in `scope.orgs` that has been pushed within the
analysis window (plus a 6-week buffer) is scanned. `scope.extra_repos` adds
specific repos outside those orgs. Add or remove repos to widen or narrow the
scope.

### `[team]` — which contributors count

```toml
[team]
github_teams = [
    "FilOzone/filoz-fs",
    "filecoin-project/curio",
]
extra_members = ["hugomrdias", "juliangruber"]
```

Members of any listed GitHub team are in scope. `extra_members` adds logins
that are not in any of those teams (typically external contractors).

To add a new contractor: append their GitHub login to `extra_members`.
To bring a new GitHub team into scope: append `"org/team-slug"` to
`github_teams`.

Set `github_teams = []` and `extra_members = []` to disable team filtering
entirely. The report then includes every active contributor.

### `[ignored]` — always exclude

```toml
[ignored]
logins = ["FilOzzy", "magik6k", "redpanda-f"]
```

Logins listed here are dropped from both authoring and reviewing, even if
they appear in a configured team. Use this for:

- bots that don't carry the GitHub Bot account type (e.g. release-bot accounts)
- team members who should not be counted (e.g. departed engineers)
- members of an in-scope team who fall outside this particular analysis

Matching is case-insensitive.

## What the columns mean

| Column | Meaning |
|---|---|
| `Contributor` | Display name from GitHub, falling back to login. |
| `PRs` | PRs authored in the window. |
| `Reviews` | Distinct PRs reviewed in the window (self-reviews and bot-authored PRs excluded). With `--until`, review submission timestamps are filtered to the requested date range. |
| `Rev/PR` | `Reviews` divided by `PRs`. Below 1 means more authored than reviewed (review debt); above 1 means paying review forward. |
| `Reviewed by (top N)` | Top reviewers of this contributor's PRs in the window. |
| `Reviewed for (top N)` | Top authors whose PRs this contributor reviewed. |

In the HTML output, the `Rev/PR` cell is shaded light red when below 1 and
light green when above 1.

## Counting rules

- PR authored by a GitHub Bot account or by anyone in `ignored.logins` is
  dropped entirely (its reviewers are not counted on that PR either).
- Each distinct reviewer is counted once per PR regardless of how many review
  events they submitted.
- When `--until` is set, the report uses an inclusive date window. PRs are
  counted by PR creation timestamp, while reviews are counted by review
  submission timestamp. This means a review in the requested window can count
  even when the PR was created before the window.
- Self-reviews (reviewer login equals author login) are skipped.
- Active in window means at least one PR authored or one PR reviewed within
  the requested report window; contributors with zero activity are not shown.
- With `[team]` configured: PRs authored by anyone outside the team union are
  dropped, and reviews submitted by anyone outside the team union are not
  counted (so external one-off contributors don't appear).

## Troubleshooting

**`Error: set GITHUB_TOKEN or pass --token`**
The tool didn't find your token. Run `export GITHUB_TOKEN=$(gh auth token)` in
the same shell first, or pass `--token TOKEN` on the command line.

**`organization 'X' not found` or empty team results**
Your token lacks `read:org` scope, or your GitHub account is not a member of
the org. Run `gh auth refresh -s read:org` and try again.

**`HTTP 502` or `504` for a few repos**
GitHub GraphQL has occasional transient gateway errors. The tool retries each
request three times. If a repo still fails, it is reported on stderr and
skipped; rerun to pick it up.

**Slow first run**
On the first invocation `uv` builds a virtual environment and downloads
`requests` etc. Subsequent runs are fast.

**Output includes people you didn't expect**
With `[team]` configured, the most likely cause is a new member added to one
of the listed GitHub teams. Add their login to `[ignored].logins` to drop
them.

## Development

```bash
uv run pytest                  # unit tests (no network)
uv run foc-review-stats -q     # local smoke test (requires GITHUB_TOKEN)
```

The tool is laid out as:

```
foc-review-stats/
├── team.toml                       # config you edit
├── foc_review_stats/
│   ├── cli.py                      # argument parsing, orchestration
│   ├── github.py                   # GraphQL client (repos, PRs, teams, users)
│   ├── stats.py                    # PR/review aggregation
│   └── render.py                   # text / md / html renderers
└── tests/
    └── test_stats.py               # aggregation unit tests
```
