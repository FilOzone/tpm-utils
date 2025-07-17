# Filtering Chain List Messages from Slack Search Results

## Overview

When searching Slack for Filecoin-related content, you may encounter automated "chain list" messages that contain blockchain epoch information and storage provider (SP) data. These messages follow a specific pattern and can clutter search results when you're looking for human conversations.

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

## Step-by-Step Filtering Process

### Prerequisites
- JSON file exported from slack_search.py (using `--export-json`)
- Python 3 with json and re modules (standard library)

### Steps

1. **Export your search results to JSON first:**
   ```bash
   python3 slack_search.py --export-json search_results.json "your_query1" "your_query2"
   ```

2. **Create the filtering script:**
   
   Save this as `filter_chain_messages.py` or run directly:
   
   ```python
   import json
   import re
   import sys
   
   # Read the JSON file
   with open('search_results.json', 'r') as f:
       data = json.load(f)
   
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
   
   # Write filtered data back
   with open('search_results_filtered.json', 'w') as f:
       json.dump(filtered_data, f, indent=2)
   
   print('Filtered JSON saved to search_results_filtered.json')
   ```

3. **Run the filtering:**
   ```bash
   python3 filter_chain_messages.py
   ```

4. **Convert filtered results to markdown:**
   ```bash
   python3 slack_search.py --import-json search_results_filtered.json --output filtered_results.md
   ```

### One-Line Command Alternative

For quick filtering without creating a separate script:

```bash
python3 -c "
import json
import re
import sys

# Read the JSON file
with open('search_results.json', 'r') as f:
    data = json.load(f)

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
        print(f'Filtered {filtered_count} chain list messages from query \"{query[\"query\"]}\"', file=sys.stderr)

# Write filtered data back
with open('search_results_filtered.json', 'w') as f:
    json.dump(filtered_data, f, indent=2)

print('Filtered JSON saved to search_results_filtered.json')
"
```

## Verification

After filtering, you can verify the results:

```bash
# Check statistics
echo "Original results:"
jq '[.queries[].results | length] | add' search_results.json

echo "Filtered results:"
jq '[.queries[].results | length] | add' search_results_filtered.json

# Verify no chain list messages remain
echo "Chain list messages in filtered file:"
jq -r '.queries[].results[].text' search_results_filtered.json | grep -c "^[0-9]\+: ([^)]*) \[" || echo "None found (good!)"
```

## When to Use This Filter

Use this filtering approach when:
- You're searching for storage provider IDs (f0xxxxx) that appear in both human conversations and automated chain lists
- You want to focus on human discussions about specific SPs rather than automated blockchain data
- You're analyzing SP-related issues, participation, or communications
- You need to separate signal (human conversations) from noise (automated logs)

## Customization

You can modify the regex pattern if you encounter different chain list formats:
- Adjust the CID pattern length: `bafy2[a-z0-9]{50,}` → `bafy2[a-z0-9]{40,}`
- Add other patterns: `|f[0-9]+` for different miner ID formats
- Modify date format matching: `\([^)]+\)` → `\([A-Z][a-z]+ \d+ \d+:\d+:\d+\)`

## Files Generated

After running the filter:
- `search_results.json` - Original search results
- `search_results_filtered.json` - Filtered results without chain list messages
- `filtered_results.md` - Markdown output from filtered results (if generated)

## Notes

- The filter preserves all query structure and metadata
- Only the `text` field of results is analyzed for filtering
- The filter is case-insensitive
- All other message types (human conversations, error messages, etc.) are preserved
- The original JSON file is not modified - a new filtered version is created