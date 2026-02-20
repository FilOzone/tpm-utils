#!/usr/bin/env python3
"""
FOC-WG PR Notifier

This script queries FilOzone GitHub Project 14 for open PRs matching view 32 filters
and posts a daily summary to the #foc-wg Slack channel.

View 32 filters (https://github.com/orgs/FilOzone/projects/14/views/32):
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
from urllib.parse import quote
import argparse

# FilOzone Project 14 ID (from the project URL)
FILOZ_ORG = "FilOzone"
PROJECT_NUMBER = 14

# Milestones to exclude (view 32 filter)
EXCLUDED_MILESTONES = [
    "MX: Priority and sequencing TBD",
    "M4.5: GA Fast Follows",
]

# Status constants for categorization
AWAITING_REVIEW_STATUS = "🔎 Awaiting review"
IN_PROGRESS_STATUSES = ["📌 Triage", "🐱 Todo", "⌨️ In Progress"]
DONE_STATUS = "🎉 Done"

# Base URL for personalized GitHub project views
PROJECT_VIEW_BASE_URL = "https://github.com/orgs/FilOzone/projects/14/views/18"


class FOCWGNotifier:
    """Fetches PRs from FilOzone Project 14 and posts to Slack."""

    GRAPHQL_URL = "https://api.github.com/graphql"

    def __init__(self, github_token: str, slack_webhook_url: Optional[str] = None,
                 user_map_path: Optional[str] = None):
        self.github_token = github_token
        self.slack_webhook_url = slack_webhook_url
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {github_token}',
            'Content-Type': 'application/json',
        })
        self.user_map = self._load_user_map(user_map_path)

    def _load_user_map(self, user_map_path: Optional[str] = None) -> Dict[str, str]:
        """Load GitHub username to Slack user ID mapping from JSON file."""
        if user_map_path is None:
            # Default to gh_slack_users.json in the same directory as the script
            script_dir = os.path.dirname(os.path.abspath(__file__))
            user_map_path = os.path.join(script_dir, 'gh_slack_users.json')

        try:
            with open(user_map_path, 'r') as f:
                user_map = json.load(f)
                print(f"Loaded {len(user_map)} user mappings from {user_map_path}")
                return user_map
        except FileNotFoundError:
            print(f"User map file not found: {user_map_path} (using empty mapping)")
            return {}
        except json.JSONDecodeError as e:
            print(f"Error parsing user map file: {e} (using empty mapping)")
            return {}

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
                                    assignees(first: 10) {
                                        nodes { login }
                                    }
                                    reviewRequests(first: 10) {
                                        nodes {
                                            requestedReviewer {
                                                ... on User { login }
                                                ... on Team { name }
                                            }
                                        }
                                    }
                                    latestReviews(first: 10) {
                                        nodes {
                                            author { login }
                                            state
                                        }
                                    }
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
        """Apply filters to the items (open PRs, non-draft, excluding certain milestones and Done status)."""
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

            # Filter: Exclude draft PRs
            if content.get('isDraft'):
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
            if status == DONE_STATUS:
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

    def _safe_field_text(self, label: str, value: str, max_length: int = 100) -> str:
        """Safely format a field text, ensuring it doesn't exceed limits."""
        # Handle None or empty values
        if not value or value.strip() == '' or value == 'None':
            value = 'None'
        else:
            # Truncate value if needed
            if len(value) > max_length:
                value = value[:max_length - 3] + "..."
        return f"*{label}:*\n{value}"

    def build_github_link(self, username: str) -> str:
        """Build a URL-encoded link to View 18 filtered by username."""
        filter_query = f'is:pr -status:"🎉 Done" {username}'
        return f"{PROJECT_VIEW_BASE_URL}?filterQuery={quote(filter_query)}"

    def _get_slack_mention(self, github_username: str) -> str:
        """Get Slack mention for a GitHub user, or fallback to plain text."""
        slack_id = self.user_map.get(github_username)
        if slack_id:
            return f"<@{slack_id}>"
        return f"@{github_username}"

    def group_prs_by_person(self, prs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Group PRs by person based on their status.

        Returns dict with three keys:
        - awaiting_review: {reviewer_username: [(repo, number, url), ...]}
        - in_progress: {assignee_or_author: [(repo, number, url), ...]}
        - no_reviewer: [prs with "Awaiting Review" status but no reviewer]
        """
        awaiting_review: Dict[str, List[tuple]] = {}
        in_progress: Dict[str, List[tuple]] = {}
        no_reviewer: List[Dict[str, Any]] = []

        for pr in prs:
            status = pr.get('_project_fields', {}).get('Status', '')
            url = pr.get('url', '')
            number = pr.get('number')
            repo = pr.get('repository', {}).get('nameWithOwner', 'Unknown')
            # Get short repo name (without org)
            short_repo = repo.split('/')[-1] if '/' in repo else repo
            pr_info = (short_repo, number, url)

            if status == AWAITING_REVIEW_STATUS:
                # Get explicitly requested reviewers
                review_requests = pr.get('reviewRequests', {}).get('nodes', [])
                reviewers = set()
                for rr in review_requests:
                    reviewer = rr.get('requestedReviewer', {})
                    if reviewer:
                        # Could be User or Team
                        reviewer_name = reviewer.get('login') or reviewer.get('name')
                        if reviewer_name:
                            reviewers.add(reviewer_name)

                # Remove the PR author from reviewers (they aren't reviewing their own PR)
                pr_author = pr.get('author', {}).get('login')
                reviewers.discard(pr_author)

                if reviewers:
                    # Add to each reviewer's list
                    for reviewer in reviewers:
                        if reviewer not in awaiting_review:
                            awaiting_review[reviewer] = []
                        awaiting_review[reviewer].append(pr_info)
                else:
                    # No reviewer assigned - skip dependabot PRs
                    if pr_author and pr_author.lower() in ('dependabot', 'dependabot[bot]'):
                        continue
                    no_reviewer.append(pr)

            elif status in IN_PROGRESS_STATUSES:
                # Get assignee, or fall back to author
                assignees = pr.get('assignees', {}).get('nodes', [])
                assignee_logins = [a.get('login') for a in assignees if a and a.get('login')]

                if assignee_logins:
                    # Add to first assignee's list (primary assignee)
                    person = assignee_logins[0]
                else:
                    # Fall back to author
                    person = pr.get('author', {}).get('login', 'unknown')

                if person not in in_progress:
                    in_progress[person] = []
                in_progress[person].append(pr_info)

        return {
            'awaiting_review': awaiting_review,
            'in_progress': in_progress,
            'no_reviewer': no_reviewer,
        }

    def format_person_centric_message(self, prs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Format PRs into a person-centric Slack message with @mentions and personalized links."""
        if not prs:
            return [{
                "text": "FOC-WG PR Summary: No open PRs matching filters",
                "blocks": [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": "FOC-WG PR Summary",
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
            }]

        grouped = self.group_prs_by_person(prs)
        blocks = []

        # Section: PRs Awaiting Your Review (only users in mapping)
        mapped_awaiting = {u: prs for u, prs in grouped['awaiting_review'].items() if u in self.user_map}
        if mapped_awaiting:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*:mag: PRs Awaiting Your Review*"
                }
            })

            # Sort by username alphabetically (case-insensitive)
            for username in sorted(mapped_awaiting.keys(), key=str.lower):
                pr_list = mapped_awaiting[username]
                mention = self._get_slack_mention(username)
                view_link = self.build_github_link(username)
                # Format: <@USER> repo#123 repo#456 (view all)
                pr_links = ' '.join([f"<{url}|{repo}#{num}>" for repo, num, url in pr_list])
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"  • {mention}: {pr_links} (<{view_link}|view all>)"
                    }
                })

        # Section: PRs In Progress (only users in mapping)
        mapped_in_progress = {u: prs for u, prs in grouped['in_progress'].items() if u in self.user_map}
        if mapped_in_progress:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*:construction: PRs In Progress*"
                }
            })

            # Sort by username alphabetically (case-insensitive)
            for username in sorted(mapped_in_progress.keys(), key=str.lower):
                pr_list = mapped_in_progress[username]
                mention = self._get_slack_mention(username)
                view_link = self.build_github_link(username)
                # Format: <@USER> repo#123 repo#456 (view all)
                pr_links = ' '.join([f"<{url}|{repo}#{num}>" for repo, num, url in pr_list])
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"  • {mention}: {pr_links} (<{view_link}|view all>)"
                    }
                })

        # Section: PRs Awaiting Review (No Reviewer Assigned)
        if grouped['no_reviewer']:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*:warning: PRs Awaiting Review (No Reviewer Assigned)*"
                }
            })

            for pr in grouped['no_reviewer']:
                repo = pr.get('repository', {}).get('nameWithOwner', 'Unknown')
                number = pr.get('number')
                title = pr.get('title', 'Untitled')
                url = pr.get('url', '')
                author = pr.get('author', {}).get('login', 'unknown')
                author_mention = self._get_slack_mention(author)

                # Truncate title if too long
                if len(title) > 60:
                    title = title[:57] + "..."

                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"  • <{url}|{repo}#{number}> - {title} (authored by {author_mention})"
                    }
                })

        # Footer with timestamp
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Generated {now}"
                }
            ]
        })

        return [{
            "text": f"FOC-WG PR Summary: {len(prs)} open PRs",
            "blocks": blocks
        }]

    def format_slack_messages(self, prs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Format PRs into one or more Slack messages with blocks (splits if >50 blocks)."""
        SLACK_MAX_BLOCKS = 50
        
        if not prs:
            return [{
                "text": "FOC-WG Daily PR Summary: No open PRs matching filters",
                "blocks": [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": "📋 FOC-WG Daily PR Summary",
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
            }]

        # Sort by updated date (most recent first)
        prs_sorted = sorted(prs, key=lambda x: x.get('updatedAt', ''), reverse=True)

        # Group PRs by repository
        prs_by_repo: Dict[str, List[Dict]] = {}
        for pr in prs_sorted:
            repo = pr.get('repository', {}).get('nameWithOwner', 'Unknown')
            if repo not in prs_by_repo:
                prs_by_repo[repo] = []
            prs_by_repo[repo].append(pr)

        messages = []
        current_blocks = []
        message_num = 1
        total_messages = 1  # Will be calculated if we need to split
        
        # Compact header for first message
        header_blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*📋 FOC-WG Daily PR Summary* · {len(prs_sorted)} open PRs · <https://github.com/orgs/FilOzone/projects/14/views/32|View 32>"
                }
            }
        ]
        
        # Group PRs by repository first
        prs_by_repo: Dict[str, List[Dict]] = {}
        for pr in prs_sorted:
            repo = pr.get('repository', {}).get('nameWithOwner', 'Unknown')
            if repo not in prs_by_repo:
                prs_by_repo[repo] = []
            prs_by_repo[repo].append(pr)

        # Estimate if we need to split (now: 1 block per PR + 1 per repo header + header + footer)
        estimated_blocks = len(header_blocks) + len(prs_sorted) + len(prs_by_repo) + 1  # +1 for footer
        if estimated_blocks > SLACK_MAX_BLOCKS:
            # Calculate how many messages we'll need
            blocks_per_message = SLACK_MAX_BLOCKS - len(header_blocks) - 2  # Reserve for footer
            prs_per_message = blocks_per_message - len(prs_by_repo)  # Rough estimate
            if prs_per_message < 10:
                prs_per_message = 10  # Minimum
            total_messages = (len(prs_sorted) + prs_per_message - 1) // prs_per_message
        else:
            total_messages = 1
        
        current_blocks.extend(header_blocks)

        repo_list = list(prs_by_repo.items())
        for repo_idx, (repo, repo_prs) in enumerate(repo_list):
            # Check if we need to start a new message
            # Each PR takes ~1 block (section with fields), repo header takes 1, divider takes 1
            estimated_new_blocks = 1 + len(repo_prs) + 1  # repo header + PRs + divider
            if len(current_blocks) + estimated_new_blocks > SLACK_MAX_BLOCKS - 3:  # Reserve for footer
                # Finish current message
                now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
                current_blocks.append({
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"Part {message_num} · Generated {now}"
                        }
                    ]
                })
                messages.append({
                    "text": f"FOC-WG Daily PR Summary (Part {message_num})",
                    "blocks": current_blocks
                })
                
                # Start new message
                message_num += 1
                current_blocks = [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*📋 FOC-WG Daily PR Summary (Part {message_num})* · <https://github.com/orgs/FilOzone/projects/14/views/32|View 32>"
                        }
                    }
                ]
            
            # Compact repo header
            current_blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{repo}* ({len(repo_prs)})"
                }
            })

            # PR list for this repo - compact format
            for pr_idx, pr in enumerate(repo_prs):
                number = pr.get('number')
                title = pr.get('title', 'Untitled')
                url = pr.get('url', '')
                author = pr.get('author', {}).get('login', 'unknown')
                
                # Get assignees
                assignees = pr.get('assignees', {}).get('nodes', [])
                assignee_logins = [a.get('login') for a in assignees if a]
                assignees_str = ', '.join(assignee_logins) if assignee_logins else 'None'
                # Truncate if too long (Slack field limit is 2000 chars)
                if len(assignees_str) > 100:
                    assignees_str = assignees_str[:97] + "..."
                
                # Get requested reviewers
                review_requests = pr.get('reviewRequests', {}).get('nodes', [])
                reviewers = []
                for rr in review_requests:
                    reviewer = rr.get('requestedReviewer', {})
                    if reviewer:
                        # Could be User or Team
                        reviewer_name = reviewer.get('login') or reviewer.get('name')
                        if reviewer_name:
                            reviewers.append(reviewer_name)
                reviewers_str = ', '.join(reviewers) if reviewers else 'None'
                # Truncate if too long
                if len(reviewers_str) > 100:
                    reviewers_str = reviewers_str[:97] + "..."
                
                # Dates - parse ISO format dates
                created_at = pr.get('createdAt', '')
                updated_at = pr.get('updatedAt', '')
                try:
                    if created_at:
                        created_date = datetime.fromisoformat(created_at.replace('Z', '+00:00')).strftime('%Y-%m-%d')
                    else:
                        created_date = 'Unknown'
                except (ValueError, AttributeError):
                    created_date = 'Unknown'
                
                try:
                    if updated_at:
                        updated_date = datetime.fromisoformat(updated_at.replace('Z', '+00:00')).strftime('%Y-%m-%d')
                    else:
                        updated_date = 'Unknown'
                except (ValueError, AttributeError):
                    updated_date = 'Unknown'
                
                # Project fields
                project_fields = pr.get('_project_fields', {})
                status = project_fields.get('Status', '') or 'None'
                cycle = project_fields.get('Cycle', '') or project_fields.get('Iteration', '') or 'None'
                # Truncate if too long
                if len(status) > 50:
                    status = status[:47] + "..."
                if len(cycle) > 50:
                    cycle = cycle[:47] + "..."
                
                # Truncate title if too long
                display_title = title
                if len(display_title) > 70:
                    display_title = display_title[:67] + "..."
                
                # Build compact single line: PR link, author, assignee (if different), reviewer, created date, status
                pr_line = f"• <{url}|#{number}> {display_title}"
                
                # Add author
                pr_line += f" · _{author}_"
                
                # Add assignee only if different from author
                if assignees_str != 'None' and assignees_str != author:
                    # Truncate assignees if multiple
                    if len(assignees_str) > 30:
                        assignees_str = assignees_str[:27] + "..."
                    pr_line += f" → _{assignees_str}_"
                
                # Add reviewer if exists
                if reviewers_str != 'None':
                    # Truncate reviewers if multiple
                    if len(reviewers_str) > 30:
                        reviewers_str = reviewers_str[:27] + "..."
                    pr_line += f" 👀 _{reviewers_str}_"
                
                # Add created date
                pr_line += f" · {created_date}"
                
                # Add status (truncate if too long)
                if status and status != 'None':
                    status_short = status[:20] if len(status) > 20 else status
                    pr_line += f" · {status_short}"
                
                current_blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": pr_line
                    }
                })
            
            # No divider between repos - repo headers provide enough separation

        # Compact footer with timestamp
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        footer_text = f"Generated {now}"
        current_blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": footer_text
                }
            ]
        })

        messages.append({
            "text": f"FOC-WG Daily PR Summary: {len(prs_sorted)} open PRs",
            "blocks": current_blocks
        })

        # Update footers with part indicators only if we actually have multiple messages
        if len(messages) > 1:
            for i, msg in enumerate(messages, 1):
                # Update footer in each message
                for block in reversed(msg['blocks']):
                    if block.get('type') == 'context':
                        elements = block.get('elements', [])
                        if elements and 'Generated' in str(elements[0].get('text', '')):
                            elements[0]['text'] = f"Part {i}/{len(messages)} · {elements[0]['text']}"
                            break
                # Update header if it's a continuation message
                if i > 1:
                    for block in msg['blocks']:
                        if block.get('type') == 'section' and 'Part' in str(block.get('text', {}).get('text', '')):
                            block['text']['text'] = block['text']['text'].replace(
                                f"Part {i})", f"Part {i}/{len(messages)})"
                            )
                            break

        return messages

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

            # Format messages using person-centric format
            print("Formatting Slack message(s)...")
            messages = self.format_person_centric_message(filtered_prs)

            if dry_run:
                print(f"\n=== DRY RUN - {len(messages)} message(s) that would be sent ===")
                for i, message in enumerate(messages, 1):
                    print(f"\n--- Message {i} of {len(messages)} ---")
                    print(json.dumps(message, indent=2))
                print("\n=== PR Summary ===")
                for pr in filtered_prs:
                    repo = pr.get('repository', {}).get('nameWithOwner', 'Unknown')
                    number = pr.get('number')
                    title = pr.get('title', 'Untitled')
                    print(f"  {repo}#{number}: {title}")
                return True

            # Post to Slack (may be multiple messages)
            print(f"Posting {len(messages)} message(s) to Slack...")
            success = True
            for i, message in enumerate(messages, 1):
                if len(messages) > 1:
                    print(f"  Posting message {i} of {len(messages)}...")
                if not self.post_to_slack(message):
                    success = False
                    break
                # Small delay between messages to avoid rate limiting
                if i < len(messages):
                    import time
                    time.sleep(1)

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

  # Use a custom user mapping file
  python foc_wg_pr_notifier.py --user-map /path/to/users.json --dry-run
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
        '--user-map',
        help='Path to JSON file mapping GitHub usernames to Slack user IDs (default: gh_slack_users.json in script directory)'
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

    notifier = FOCWGNotifier(github_token, slack_webhook, args.user_map)
    success = notifier.run(dry_run=args.dry_run)

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
