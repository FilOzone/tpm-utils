#!/usr/bin/env python3
"""
FOC-WG PR Notifier

This script queries FilOzone GitHub Project 14 for open PRs matching view 32 filters
and posts a daily summary to the #foc-wg Slack channel.

View 32 filters:
- is:pr
- -status:"🎉 Done"
- -milestone:"MX: Priority and sequencing TBD"
- -milestone:"M4.5: GA Fast Follows"
"""

import os
import sys
import json
import requests
from datetime import datetime
from typing import List, Dict, Any, Optional
import argparse

# FilOzone Project 14 ID (from the project URL)
FILOZ_ORG = "FilOzone"
PROJECT_NUMBER = 14

# Milestones to exclude (view 32 filter)
EXCLUDED_MILESTONES = [
    "MX: Priority and sequencing TBD",
    "M4.5: GA Fast Follows",
]

# Status to exclude
EXCLUDED_STATUS = "🎉 Done"


class FOCWGNotifier:
    """Fetches PRs from FilOzone Project 14 and posts to Slack."""

    GRAPHQL_URL = "https://api.github.com/graphql"

    def __init__(self, github_token: str, slack_webhook_url: Optional[str] = None):
        self.github_token = github_token
        self.slack_webhook_url = slack_webhook_url
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {github_token}',
            'Content-Type': 'application/json',
        })

    def _graphql_query(self, query: str, variables: Dict[str, Any] = None) -> Dict[str, Any]:
        """Execute a GraphQL query against GitHub API."""
        payload = {'query': query}
        if variables:
            payload['variables'] = variables

        response = self.session.post(self.GRAPHQL_URL, json=payload, timeout=30)
        response.raise_for_status()

        result = response.json()
        if 'errors' in result:
            raise Exception(f"GraphQL errors: {result['errors']}")

        return result['data']

    def fetch_project_items(self) -> List[Dict[str, Any]]:
        """Fetch all items from FilOzone Project 14 with pagination."""
        # First, get the project ID
        project_query = """
        query($org: String!, $number: Int!) {
            organization(login: $org) {
                projectV2(number: $number) {
                    id
                    title
                }
            }
        }
        """

        project_data = self._graphql_query(project_query, {
            'org': FILOZ_ORG,
            'number': PROJECT_NUMBER,
        })

        project = project_data['organization']['projectV2']
        if not project:
            raise Exception(f"Project {PROJECT_NUMBER} not found in {FILOZ_ORG}")

        project_id = project['id']
        print(f"Found project: {project['title']} (ID: {project_id})")

        # Now fetch all items with pagination
        items_query = """
        query($projectId: ID!, $cursor: String) {
            node(id: $projectId) {
                ... on ProjectV2 {
                    items(first: 100, after: $cursor) {
                        pageInfo {
                            hasNextPage
                            endCursor
                        }
                        nodes {
                            id
                            fieldValues(first: 20) {
                                nodes {
                                    ... on ProjectV2ItemFieldTextValue {
                                        text
                                        field { ... on ProjectV2Field { name } }
                                    }
                                    ... on ProjectV2ItemFieldSingleSelectValue {
                                        name
                                        field { ... on ProjectV2SingleSelectField { name } }
                                    }
                                    ... on ProjectV2ItemFieldIterationValue {
                                        title
                                        field { ... on ProjectV2IterationField { name } }
                                    }
                                }
                            }
                            content {
                                ... on PullRequest {
                                    __typename
                                    number
                                    title
                                    url
                                    state
                                    isDraft
                                    createdAt
                                    updatedAt
                                    author { login }
                                    repository { nameWithOwner }
                                    milestone { title }
                                }
                                ... on Issue {
                                    __typename
                                    number
                                    title
                                    url
                                    state
                                }
                            }
                        }
                    }
                }
            }
        }
        """

        all_items = []
        cursor = None
        page = 1

        while True:
            print(f"Fetching page {page}...", end="", flush=True)

            data = self._graphql_query(items_query, {
                'projectId': project_id,
                'cursor': cursor,
            })

            items_data = data['node']['items']
            nodes = items_data['nodes']
            all_items.extend(nodes)

            print(f" got {len(nodes)} items")

            if not items_data['pageInfo']['hasNextPage']:
                break

            cursor = items_data['pageInfo']['endCursor']
            page += 1

        print(f"Total items fetched: {len(all_items)}")
        return all_items

    def filter_items(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Apply view 32 filters to the items."""
        filtered = []

        for item in items:
            content = item.get('content')
            if not content:
                continue

            # Filter: Only PRs (not issues)
            if content.get('__typename') != 'PullRequest':
                continue

            # Filter: Only open PRs
            if content.get('state') != 'OPEN':
                continue

            # Get project field values
            field_values = {}
            for fv in item.get('fieldValues', {}).get('nodes', []):
                if not fv:
                    continue
                field = fv.get('field', {})
                field_name = field.get('name') if field else None
                if field_name:
                    # Get the value (could be 'name', 'text', or 'title' depending on field type)
                    value = fv.get('name') or fv.get('text') or fv.get('title')
                    field_values[field_name] = value

            # Filter: Exclude status "🎉 Done"
            status = field_values.get('Status')
            if status == EXCLUDED_STATUS:
                continue

            # Filter: Exclude specific milestones
            milestone = content.get('milestone', {})
            milestone_title = milestone.get('title') if milestone else None
            if milestone_title in EXCLUDED_MILESTONES:
                continue

            # Add field values to content for later use
            content['_project_fields'] = field_values
            filtered.append(content)

        print(f"Filtered to {len(filtered)} PRs (from {len(items)} total items)")
        return filtered

    def format_slack_message(self, prs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Format PRs into a Slack message with blocks."""
        if not prs:
            return {
                "text": "FOC-WG PR Report: No open PRs matching filters",
                "blocks": [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": "📋 FOC-WG PR Report",
                            "emoji": True
                        }
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "No open PRs matching the current filters."
                        }
                    }
                ]
            }

        # Sort by updated date (most recent first)
        prs_sorted = sorted(prs, key=lambda x: x.get('updatedAt', ''), reverse=True)

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "📋 FOC-WG PR Report",
                    "emoji": True
                }
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"*{len(prs_sorted)} open PRs* from <https://github.com/orgs/FilOzone/projects/14/views/32|FilOzone Project 14 (View 32)>"
                    }
                ]
            },
            {"type": "divider"}
        ]

        # Group PRs by repository
        prs_by_repo: Dict[str, List[Dict]] = {}
        for pr in prs_sorted:
            repo = pr.get('repository', {}).get('nameWithOwner', 'Unknown')
            if repo not in prs_by_repo:
                prs_by_repo[repo] = []
            prs_by_repo[repo].append(pr)

        for repo, repo_prs in prs_by_repo.items():
            # Repo header
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{repo}* ({len(repo_prs)} PRs)"
                }
            })

            # PR list for this repo
            pr_lines = []
            for pr in repo_prs:
                number = pr.get('number')
                title = pr.get('title', 'Untitled')
                url = pr.get('url', '')
                author = pr.get('author', {}).get('login', 'unknown')
                is_draft = pr.get('isDraft', False)
                status = pr.get('_project_fields', {}).get('Status', '')

                # Truncate title if too long
                if len(title) > 60:
                    title = title[:57] + "..."

                draft_indicator = " 📝" if is_draft else ""
                status_indicator = f" [{status}]" if status else ""

                pr_lines.append(f"• <{url}|#{number}>{draft_indicator} {title} - _{author}_{status_indicator}")

            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "\n".join(pr_lines)
                }
            })

        # Footer with timestamp
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Generated at {now} | <https://github.com/orgs/FilOzone/projects/14/views/32|View in GitHub>"
                }
            ]
        })

        return {
            "text": f"FOC-WG PR Report: {len(prs_sorted)} open PRs",
            "blocks": blocks
        }

    def post_to_slack(self, message: Dict[str, Any]) -> bool:
        """Post message to Slack webhook."""
        if not self.slack_webhook_url:
            raise ValueError("Slack webhook URL not configured")

        response = requests.post(
            self.slack_webhook_url,
            json=message,
            timeout=30
        )

        if response.status_code != 200:
            print(f"Slack API error: {response.status_code} - {response.text}")
            return False

        return True

    def run(self, dry_run: bool = False) -> bool:
        """Execute the full workflow."""
        try:
            # Fetch items from project
            print("Fetching items from FilOzone Project 14...")
            items = self.fetch_project_items()

            # Apply filters
            print("Applying view 32 filters...")
            filtered_prs = self.filter_items(items)

            # Format message
            print("Formatting Slack message...")
            message = self.format_slack_message(filtered_prs)

            if dry_run:
                print("\n=== DRY RUN - Message that would be sent ===")
                print(json.dumps(message, indent=2))
                print("\n=== PR Summary ===")
                for pr in filtered_prs:
                    repo = pr.get('repository', {}).get('nameWithOwner', 'Unknown')
                    number = pr.get('number')
                    title = pr.get('title', 'Untitled')
                    print(f"  {repo}#{number}: {title}")
                return True

            # Post to Slack
            print("Posting to Slack...")
            success = self.post_to_slack(message)

            if success:
                print("✅ Successfully posted to Slack!")
            else:
                print("❌ Failed to post to Slack")

            return success

        except Exception as e:
            print(f"❌ Error: {e}")
            return False


def main():
    parser = argparse.ArgumentParser(
        description='Fetch PRs from FilOzone Project 14 and post to Slack',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run (fetch PRs and show what would be posted)
  GITHUB_TOKEN=xxx python foc_wg_pr_notifier.py --dry-run

  # Post to Slack
  GITHUB_TOKEN=xxx SLACK_WEBHOOK_URL=yyy python foc_wg_pr_notifier.py

  # Use command-line arguments instead of env vars
  python foc_wg_pr_notifier.py --token xxx --webhook yyy
        """
    )
    parser.add_argument(
        '--token',
        help='GitHub personal access token (or set GITHUB_TOKEN env var)'
    )
    parser.add_argument(
        '--webhook',
        help='Slack webhook URL (or set SLACK_WEBHOOK_URL env var)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Fetch PRs and show message without posting to Slack'
    )

    args = parser.parse_args()

    # Get credentials
    github_token = args.token or os.getenv('GITHUB_TOKEN')
    slack_webhook = args.webhook or os.getenv('SLACK_WEBHOOK_URL')

    if not github_token:
        print("Error: GitHub token required. Set GITHUB_TOKEN environment variable or use --token flag.")
        sys.exit(1)

    if not args.dry_run and not slack_webhook:
        print("Error: Slack webhook URL required. Set SLACK_WEBHOOK_URL environment variable or use --webhook flag.")
        print("Tip: Use --dry-run to test without posting to Slack.")
        sys.exit(1)

    notifier = FOCWGNotifier(github_token, slack_webhook)
    success = notifier.run(dry_run=args.dry_run)

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
