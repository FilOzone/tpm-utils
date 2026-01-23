# FOC GA Tracker

Utilities and scripts to interact with GitHub Projects v2 (specifically the [FilOzone FOC GA Tracker project](https://github.com/orgs/FilOzone/projects/14/views/22)).

## Overview

This directory contains tools for:
- Exporting GitHub Projects v2 data to CSV/TSV/JSON formats (like GitHub's built-in export)
- Querying and analyzing project items
- Filtering and processing project data

## Setup

1. **Install dependencies**:
   ```bash
   pip install gql requests
   ```

2. **Set up GitHub token**:
   ```bash
   export GITHUB_TOKEN=your_github_personal_access_token
   ```
   
   Your token must have the `read:project` scope for organization projects. You can create a token at: https://github.com/settings/tokens

## Usage

### Export Project to CSV/TSV

The main tool is `github_project_exporter.py`, which exports GitHub Projects v2 data to spreadsheet-friendly formats.

**Basic usage**:
```bash
# Export using organization name and project number
python github_project_exporter.py --org FilOzone --project-number 14 --output foc_ga_tracker.csv

# Export using URL (easiest)
python github_project_exporter.py --url https://github.com/orgs/FilOzone/projects/14 --output foc_ga_tracker.csv

# Export to TSV format (tab-separated, better for Excel/Google Sheets)
python github_project_exporter.py --url https://github.com/orgs/FilOzone/projects/14 --format tsv --output foc_ga_tracker.tsv

# Export to JSON (full data structure)
python github_project_exporter.py --url https://github.com/orgs/FilOzone/projects/14 --format json --output foc_ga_tracker.json
```

**Options**:
- `--org`: Organization name (e.g., `FilOzone`)
- `--project-number`: Project number (e.g., `14`)
- `--url`: Full GitHub Projects URL (easiest option)
- `--project-id`: Direct project node ID (if you already have it)
- `--output`, `-o`: Output file path (default: `project_export.csv`)
- `--format`: Output format: `csv`, `tsv`, or `json` (default: `csv`)
- `--max-items`: Maximum number of items to fetch (default: 1000)
- `--token`: GitHub token (or use `GITHUB_TOKEN` env var)

### Exporting Specific Views

GitHub Projects v2 URLs often include a view number (e.g., `/views/22`). However, the export tool exports all items from the project, not just those visible in a specific view. Views are filters/groupings on the web interface, but the API gives you access to all project items.

If you need to filter items to match a view, you can:
1. Export all items to CSV/JSON
2. Apply filters manually or via script based on the view's filter criteria
3. Future versions of this tool may support view-specific filtering

## Understanding the Export Format

### CSV/TSV Columns

The exported CSV/TSV includes:

**Standard columns** (always present):
- `Type`: Item type (`Issue`, `PullRequest`, or `Draft`)
- `Title`: Item title
- `Number`: Issue/PR number
- `State`: State (`OPEN`, `CLOSED`, `MERGED`)
- `URL`: Link to the item
- `Assignees`: Comma-separated list of assignee usernames
- `Labels`: Comma-separated list of labels
- `Created At`: ISO 8601 timestamp
- `Updated At`: ISO 8601 timestamp

**Dynamic columns** (based on your project's custom fields):
- Any custom fields you've added to the project (Status, Priority, Iteration, etc.)
- Field values are flattened into columns with the field name as the header

### JSON Format

The JSON export contains the full GraphQL response structure, including:
- All field values with their types
- Complete assignee and label information
- All metadata

Use JSON format if you need to programmatically process the data or need the full structure.

## Examples

### Weekly Report Export

```bash
# Export current state of FOC GA Tracker
python github_project_exporter.py \
  --url https://github.com/orgs/FilOzone/projects/14 \
  --format tsv \
  --output foc_ga_tracker_$(date +%Y%m%d).tsv
```

### Processing with Python

```python
import csv
from collections import Counter

# Read exported CSV
with open('foc_ga_tracker.csv', 'r') as f:
    reader = csv.DictReader(f)
    items = list(reader)

# Count items by status
statuses = Counter(item.get('Status', 'No Status') for item in items)
print("Items by Status:")
for status, count in statuses.most_common():
    print(f"  {status}: {count}")
```

## Troubleshooting

### "Project not found or not accessible"

- Verify your GitHub token has the `read:project` scope
- Ensure you have access to the FilOzone organization
- Check that the project number is correct

### "Rate limit exceeded"

The GitHub GraphQL API has rate limits. The script includes a small delay between requests. If you hit rate limits:
- Wait a few minutes and try again
- Use a token with higher rate limits (authenticated requests have higher limits)
- Process projects in smaller batches

### Missing fields in export

- Custom fields must exist on the project for them to appear in the export
- Some field types may not be fully supported yet
- Check the JSON export if you need to see all available data

## Future Enhancements

Potential additions to this toolkit:
- [ ] View-specific filtering (export only items matching a view's filters)
- [ ] Update project items via API
- [ ] Bulk operations (update status, assignees, etc.)
- [ ] Change history tracking
- [ ] Integration with other FilOz utilities

## Related Tools

- [`github_pr_report.py`](../github_pr_report.py) - Generate PR reports across repositories
- [`team_pr_report.py`](../team_pr_report.py) - Track team member PRs
- [`slack_search.py`](../slack_search.py) - Search Slack conversations

## Resources

- [GitHub Projects v2 API Documentation](https://docs.github.com/en/graphql/reference/objects#projectv2)
- [GitHub GraphQL Explorer](https://docs.github.com/en/graphql/overview/explorer) - Test queries interactively
- [GitHub Projects Documentation](https://docs.github.com/en/issues/planning-and-tracking-with-projects)
