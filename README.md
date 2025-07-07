# GitHub PR Report Generator

A Python script that queries GitHub repositories for pull request information and generates reports with open PR counts and detailed PR summaries.

## Features

- Count open non-draft PRs for each repository
- Generate detailed PR summaries for the last 3 months
- Tab-separated output for easy spreadsheet import
- Includes PR number, creation date, last modified date, title, author, status, and URL

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Create a GitHub Personal Access Token:
   - Go to [GitHub Settings > Developer settings > Personal access tokens](https://github.com/settings/tokens)
   - Generate a new token with `repo` scope
   - Set the token as an environment variable:
     ```bash
     export GITHUB_TOKEN="your_token_here"
     ```

## Usage

### FilOz Weekly Report

To generate the FilOz Weekly Report on repos @biglep runs:

```bash
python3 github_pr_report.py filecoin-project/lotus filecoin-project/go-state-types filecoin-project/filecoin-ffi filecoin-project/builtin-actors filecoin-project/ref-fvm filecoin-project/actors-utils filecoin-project/lotus-infra filecoin-project/go-jsonrpc filecoin-project/go-crypto filecoin-project/go-f3 filecoin-project/lotus-docs filecoin-project/rust-filecoin-proofs-api filecoin-project/rust-gpu-tools filecoin-project/bellperson filecoin-project/rust-fil-proofs filecoin-project/ec-gpu filecoin-project/merkletree filecoin-project/blstrs filecoin-project/go-paramfetch
```

### Basic Usage

```bash
python3 github_pr_report.py owner/repo1 owner/repo2 owner/repo3
```

### Save to File

```bash
python3 github_pr_report.py owner/repo1 owner/repo2 --output report.txt
```

### Using Token Flag

```bash
python3 github_pr_report.py --token your_token_here owner/repo1 owner/repo2
```

## Example Output

```
=== Open Non-Draft PR Count Summary ===
Repository              Open Non-Draft PRs
owner/repo1             5
owner/repo2             3
owner/repo3             2
TOTAL                   10

=== PR Details (Last 3 Months) ===
Repository      PR Number       Created Date    Last Modified   Title                   Author  Status          URL
owner/repo1     42             2024-01-15      2024-01-20      Fix authentication bug  alice   ready for review https://github.com/owner/repo1/pull/42
owner/repo2     38             2024-01-10      2024-01-18      Add new feature        bob     draft           https://github.com/owner/repo2/pull/38
```

## Importing to Spreadsheet

The output uses tab-separated values that can be easily copied and pasted into Excel, Google Sheets, or other spreadsheet applications:

1. Run the script and copy the output
2. Open your spreadsheet application
3. Paste the data - it will automatically separate into columns

## Command Line Options

- `repos`: One or more GitHub repositories in `owner/repo` format
- `--token`: GitHub personal access token (optional if `GITHUB_TOKEN` env var is set)
- `--output`, `-o`: Output file path (optional, defaults to stdout)

## Requirements

- Python 3.6+
- `requests` library
- GitHub Personal Access Token with `repo` scope