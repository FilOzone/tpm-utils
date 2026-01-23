#!/usr/bin/env python3
"""
GitHub Projects v2 Exporter

This script queries GitHub Projects v2 (via GraphQL API) and exports
project items to CSV/TSV format, similar to GitHub's built-in export.

Usage:
    python github_project_exporter.py --org FilOzone --project-number 14 --view 22
    python github_project_exporter.py --project-id <node_id>
    python github_project_exporter.py --url https://github.com/orgs/FilOzone/projects/14
"""

import os
import sys
import csv
import json
import argparse
from typing import List, Dict, Any, Optional
import time

try:
    from gql import gql, Client
    from gql.transport.requests import RequestsHTTPTransport
except ImportError:
    print("Error: gql library required. Install with: pip install gql")
    sys.exit(1)


class GitHubProjectExporter:
    def __init__(self, token: str):
        self.token = token
        transport = RequestsHTTPTransport(
            url='https://api.github.com/graphql',
            headers={'Authorization': f'Bearer {token}'},
            use_json=True,
        )
        self.client = Client(transport=transport, fetch_schema_from_transport=False)

    def get_project_id_from_url(self, url: str) -> Optional[str]:
        """
        Extract project number from GitHub Projects URL and convert to node ID.
        URL format: https://github.com/orgs/{org}/projects/{number}
        """
        parts = url.rstrip('/').split('/')
        try:
            if 'orgs' in parts:
                org_idx = parts.index('orgs')
                org = parts[org_idx + 1]
                project_num_idx = parts.index('projects')
                project_number = int(parts[project_num_idx + 1])
                return self.get_project_node_id(org=org, project_number=project_number)
            elif 'users' in parts:
                user_idx = parts.index('users')
                user = parts[user_idx + 1]
                project_num_idx = parts.index('projects')
                project_number = int(parts[project_num_idx + 1])
                return self.get_project_node_id(user=user, project_number=project_number)
        except (ValueError, IndexError) as e:
            print(f"Error parsing URL: {e}")
            return None

    def get_project_node_id(self, org: Optional[str] = None, user: Optional[str] = None, project_number: int = None) -> Optional[str]:
        """Convert organization/user + project number to GitHub node ID."""
        if not org and not user:
            return None
        
        query_str = """
        query($owner: String!, $projectNumber: Int!) {
            organization(login: $owner) {
                projectV2(number: $projectNumber) {
                    id
                }
            }
        }
        """
        
        if user:
            query_str = """
            query($owner: String!, $projectNumber: Int!) {
                user(login: $owner) {
                    projectV2(number: $projectNumber) {
                        id
                    }
                }
            }
        """
        
        query = gql(query_str)
        variables = {
            "owner": org or user,
            "projectNumber": project_number
        }
        
        try:
            result = self.client.execute(query, variable_values=variables)
            if org:
                project_id = result.get('organization', {}).get('projectV2', {}).get('id')
            else:
                project_id = result.get('user', {}).get('projectV2', {}).get('id')
            
            if not project_id:
                print(f"Error: Project {project_number} not found for {'org' if org else 'user'} {org or user}")
                return None
            
            return project_id
        except Exception as e:
            print(f"Error fetching project ID: {e}")
            return None

    def get_project_items(self, project_id: str, max_items: int = 1000) -> List[Dict[str, Any]]:
        """Fetch all items from a GitHub Project v2."""
        query = gql("""
        query($projectId: ID!, $first: Int!, $after: String) {
            node(id: $projectId) {
                ... on ProjectV2 {
                    title
                    items(first: $first, after: $after) {
                        pageInfo {
                            hasNextPage
                            endCursor
                        }
                        nodes {
                            id
                            content {
                                ... on DraftIssue {
                                    title
                                    body
                                    type: __typename
                                }
                                ... on Issue {
                                    id
                                    title
                                    number
                                    state
                                    url
                                    assignees(first: 10) {
                                        nodes {
                                            login
                                        }
                                    }
                                    labels(first: 20) {
                                        nodes {
                                            name
                                        }
                                    }
                                    createdAt
                                    updatedAt
                                    type: __typename
                                }
                                ... on PullRequest {
                                    id
                                    title
                                    number
                                    state
                                    url
                                    assignees(first: 10) {
                                        nodes {
                                            login
                                        }
                                    }
                                    labels(first: 20) {
                                        nodes {
                                            name
                                        }
                                    }
                                    createdAt
                                    updatedAt
                                    type: __typename
                                }
                            }
                            fieldValues(first: 50) {
                                nodes {
                                    ... on ProjectV2ItemFieldTextValue {
                                        text
                                        field {
                                            ... on ProjectV2Field {
                                                name
                                            }
                                            ... on ProjectV2IterationField {
                                                name
                                            }
                                            ... on ProjectV2SingleSelectField {
                                                name
                                            }
                                        }
                                    }
                                    ... on ProjectV2ItemFieldSingleSelectValue {
                                        name
                                        field {
                                            ... on ProjectV2SingleSelectField {
                                                name
                                            }
                                        }
                                    }
                                    ... on ProjectV2ItemFieldNumberValue {
                                        number
                                        field {
                                            ... on ProjectV2Field {
                                                name
                                            }
                                        }
                                    }
                                    ... on ProjectV2ItemFieldDateValue {
                                        date
                                        field {
                                            ... on ProjectV2Field {
                                                name
                                            }
                                        }
                                    }
                                    ... on ProjectV2ItemFieldIterationValue {
                                        title
                                        startDate
                                        duration
                                        field {
                                            ... on ProjectV2IterationField {
                                                name
                                            }
                                        }
                                    }
                                    ... on ProjectV2ItemFieldMilestoneValue {
                                        title
                                        field {
                                            ... on ProjectV2Field {
                                                name
                                            }
                                        }
                                    }
                                    ... on ProjectV2ItemFieldRepositoryValue {
                                        nameWithOwner
                                        field {
                                            ... on ProjectV2Field {
                                                name
                                            }
                                        }
                                    }
                                    ... on ProjectV2ItemFieldUserValue {
                                        users(first: 10) {
                                            nodes {
                                                login
                                            }
                                        }
                                        field {
                                            ... on ProjectV2Field {
                                                name
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        """)
        
        all_items = []
        cursor = None
        page_size = 100  # GitHub allows up to 100 items per page
        fetched = 0
        
        print(f"Fetching project items...", end="", flush=True)
        
        while fetched < max_items:
            variables = {
                "projectId": project_id,
                "first": min(page_size, max_items - fetched),
                "after": cursor
            }
            
            try:
                result = self.client.execute(query, variable_values=variables)
                project = result.get('node')
                
                if not project:
                    print(f"\nError: Project not found or not accessible")
                    break
                
                items_data = project.get('items', {})
                items = items_data.get('nodes', [])
                page_info = items_data.get('pageInfo', {})
                
                if not items:
                    break
                
                all_items.extend(items)
                fetched += len(items)
                
                print(".", end="", flush=True)
                
                if not page_info.get('hasNextPage', False):
                    break
                
                cursor = page_info.get('endCursor')
                
                # Rate limiting - be nice to GitHub API
                time.sleep(0.5)
                
            except Exception as e:
                print(f"\nError fetching items: {e}")
                if "rate limit" in str(e).lower():
                    print("Rate limit exceeded. Please wait and try again.")
                break
        
        print(f" Found {len(all_items)} items")
        return all_items

    def flatten_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Flatten a project item into a flat dictionary suitable for CSV export."""
        flattened = {}
        
        content = item.get('content', {})
        
        # Basic content fields
        if content:
            flattened['Type'] = content.get('type', 'Unknown')
            flattened['Title'] = content.get('title', '')
            flattened['Number'] = content.get('number', '')
            flattened['State'] = content.get('state', '')
            flattened['URL'] = content.get('url', '')
            flattened['Created At'] = content.get('createdAt', '')
            flattened['Updated At'] = content.get('updatedAt', '')
            
            # Assignees
            assignees = content.get('assignees', {}).get('nodes', [])
            flattened['Assignees'] = ', '.join([a['login'] for a in assignees]) if assignees else ''
            
            # Labels
            labels = content.get('labels', {}).get('nodes', [])
            flattened['Labels'] = ', '.join([l['name'] for l in labels]) if labels else ''
        else:
            flattened['Type'] = 'Draft'
            flattened['Title'] = ''
            flattened['Number'] = ''
            flattened['State'] = ''
            flattened['URL'] = ''
            flattened['Created At'] = ''
            flattened['Updated At'] = ''
            flattened['Assignees'] = ''
            flattened['Labels'] = ''
        
        # Field values
        field_values = item.get('fieldValues', {}).get('nodes', [])
        for field_value in field_values:
            field = field_value.get('field', {})
            field_name = field.get('name', 'Unknown Field')
            
            # Handle different field types
            if 'text' in field_value:
                flattened[field_name] = field_value['text']
            elif 'name' in field_value:
                flattened[field_name] = field_value['name']
            elif 'number' in field_value:
                flattened[field_name] = field_value['number']
            elif 'date' in field_value:
                flattened[field_name] = field_value['date']
            elif 'title' in field_value:
                # Iteration or Milestone
                iteration = field_value.get('title', '')
                if 'startDate' in field_value:
                    # It's an iteration
                    start = field_value.get('startDate', '')
                    flattened[field_name] = f"{iteration} ({start})" if start else iteration
                else:
                    flattened[field_name] = iteration
            elif 'nameWithOwner' in field_value:
                flattened[field_name] = field_value['nameWithOwner']
            elif 'users' in field_value:
                users = field_value['users'].get('nodes', [])
                flattened[field_name] = ', '.join([u['login'] for u in users]) if users else ''
            else:
                flattened[field_name] = ''
        
        return flattened

    def export_to_csv(self, items: List[Dict[str, Any]], output_file: str, delimiter: str = ','):
        """Export project items to CSV/TSV file."""
        if not items:
            print("No items to export")
            return
        
        flattened_items = [self.flatten_item(item) for item in items]
        
        # Get all unique field names
        all_fields = set()
        for item in flattened_items:
            all_fields.update(item.keys())
        
        # Sort fields for consistent output (standard fields first, then custom)
        standard_fields = ['Type', 'Title', 'Number', 'State', 'URL', 'Assignees', 'Labels', 'Created At', 'Updated At']
        field_order = [f for f in standard_fields if f in all_fields]
        field_order.extend(sorted([f for f in all_fields if f not in standard_fields]))
        
        # Write CSV
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=field_order, delimiter=delimiter, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(flattened_items)
        
        print(f"Exported {len(items)} items to {output_file}")

    def export_to_json(self, items: List[Dict[str, Any]], output_file: str):
        """Export project items to JSON file."""
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(items, f, indent=2, default=str)
        
        print(f"Exported {len(items)} items to {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description='Export GitHub Projects v2 data to CSV/TSV/JSON',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Export using organization and project number
  python github_project_exporter.py --org FilOzone --project-number 14
  
  # Export using URL
  python github_project_exporter.py --url https://github.com/orgs/FilOzone/projects/14
  
  # Export using project node ID
  python github_project_exporter.py --project-id PVT_kwDO...
  
  # Export to TSV format
  python github_project_exporter.py --url <url> --format tsv --output project.tsv
  
  # Export to JSON
  python github_project_exporter.py --url <url> --format json --output project.json
        """
    )
    
    # Project identification (mutually exclusive)
    project_group = parser.add_mutually_exclusive_group(required=True)
    project_group.add_argument('--org', help='Organization name')
    project_group.add_argument('--user', help='User name (for user projects)')
    project_group.add_argument('--url', help='GitHub Projects URL')
    project_group.add_argument('--project-id', help='Project node ID (e.g., PVT_kwDO...)')
    
    parser.add_argument('--project-number', type=int, help='Project number (required with --org or --user)')
    parser.add_argument('--token', help='GitHub personal access token (or set GITHUB_TOKEN env var)')
    parser.add_argument('--output', '-o', default='project_export.csv', help='Output file (default: project_export.csv)')
    parser.add_argument('--format', choices=['csv', 'tsv', 'json'], default='csv', help='Output format (default: csv)')
    parser.add_argument('--max-items', type=int, default=1000, help='Maximum number of items to fetch (default: 1000)')
    
    args = parser.parse_args()
    
    # Validate arguments
    if (args.org or args.user) and not args.project_number:
        parser.error("--project-number is required when using --org or --user")
    
    # Get GitHub token
    token = args.token or os.getenv('GITHUB_TOKEN')
    if not token:
        print("Error: GitHub token required. Set GITHUB_TOKEN environment variable or use --token flag.")
        print("Token must have 'read:project' scope for organization projects.")
        sys.exit(1)
    
    exporter = GitHubProjectExporter(token)
    
    # Get project ID
    project_id = None
    if args.project_id:
        project_id = args.project_id
    elif args.url:
        project_id = exporter.get_project_id_from_url(args.url)
    elif args.org:
        project_id = exporter.get_project_node_id(org=args.org, project_number=args.project_number)
    elif args.user:
        project_id = exporter.get_project_node_id(user=args.user, project_number=args.project_number)
    
    if not project_id:
        print("Error: Could not determine project ID")
        sys.exit(1)
    
    print(f"Project ID: {project_id}")
    
    try:
        # Fetch items
        items = exporter.get_project_items(project_id, max_items=args.max_items)
        
        if not items:
            print("No items found in project")
            sys.exit(0)
        
        # Export
        if args.format == 'json':
            exporter.export_to_json(items, args.output)
        else:
            delimiter = '\t' if args.format == 'tsv' else ','
            exporter.export_to_csv(items, args.output, delimiter=delimiter)
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
