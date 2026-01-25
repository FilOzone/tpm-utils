# GitHub Milestone Manager

A Python script for creating and updating GitHub milestones across multiple repositories from a JSON configuration file.

## Overview

This tool allows you to:
- Create or update milestones across multiple GitHub repositories
- Sync milestones from a reference repository (source of truth)
- Automatically match existing milestones by name
- Rename existing milestones
- Manage milestone descriptions and due dates
- Validate configuration against a JSON schema
- Preview changes with dry-run mode

## Features

- **Reference Milestones**: Sync milestones from one repository to others, automatically matching by name
- **Automatic Matching**: Finds existing milestones by name before creating new ones
- **Milestone Renaming**: Rename existing milestones using `existingNameToRename`
- **Flexible Updates**: Clear or update descriptions and due dates with null/empty string handling
- **JSON Schema Validation**: Validates configuration files against a schema
- **Comment Support**: Supports `//` and `/* */` style comments in JSON files
- **Dry-Run Mode**: Preview all changes before executing
- **Detailed Output**: Shows previous → new values for all fields

## Prerequisites

- Python 3.8 or higher
- [uv](https://github.com/astral-sh/uv) package manager
- GitHub personal access token with `repo` scope
- Access to the repositories you want to manage milestones for

## Installation

No installation needed! The script uses `uv run` which automatically handles dependencies.

## Usage

### Basic Command

```bash
cd github-milestone-creator
uv run github_milestone_manager.py --config <config-file.json> --token $(gh auth token) [--dry-run]
```

### Options

- `--config` (required): Path to your milestones JSON configuration file
- `--token`: GitHub personal access token (or set `GITHUB_TOKEN` environment variable)
- `--dry-run`: Preview changes without making any modifications

### Examples

**Dry-run (recommended first step):**
```bash
uv run github_milestone_manager.py \
  --config milestones-FOCRepos-2026-01-23.json \
  --token $(gh auth token) \
  --dry-run
```

**Execute changes:**
```bash
uv run github_milestone_manager.py \
  --config milestones-FOCRepos-2026-01-23.json \
  --token $(gh auth token)
```

**Using environment variable for token:**
```bash
export GITHUB_TOKEN=$(gh auth token)
uv run github_milestone_manager.py \
  --config milestones-FOCRepos-2026-01-23.json \
  --dry-run
```

## Configuration File Format

The configuration file is a JSON file with the following structure:

```json
{
  "repos": [
    "owner/repo1",
    "owner/repo2"
  ],
  "milestones": [
    {
      "name": "Milestone Name",
      "description": "Milestone description",
      "dueDate": "2026-01-30"
    }
  ]
}
```

### Milestone Fields

- **`name`** (string, required if `referenceMilestoneUrl` not set): The milestone name
- **`referenceMilestoneUrl`** (string, optional): URL to a GitHub milestone in another repo to sync from. If provided:
  - Uses the reference milestone's name, description, and due date
  - Automatically matches existing milestones with the same name
  - Sets description to `"See <url>"`
- **`existingNameToRename`** (string, optional): If provided, finds and renames an existing milestone with this name
- **`description`** (string or null, optional):
  - Not present: Field won't be touched
  - `null` or `""`: Field will be cleared
  - String value: Field will be set to that value
  - Ignored if `referenceMilestoneUrl` is set
- **`dueDate`** (string or null, optional, format: YYYY-MM-DD):
  - Not present: Field won't be touched
  - `null` or `""`: Field will be cleared
  - Date string: Field will be set to that date
  - Ignored if `referenceMilestoneUrl` is set

### Example Configurations

**Basic milestone:**
```json
{
  "name": "Q1 2026 Release",
  "description": "First quarter 2026 release milestone",
  "dueDate": "2026-03-31"
}
```

**Reference milestone (syncs from another repo):**
```json
{
  "referenceMilestoneUrl": "https://github.com/FilOzone/filecoin-services/milestone/1"
}
```

**Rename existing milestone:**
```json
{
  "name": "M4.1: mainnet ready",
  "existingNameToRename": "M4: Filecoin Service Liftoff",
  "description": "Updated description",
  "dueDate": "2026-02-14"
}
```

**Clear description:**
```json
{
  "name": "Milestone Name",
  "description": null,
  "dueDate": "2026-06-30"
}
```

**JSON with comments (supported):**
```json
{
  "repos": [
    "FilOzone/filecoin-services"  // Main repository
  ],
  "milestones": [
    {
      /* This is a multi-line comment */
      "name": "Q1 2026 Release",
      "description": "First quarter release"
    }
  ]
}
```

## How It Works

### Milestone Matching Logic

Before creating a milestone, the script checks for existing milestones in this order:

1. **`existingNameToRename`**: If provided, finds milestone with that name
2. **Reference milestone name**: If `referenceMilestoneUrl` is provided, checks for milestone with the reference milestone's name
3. **Resolved name**: Checks for milestone with the final resolved name
4. **Create new**: Only creates if no matching milestone is found

### Reference Milestones

When `referenceMilestoneUrl` is provided:
- Fetches the reference milestone to get its name, description, and due date
- Automatically finds existing milestones with the same name in target repos
- Updates the existing milestone or creates a new one if not found
- Sets description to `"See <referenceMilestoneUrl>"` (pointer to source)
- Uses reference milestone's due date

### Update Behavior

- **Name**: Updated if `existingNameToRename` is used (renaming) or if creating new
- **Description**: 
  - If `referenceMilestoneUrl`: Always set to pointer
  - Otherwise: Updated based on config (null/empty clears, string sets, undefined leaves unchanged)
- **Due Date**:
  - If `referenceMilestoneUrl`: Uses reference milestone's due date
  - Otherwise: Updated based on config (null/empty clears, date sets, undefined leaves unchanged)

## Output

The script provides detailed output showing:

**For CREATE operations:**
```
Would CREATE: M4.0: mainnet staged
    Name: (not set) → M4.0: mainnet staged
    Description: (not set) → See https://github.com/...
    Due Date: (not set) → 2026-01-30
```

**For UPDATE operations:**
```
Would UPDATE: M4.0: mainnet staged (milestone #1)
    Name: M4.0: mainnet staged (unchanged)
    Description: Old description → See https://github.com/...
    Due Date: 2026-01-25 → 2026-01-30
```

## Schema Validation

Configuration files are validated against `milestones-schema.json`. The schema ensures:
- Required fields are present
- Field types are correct
- Date formats are valid (YYYY-MM-DD)
- Repository names are in `owner/repo` format
- Milestone URLs are valid GitHub milestone URLs

## Error Handling

The script handles:
- Missing or invalid configuration files
- Schema validation errors
- GitHub API rate limiting (automatic retry with backoff)
- Missing reference milestones (warns and continues)
- Network errors (clear error messages)

## Examples

See the example configuration files in this directory:
- `milestones-FOCRepos-2026-01-23.json` - Real-world example for FOC repos
- `milestones-filecoin-services-as-source-of-truth-2026-01-23.json` - Example using reference milestones

## Troubleshooting

**ModuleNotFoundError: No module named 'requests'**
- Make sure you're using `uv run` which handles dependencies automatically
- The script uses PEP 723 inline script metadata for dependency management

**Rate limit errors**
- The script automatically handles rate limiting with retries
- If you hit rate limits frequently, consider processing fewer repos at once

**Milestone not found errors**
- Check that you have access to the repository
- Verify the milestone URL is correct (if using `referenceMilestoneUrl`)
- Ensure your GitHub token has `repo` scope

**Schema validation errors**
- Check that your JSON is valid (use a JSON validator)
- Review the schema file for required fields and formats
- Ensure date formats are YYYY-MM-DD

## See Also

- [JSON Schema](milestones-schema.json) - Configuration schema definition
