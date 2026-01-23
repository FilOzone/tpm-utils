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

### 📋 GitHub Projects v2 Exporter (FOC GA Tracker)
**Directory:** [foc-ga-tracker/](foc-ga-tracker/)

Export and interact with GitHub Projects v2 data, specifically designed for the [FilOzone FOC GA Tracker project](https://github.com/orgs/FilOzone/projects/14/views/22). 

Features:
- Export project items to CSV/TSV/JSON formats
- Preserve all custom fields and metadata
- Compatible with spreadsheet applications
- Full GraphQL API integration

See [foc-ga-tracker/README.md](foc-ga-tracker/README.md) for detailed usage instructions.

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