# Finding Relevant Filecoin Slack Messages for Miner IDs

## Overview

This document describes the complete workflow for finding relevant Filecoin Slack messages for a list of miner IDs. The process involves searching Slack, filtering out automated chain messages, and generating clean markdown reports.

## When to Use This Workflow

Use this complete workflow when:
- You're searching for multiple storage provider IDs (f0xxxxx) that appear in both human conversations and automated chain lists
- You want to focus on human discussions about specific SPs rather than automated blockchain data
- You're analyzing SP-related issues, participation, or communications across multiple miners
- You need to separate signal (human conversations) from noise (automated logs)
- You want a clean, consolidated markdown report of relevant conversations

## Complete Workflow

### Step 1: Initial Slack Search with JSON Export

Search Slack for multiple miner IDs and export results to JSON for post-processing:

```bash
# Create a file with your miner IDs (one per line)
vim /tmp/search_queries.txt

# Search and export to JSON
python3 slack_search.py --export-json /tmp/slack_search.json < /tmp/search_queries.txt
```

**Note**: If there are specific messages you know you don't want in the results, you can use the `--exclude-url` functionality during the search phase, or do post-processing with `jq` to remove unwanted results from the JSON.

### Step 2: Filter Chain Messages

Remove automated "chain list" messages that contain blockchain epoch information and storage provider data. These messages follow a specific pattern and can clutter search results when you're looking for human conversations.

## Chain List Message Pattern

Chain list messages typically follow this format:
```
<epoch_number>: (<date_time>) [ <chain_data> ]
```

**Example:**
```
4880058: (Apr 15 16:09:00) [ bafy2bzacebi2ksvy2tkbkvtxmtt77odhu44jcizzw472j4jbajgqowsue2e2y: f03363420,bafy2bzacedzt2o23vvhdgkq4hq7t7tzxwpgucchipfvxdpygwuqct3t34jxnk: f02809382,bafy2bzacec4xwieh6smhnubzf3cg7mi55tyqb6qeeugnjslwqhm45etcd2si2: f02941891, ]
```

**Pattern Components:**
- `4880058:` - Epoch number followed by colon
- `(Apr 15 16:09:00)` - Date and time in parentheses
- `[ ... ]` - Square brackets containing chain data
- `bafy2...` - Content Identifier (CID) patterns
- `f03363420` - Storage provider (miner) ID patterns

## Filtering Approach

The filtering uses a regular expression to identify and remove messages containing this pattern from exported JSON search results.

### Regular Expression Pattern

```regex
\d+:\s*\([^)]+\)\s*\[\s*[^]]*(?:bafy2[a-z0-9]{50,}|f0\d+)[^]]*\]
```

**Pattern Breakdown:**
- `\d+:` - Matches epoch number followed by colon
- `\s*\([^)]+\)` - Matches date/time in parentheses with optional whitespace
- `\s*\[` - Matches opening square bracket with optional whitespace
- `[^]]*(?:bafy2[a-z0-9]{50,}|f0\d+)[^]]*` - Matches content containing either:
  - `bafy2` followed by 50+ alphanumeric characters (CID pattern)
  - `f0` followed by digits (storage provider ID pattern)
- `\]` - Matches closing square bracket

#### Chain Message Filtering

Create a Python script to filter out chain messages:

```python
import json
import re
import sys

# Read JSON from stdin
data = json.load(sys.stdin)

# Regex pattern to match chain list messages
chain_pattern = r'\d+:\s*\([^)]+\)\s*\[\s*[^]]*(?:bafy2[a-z0-9]{50,}|f0\d+)[^]]*\]'

# Filter out chain list messages
filtered_data = data.copy()
for query in filtered_data['queries']:
    original_count = len(query['results'])
    query['results'] = [
        result for result in query['results'] 
        if not re.search(chain_pattern, result['text'], re.IGNORECASE)
    ]
    filtered_count = original_count - len(query['results'])
    if filtered_count > 0:
        print(f'Filtered {filtered_count} chain list messages from query "{query["query"]}"', file=sys.stderr)

# Write filtered data to stdout
json.dump(filtered_data, sys.stdout, indent=2)
```

### Step 3: Remove Empty Queries

Remove any search queries that have no remaining messages after filtering:

```bash
jq '.queries |= map(select(.results | length > 0))' /tmp/slack_search_filtered.json > /tmp/slack_search_cleaned.json
```

### Step 4: Generate Final Markdown Report

Import the cleaned JSON and generate a markdown report:

```bash
python3 slack_search.py --import-json /tmp/slack_search_cleaned.json --output /tmp/slack_search.md
```

## Example Command Sequence

Based on actual usage, here's the typical command sequence:

```bash
# 1. Create search queries file
vim /tmp/search_queries.txt

# 2. Run initial search with JSON export
python3 slack_search.py --export-json /tmp/slack_search.json < /tmp/search_queries.txt

# 3. Filter chain messages (using Python script from Step 2)
python3 filter_chain_messages.py < /tmp/slack_search.json > /tmp/slack_search_filtered.json

# 4. Remove empty queries
jq '.queries |= map(select(.results | length > 0))' /tmp/slack_search_filtered.json > /tmp/slack_search_cleaned.json

# 5. Generate final markdown report
python3 slack_search.py --import-json /tmp/slack_search_cleaned.json --output /tmp/slack_search.md
```

### Files Generated

After running the complete workflow:
- `/tmp/slack_search.json` - Original search results
- `/tmp/slack_search_filtered.json` - Filtered results without chain list messages
- `/tmp/slack_search_cleaned.json` - Cleaned results with empty queries removed
- `/tmp/slack_search.md` - Final markdown report

### Verification

After filtering, you can verify the results:

```bash
# Check statistics
echo "Original results:"
jq '[.queries[].results | length] | add' /tmp/slack_search.json

echo "Filtered results:"
jq '[.queries[].results | length] | add' /tmp/slack_search_filtered.json

echo "Cleaned results:"
jq '[.queries[].results | length] | add' /tmp/slack_search_cleaned.json

# Verify no chain list messages remain
echo "Chain list messages in cleaned file:"
jq -r '.queries[].results[].text' /tmp/slack_search_cleaned.json | grep -c "^[0-9]\+: ([^)]*) \[" || echo "None found (good!)"
```

### Notes

- The filter preserves all query structure and metadata
- Only the `text` field of results is analyzed for filtering
- The filter is case-insensitive
- All other message types (human conversations, error messages, etc.) are preserved
- The original JSON file is not modified - new filtered versions are created
- The workflow is designed to be run iteratively as you discover new miner IDs of interest