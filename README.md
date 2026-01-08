# FilOz TPM Utilities

This repository contains various scripts and documentation to help [FilOz](https://www.filoz.org/) Technical Program Managers (TPMs) with weekly reporting, investigations, and other operational tasks.

## Overview

FilOz TPMs regularly need to:
- Generate reports on GitHub pull requests and development activity
- Find and analyze Filecoin Slack conversations related to specific miner IDs
- Track storage provider issues and communications
- Investigate technical problems across the Filecoin ecosystem

This repository provides tools and workflows to streamline these tasks.

## Available Tools & Documentation

### 📊 GitHub PR Report Generator
**File:** [GITHUB_PR_REPORT_GENERATOR.md](GITHUB_PR_REPORT_GENERATOR.md)

Generate comprehensive reports of GitHub pull requests across repositories, with filtering capabilities for date ranges, repositories, and specific criteria. Useful for weekly development activity summaries.

### 🔍 Slack Miner ID Search Workflow
**File:** [FINDING_MINERIDS_ON_SLACK.md](FINDING_MINERIDS_ON_SLACK.md)

Complete workflow for finding relevant Filecoin Slack messages related to specific miner IDs. Includes:
- Automated searching across Slack channels
- Filtering out automated chain messages
- Post-processing to focus on human conversations
- Clean markdown report generation

This is particularly useful for investigating storage provider issues and tracking community discussions.

### 📢 FOC-WG PR Notifier
**File:** `foc_wg_pr_notifier.py`

Automated daily notification system that fetches open PRs from FilOzone GitHub Project 14 (View 32) and posts a formatted summary to the `#foc-wg` Slack channel.

**Features:**
- Queries GitHub Project 14 via GraphQL API
- Applies View 32 filters (excludes "Done" status, specific milestones)
- Groups PRs by repository
- Posts formatted Slack messages with PR details
- Runs automatically via GitHub Actions (daily at 9 AM EST on weekdays)

**Testing:**

1. **Local dry-run test** (recommended first step):
   ```bash
   GITHUB_TOKEN=your_token python foc_wg_pr_notifier.py --dry-run
   ```
   This will fetch PRs and show the message that would be posted without actually sending to Slack.

2. **Local full test** (posts to Slack):
   ```bash
   GITHUB_TOKEN=your_token SLACK_WEBHOOK_URL=your_webhook python foc_wg_pr_notifier.py
   ```

3. **GitHub Actions test**:
   - Go to the [Actions tab](https://github.com/FilOzone/tpm-utils/actions) in the repository
   - Select "FOC-WG PR Notifier" workflow
   - Click "Run workflow"
   - Choose "true" for dry_run to test without posting, or "false" to post to Slack
   - Click "Run workflow" button

**Prerequisites:**
- GitHub PAT with `read:project` organization permission (stored as `FOC_WG_NOTIFIER_PAT` secret)
- Slack incoming webhook URL for `#foc-wg` channel (stored as `SLACK_WEBHOOK_URL` secret)

***Periodic Runs:***
This notifier is scheduled to run periodically per [./github/workflows/fog-wg-pr-notifier.yml](fog-wg-pr-notifier.yml).

## Getting Started

1. **Clone the repository**
   ```bash
   git clone https://github.com/FilOzone/tpm-utils.git
   cd tpm-utils
   ```

2. **Review the documentation** for the specific tool you need
3. **Set up any required dependencies** (Python 3, jq, etc.)
4. **Follow the workflow steps** outlined in each documentation file

## Contributing

If you have additional tools or improvements to existing workflows:
1. Fork the repository
2. Create a feature branch
3. Add your tools with appropriate documentation
4. Submit a pull request

## Support

For questions or issues with these tools, please open an issue in this repository or reach out to the FilOz team.

---

*Part of the [FilOz](https://www.filoz.org/) Technical Program Management toolkit*