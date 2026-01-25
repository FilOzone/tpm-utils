#!/usr/bin/env python3
"""
GitHub Milestone Creator

This script validates a milestones.json file against a schema and creates/updates
GitHub milestones across multiple repositories.
"""

import os
import sys
import json
import re
import requests
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
import argparse
import time
from pathlib import Path

try:
    import jsonschema
except ImportError:
    print("Error: jsonschema library required. Install with: pip install jsonschema")
    sys.exit(1)


class GitHubMilestoneCreator:
    """Creates and updates GitHub milestones across repositories."""

    BASE_URL = "https://api.github.com"

    def __init__(self, github_token: str):
        self.github_token = github_token
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'token {github_token}',
            'Accept': 'application/vnd.github.v3+json',
        })

    def _check_rate_limit(self):
        """Check rate limit and wait if needed."""
        response = self.session.get(f"{self.BASE_URL}/rate_limit")
        if response.status_code == 200:
            rate_limit = response.json()
            remaining = rate_limit['resources']['core']['remaining']
            if remaining < 10:
                reset_time = rate_limit['resources']['core']['reset']
                wait_time = reset_time - int(time.time()) + 5
                if wait_time > 0:
                    print(f"Rate limit low ({remaining} remaining). Waiting {wait_time}s...")
                    time.sleep(wait_time)

    def _api_request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Make an API request with rate limit checking."""
        self._check_rate_limit()
        response = self.session.request(method, url, timeout=30, **kwargs)
        
        if response.status_code == 403:
            rate_limit_info = response.headers.get('X-RateLimit-Remaining', 'unknown')
            if rate_limit_info == '0':
                reset_time = response.headers.get('X-RateLimit-Reset', '0')
                wait_time = int(reset_time) - int(time.time()) + 5
                if wait_time > 0:
                    print(f"Rate limit exceeded. Waiting {wait_time}s...")
                    time.sleep(wait_time)
                    return self._api_request(method, url, **kwargs)
        
        return response

    def _strip_json_comments(self, text: str) -> str:
        """Remove comments from JSON text (supports // and /* */ style comments)."""
        lines = text.split('\n')
        result = []
        in_multiline_comment = False
        
        for line in lines:
            if in_multiline_comment:
                # Check if this line ends the multi-line comment
                if '*/' in line:
                    # Process the part after */
                    end_idx = line.find('*/')
                    line = line[end_idx + 2:]
                    in_multiline_comment = False
                else:
                    # Entire line is part of multi-line comment, skip it
                    continue
            
            i = 0
            new_line = []
            in_string = False
            escape_next = False
            
            while i < len(line):
                char = line[i]
                
                if escape_next:
                    new_line.append(char)
                    escape_next = False
                    i += 1
                    continue
                
                if char == '\\' and in_string:
                    escape_next = True
                    new_line.append(char)
                    i += 1
                    continue
                
                if char == '"' and not escape_next:
                    in_string = not in_string
                    new_line.append(char)
                    i += 1
                    continue
                
                if not in_string:
                    # Check for multi-line comment start
                    if i < len(line) - 1 and line[i:i+2] == '/*':
                        in_multiline_comment = True
                        # Check if comment ends on same line
                        if '*/' in line[i+2:]:
                            end_idx = line.find('*/', i + 2)
                            i = end_idx + 2
                            continue
                        else:
                            # Comment continues to next line, stop processing this line
                            break
                    
                    # Check for single-line comment
                    if i < len(line) - 1 and line[i:i+2] == '//':
                        # Rest of line is a comment, stop processing
                        break
                
                new_line.append(char)
                i += 1
            
            # Add the processed line (may be empty if entire line was comment)
            result.append(''.join(new_line))
        
        return '\n'.join(result)

    def validate_config(self, config_path: str, schema_path: str) -> Dict[str, Any]:
        """Validate the configuration file against the schema."""
        # Load config with comment stripping
        try:
            with open(config_path, 'r') as f:
                content = f.read()
            # Strip comments before parsing
            content = self._strip_json_comments(content)
            config = json.loads(content)
        except FileNotFoundError:
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in configuration file: {e}")

        # Load schema with comment stripping
        try:
            with open(schema_path, 'r') as f:
                content = f.read()
            # Strip comments before parsing
            content = self._strip_json_comments(content)
            schema = json.loads(content)
        except FileNotFoundError:
            raise FileNotFoundError(f"Schema file not found: {schema_path}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in schema file: {e}")

        # Validate
        try:
            jsonschema.validate(instance=config, schema=schema)
        except jsonschema.ValidationError as e:
            raise ValueError(f"Configuration validation failed: {e.message}")

        return config

    def parse_milestone_url(self, url: str) -> Tuple[str, str, int]:
        """Parse a GitHub milestone URL to extract owner, repo, and milestone number."""
        pattern = r'^https://github\.com/([^/]+)/([^/]+)/milestone/(\d+)$'
        match = re.match(pattern, url)
        if not match:
            raise ValueError(f"Invalid milestone URL format: {url}")
        return match.group(1), match.group(2), int(match.group(3))

    def get_reference_milestone(self, url: str) -> Optional[Dict[str, Any]]:
        """Fetch a reference milestone from another repository."""
        try:
            owner, repo, milestone_number = self.parse_milestone_url(url)
            api_url = f"{self.BASE_URL}/repos/{owner}/{repo}/milestones/{milestone_number}"
            response = self._api_request('GET', api_url)
            
            if response.status_code == 404:
                print(f"Warning: Reference milestone not found: {url}")
                return None
            
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error fetching reference milestone {url}: {e}")
            return None

    def list_milestones(self, owner: str, repo: str, state: str = 'all') -> List[Dict[str, Any]]:
        """List all milestones for a repository."""
        url = f"{self.BASE_URL}/repos/{owner}/{repo}/milestones"
        params = {'state': state, 'per_page': 100}
        all_milestones = []
        page = 1

        while True:
            params['page'] = page
            response = self._api_request('GET', url, params=params)
            response.raise_for_status()
            
            milestones = response.json()
            if not milestones:
                break
            
            all_milestones.extend(milestones)
            page += 1
            
            # GitHub API returns max 100 per page
            if len(milestones) < 100:
                break

        return all_milestones

    def find_milestone_by_name(self, owner: str, repo: str, name: str) -> Optional[Dict[str, Any]]:
        """Find a milestone by name in a repository."""
        milestones = self.list_milestones(owner, repo, state='all')
        for milestone in milestones:
            if milestone['title'] == name:
                return milestone
        return None

    def create_milestone(self, owner: str, repo: str, title: str, 
                         description: Optional[str] = None, 
                         due_on: Optional[str] = None) -> Dict[str, Any]:
        """Create a new milestone."""
        url = f"{self.BASE_URL}/repos/{owner}/{repo}/milestones"
        data = {'title': title}
        
        if description is not None:
            data['description'] = description
        if due_on is not None:
            data['due_on'] = due_on

        response = self._api_request('POST', url, json=data)
        response.raise_for_status()
        return response.json()

    def update_milestone(self, owner: str, repo: str, milestone_number: int,
                         title: Optional[str] = None,
                         description: Optional[str] = None,
                         due_on: Optional[str] = None) -> Dict[str, Any]:
        """Update an existing milestone."""
        url = f"{self.BASE_URL}/repos/{owner}/{repo}/milestones/{milestone_number}"
        data = {}
        
        if title is not None:
            data['title'] = title
        if description is not None:
            data['description'] = description
        if due_on is not None:
            data['due_on'] = due_on

        response = self._api_request('PATCH', url, json=data)
        response.raise_for_status()
        return response.json()

    def resolve_milestone_name(self, milestone_config: Dict[str, Any]) -> str:
        """Resolve the milestone name from config or reference milestone."""
        if 'referenceMilestoneUrl' in milestone_config and milestone_config['referenceMilestoneUrl']:
            ref_milestone = self.get_reference_milestone(milestone_config['referenceMilestoneUrl'])
            if ref_milestone:
                return ref_milestone['title']
            # Fall back to name if reference fetch fails
            if 'name' in milestone_config:
                return milestone_config['name']
            raise ValueError("referenceMilestoneUrl failed and no name provided")
        
        if 'name' in milestone_config:
            return milestone_config['name']
        
        raise ValueError("Either name or referenceMilestoneUrl must be provided")

    def resolve_description(self, milestone_config: Dict[str, Any], 
                           reference_milestone: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Resolve the description based on config and reference milestone."""
        # If reference milestone is set, use pointer to URL
        if 'referenceMilestoneUrl' in milestone_config and milestone_config['referenceMilestoneUrl']:
            return f"See {milestone_config['referenceMilestoneUrl']}"
        
        # Otherwise, use provided description
        if 'description' not in milestone_config:
            return None  # Don't touch the field
        
        desc = milestone_config['description']
        if desc is None or desc == "":
            return None  # Clear the field
        return desc

    def resolve_due_date(self, milestone_config: Dict[str, Any],
                         reference_milestone: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Resolve the due date based on config and reference milestone."""
        # If reference milestone is set, use its due date
        if 'referenceMilestoneUrl' in milestone_config and milestone_config['referenceMilestoneUrl']:
            if reference_milestone and reference_milestone.get('due_on'):
                # GitHub API returns ISO 8601 format, keep it as is
                return reference_milestone['due_on']
            return None
        
        # Otherwise, use provided due date
        if 'dueDate' not in milestone_config:
            return None  # Don't touch the field
        
        due_date = milestone_config['dueDate']
        if due_date is None or due_date == "":
            return None  # Clear the field
        
        # Validate and format date (YYYY-MM-DD -> ISO 8601)
        try:
            # Parse YYYY-MM-DD and convert to ISO 8601 format (YYYY-MM-DDTHH:MM:SSZ)
            dt = datetime.strptime(due_date, '%Y-%m-%d')
            return dt.strftime('%Y-%m-%dT00:00:00Z')
        except ValueError:
            raise ValueError(f"Invalid date format: {due_date}. Expected YYYY-MM-DD")

    def process_milestone(self, repo: str, milestone_config: Dict[str, Any],
                         dry_run: bool = False) -> Dict[str, Any]:
        """Process a single milestone for a repository."""
        owner, repo_name = repo.split('/', 1)
        result = {
            'repo': repo,
            'action': None,
            'milestone_number': None,
            'milestone_url': None,
            'name': None,
            'error': None,
            'previous_name': None,
            'previous_description': None,
            'previous_due_date': None,
            'new_name': None,
            'new_description': None,
            'new_due_date': None
        }

        try:
            # Resolve milestone name
            milestone_name = self.resolve_milestone_name(milestone_config)
            result['name'] = milestone_name

            # Get reference milestone if needed
            reference_milestone = None
            if 'referenceMilestoneUrl' in milestone_config and milestone_config['referenceMilestoneUrl']:
                reference_milestone = self.get_reference_milestone(milestone_config['referenceMilestoneUrl'])

            # Resolve description and due date
            description = self.resolve_description(milestone_config, reference_milestone)
            due_date = self.resolve_due_date(milestone_config, reference_milestone)

            # Find existing milestone to update - check BOTH names before creating:
            # 1. Check for milestone with existingNameToRename name (if provided)
            # 2. Check for milestone with reference milestone name (if referenceMilestoneUrl provided)
            # 3. Only create new milestone if neither exists
            existing_milestone = None
            found_by_rename = False
            
            # First, check for milestone with existingNameToRename name
            if 'existingNameToRename' in milestone_config and milestone_config['existingNameToRename']:
                existing_milestone = self.find_milestone_by_name(
                    owner, repo_name, milestone_config['existingNameToRename']
                )
                if existing_milestone:
                    found_by_rename = True
            
            # Also check for milestone with reference milestone name (if not already found)
            if not existing_milestone and reference_milestone:
                # milestone_name is already the reference milestone's title at this point
                existing_milestone = self.find_milestone_by_name(owner, repo_name, milestone_name)
            
            # Fallback: check if milestone with resolved name already exists
            # (handles case where name is provided directly without reference or existingNameToRename)
            if not existing_milestone:
                existing_milestone = self.find_milestone_by_name(owner, repo_name, milestone_name)

            # Store new values
            result['new_name'] = milestone_name
            result['new_description'] = description
            result['new_due_date'] = due_date

            # Determine if we're creating or updating
            if existing_milestone:
                # Update existing milestone
                # Capture previous values
                result['previous_name'] = existing_milestone.get('title')
                result['previous_description'] = existing_milestone.get('description') or None
                result['previous_due_date'] = existing_milestone.get('due_on') or None
                
                # If we found it by existingNameToRename, we need to rename it to the target name
                # (which could be from referenceMilestoneUrl or the provided name)
                needs_rename = found_by_rename and existing_milestone['title'] != milestone_name
                
                if not dry_run:
                    updated = self.update_milestone(
                        owner, repo_name, existing_milestone['number'],
                        title=milestone_name if needs_rename else None,
                        description=description,
                        due_on=due_date
                    )
                    result['milestone_number'] = updated['number']
                    result['action'] = 'updated'
                else:
                    result['milestone_number'] = existing_milestone['number']
                    result['action'] = 'update'
            else:
                # Create new milestone - no previous values
                result['previous_name'] = None
                result['previous_description'] = None
                result['previous_due_date'] = None
                
                if not dry_run:
                    created = self.create_milestone(
                        owner, repo_name, milestone_name,
                        description=description,
                        due_on=due_date
                    )
                    result['milestone_number'] = created['number']
                    result['action'] = 'created'
                else:
                    result['action'] = 'create'

            # Build milestone URL
            if result['milestone_number']:
                result['milestone_url'] = f"https://github.com/{owner}/{repo_name}/milestone/{result['milestone_number']}"

        except Exception as e:
            result['error'] = str(e)

        return result

    def _format_value_change(self, field_name: str, previous: Optional[str], new: Optional[str], is_date: bool = False) -> str:
        """Format a field change for display."""
        # For dates, normalize None and empty strings
        if is_date:
            prev_str = previous if previous and previous != "(not set)" else "(not set)"
            new_str = new if new and new != "(not set)" else "(not set)"
        else:
            prev_str = previous if previous is not None else "(not set)"
            new_str = new if new is not None else "(not set)"
        
        # Compare normalized values
        prev_normalized = prev_str if prev_str != "(not set)" else None
        new_normalized = new_str if new_str != "(not set)" else None
        
        if prev_normalized == new_normalized:
            return f"    {field_name}: {new_str} (unchanged)"
        else:
            return f"    {field_name}: {prev_str} → {new_str}"

    def _format_date(self, date_str: Optional[str]) -> Optional[str]:
        """Format a date string for display (YYYY-MM-DDTHH:MM:SSZ -> YYYY-MM-DD)."""
        if not date_str:
            return None
        try:
            # Parse ISO 8601 format and return just the date part
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return dt.strftime('%Y-%m-%d')
        except (ValueError, AttributeError):
            return date_str

    def run(self, config: Dict[str, Any], dry_run: bool = False) -> List[Dict[str, Any]]:
        """Execute the milestone creation/update process."""
        results = []
        repos = config.get('repos', [])
        milestones = config.get('milestones', [])

        print(f"Processing {len(milestones)} milestone(s) across {len(repos)} repository/repositories...")
        if dry_run:
            print("DRY RUN MODE - No changes will be made\n")

        for repo in repos:
            print(f"\nRepository: {repo}")
            print("-" * 80)
            
            for milestone_config in milestones:
                result = self.process_milestone(repo, milestone_config, dry_run)
                results.append(result)
                
                if result['error']:
                    print(f"  ❌ Error: {result['error']}")
                else:
                    action = result['action']
                    name = result['new_name']
                    
                    # Format dates for display
                    prev_due_date = self._format_date(result['previous_due_date'])
                    new_due_date = self._format_date(result['new_due_date'])
                    
                    if dry_run:
                        if action == 'create':
                            print(f"  Would CREATE: {name}")
                            print(self._format_value_change("Name", None, name))
                            print(self._format_value_change("Description", None, result['new_description']))
                            print(self._format_value_change("Due Date", None, new_due_date, is_date=True))
                        elif action == 'update':
                            print(f"  Would UPDATE: {name} (milestone #{result['milestone_number']})")
                            print(self._format_value_change("Name", result['previous_name'], name))
                            print(self._format_value_change("Description", result['previous_description'], result['new_description']))
                            print(self._format_value_change("Due Date", prev_due_date, new_due_date, is_date=True))
                    else:
                        if action == 'created':
                            print(f"  ✅ Created: {name} - {result['milestone_url']}")
                            print(self._format_value_change("Name", None, name))
                            print(self._format_value_change("Description", None, result['new_description']))
                            print(self._format_value_change("Due Date", None, new_due_date, is_date=True))
                        elif action == 'updated':
                            print(f"  ✅ Updated: {name} - {result['milestone_url']}")
                            print(self._format_value_change("Name", result['previous_name'], name))
                            print(self._format_value_change("Description", result['previous_description'], result['new_description']))
                            print(self._format_value_change("Due Date", prev_due_date, new_due_date, is_date=True))

        return results

    def print_summary(self, results: List[Dict[str, Any]], dry_run: bool = False):
        """Print a summary of all operations."""
        print("\n" + "=" * 80)
        if dry_run:
            print("DRY RUN SUMMARY")
        else:
            print("EXECUTION SUMMARY")
        print("=" * 80)

        # Group by repo
        by_repo: Dict[str, List[Dict[str, Any]]] = {}
        for result in results:
            repo = result['repo']
            if repo not in by_repo:
                by_repo[repo] = []
            by_repo[repo].append(result)

        for repo, repo_results in by_repo.items():
            print(f"\n{repo}:")
            created = [r for r in repo_results if r['action'] in ('created', 'create')]
            updated = [r for r in repo_results if r['action'] in ('updated', 'update')]
            errors = [r for r in repo_results if r['error']]

            if not dry_run:
                if created:
                    print(f"  Created ({len(created)}):")
                    for r in created:
                        print(f"    - {r['name']}: {r['milestone_url']}")
                if updated:
                    print(f"  Updated ({len(updated)}):")
                    for r in updated:
                        print(f"    - {r['name']}: {r['milestone_url']}")
            else:
                if created:
                    print(f"  Would create ({len(created)}):")
                    for r in created:
                        print(f"    - {r['name']}")
                if updated:
                    print(f"  Would update ({len(updated)}):")
                    for r in updated:
                        print(f"    - {r['name']} (milestone #{r['milestone_number']})")

            if errors:
                print(f"  Errors ({len(errors)}):")
                for r in errors:
                    print(f"    - {r['name'] or 'Unknown'}: {r['error']}")

        total_created = len([r for r in results if r['action'] in ('created', 'create')])
        total_updated = len([r for r in results if r['action'] in ('updated', 'update')])
        total_errors = len([r for r in results if r['error']])

        print(f"\nTotal: {total_created} created, {total_updated} updated, {total_errors} errors")


def main():
    parser = argparse.ArgumentParser(
        description='Create/update GitHub milestones from JSON configuration',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run
  GITHUB_TOKEN=xxx python github-milestone-creator/github_milestone_creator.py --config milestones.json --dry-run

  # Execute
  GITHUB_TOKEN=xxx python github-milestone-creator/github_milestone_creator.py --config milestones.json
        """
    )
    parser.add_argument(
        '--config',
        required=True,
        help='Path to milestones.json configuration file'
    )
    parser.add_argument(
        '--token',
        help='GitHub personal access token (or set GITHUB_TOKEN env var)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without making changes'
    )

    args = parser.parse_args()

    # Get GitHub token
    github_token = args.token or os.getenv('GITHUB_TOKEN')
    if not github_token:
        print("Error: GitHub token required. Set GITHUB_TOKEN environment variable or use --token flag.")
        sys.exit(1)

    # Determine schema path (same directory as script)
    script_dir = Path(__file__).parent
    schema_path = script_dir / 'milestones-schema.json'

    # Validate and load config
    try:
        creator = GitHubMilestoneCreator(github_token)
        config = creator.validate_config(args.config, str(schema_path))
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

    # Run the process
    try:
        results = creator.run(config, dry_run=args.dry_run)
        creator.print_summary(results, dry_run=args.dry_run)
        
        # Exit with error code if there were errors
        errors = [r for r in results if r['error']]
        sys.exit(1 if errors else 0)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
