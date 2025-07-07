#!/usr/bin/env python3
"""
Team PR Report Generator

This script queries GitHub for all open PRs created by team members
and generates a report with pretty-formatted tables.
"""

import os
import sys
import json
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Any
import argparse
import time

class GitHubTeamPRReporter:
    def __init__(self, token: str):
        self.token = token
        self.headers = {
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        self.base_url = 'https://api.github.com'
        self.session = requests.Session()
        self.session.headers.update(self.headers)
    
    def get_user_prs(self, username: str) -> List[Dict[str, Any]]:
        """Get all open PRs for a specific user using GitHub search API."""
        url = f"{self.base_url}/search/issues"
        params = {
            'q': f'type:pr state:open author:{username}',
            'sort': 'updated',
            'order': 'desc',
            'per_page': 100
        }
        
        print(f"Fetching open PRs for {username}...", end="", flush=True)
        
        all_prs = []
        page = 1
        
        while page <= 10:  # Limit to 10 pages (1000 PRs max)
            params['page'] = page
            try:
                response = self.session.get(url, params=params, timeout=30)
                
                if response.status_code != 200:
                    print(f"\nError fetching PRs for {username}: {response.status_code}")
                    if response.status_code == 403:
                        print("Rate limit exceeded. Waiting...")
                        time.sleep(60)
                        continue
                    break
                    
                data = response.json()
                prs = data.get('items', [])
                
                if not prs:
                    break
                
                all_prs.extend(prs)
                
                # Check if we've reached the end
                if len(prs) < 100:
                    break
                    
                page += 1
                
                if page % 3 == 0:
                    print(".", end="", flush=True)
                    
            except requests.exceptions.Timeout:
                print(f"\nTimeout fetching PRs for {username}")
                break
            except requests.exceptions.RequestException as e:
                print(f"\nRequest error for {username}: {e}")
                break
        
        print(f" Found {len(all_prs)} PRs")
        return all_prs
    
    def format_pr_data(self, pr: Dict[str, Any]) -> Dict[str, Any]:
        """Format PR data for display."""
        created_date = datetime.strptime(pr['created_at'], '%Y-%m-%dT%H:%M:%SZ')
        updated_date = datetime.strptime(pr['updated_at'], '%Y-%m-%dT%H:%M:%SZ')
        
        # Extract repository name from URL
        repo_name = pr['repository_url'].split('/')[-2] + '/' + pr['repository_url'].split('/')[-1]
        
        # Determine if it's a draft (GitHub search API doesn't always include this)
        status = "draft" if pr.get('draft', False) else "ready for review"
        
        return {
            'username': pr['user']['login'],
            'repo': repo_name,
            'number': pr['number'],
            'title': pr['title'],
            'created_date': created_date.strftime('%Y-%m-%d'),
            'updated_date': updated_date.strftime('%Y-%m-%d'),
            'status': status,
            'url': pr['html_url'],
            'updated_datetime': updated_date  # Keep for sorting
        }
    
    def generate_report(self, usernames: List[str]) -> str:
        """Generate the team PR report."""
        report = []
        
        # Fetch all PRs for all users
        all_prs = []
        for username in usernames:
            user_prs = self.get_user_prs(username)
            for pr in user_prs:
                formatted_pr = self.format_pr_data(pr)
                all_prs.append(formatted_pr)
        
        if not all_prs:
            return "No open PRs found for any team members."
        
        # Sort by username ascending, then by last modified date descending
        all_prs.sort(key=lambda x: (x['username'], -x['updated_datetime'].timestamp()))
        
        # Group PRs by username
        current_user = None
        user_prs = []
        
        report.append("=== Team Member Open PRs ===")
        report.append("")
        
        for pr in all_prs:
            if current_user != pr['username']:
                # Process previous user's PRs
                if current_user is not None:
                    self._add_user_section(report, current_user, user_prs)
                
                # Start new user
                current_user = pr['username']
                user_prs = []
            
            user_prs.append(pr)
        
        # Process final user's PRs
        if current_user is not None:
            self._add_user_section(report, current_user, user_prs)
        
        # Add summary
        report.append("=== Summary ===")
        user_counts = {}
        for pr in all_prs:
            user_counts[pr['username']] = user_counts.get(pr['username'], 0) + 1
        
        for username in sorted(user_counts.keys()):
            report.append(f"{username}: {user_counts[username]} open PRs")
        
        report.append(f"Total: {len(all_prs)} open PRs across {len(user_counts)} team members")
        
        return "\n".join(report)
    
    def _add_user_section(self, report: List[str], username: str, user_prs: List[Dict[str, Any]]):
        """Add a user section to the report."""
        report.append(f"User: {username}")
        report.append("-" * 120)
        
        # Format as pretty table
        headers = ["Repo", "PR#", "Created", "Modified", "Title", "Status", "URL"]
        rows = []
        
        for pr in user_prs:
            # Truncate title if too long
            title = pr['title'][:60] + "..." if len(pr['title']) > 60 else pr['title']
            rows.append([
                pr['repo'],
                str(pr['number']),
                pr['created_date'],
                pr['updated_date'],
                title,
                pr['status'],
                pr['url']
            ])
        
        # Calculate column widths
        col_widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                col_widths[i] = max(col_widths[i], len(str(cell)))
        
        # Format header
        header_row = "  ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
        report.append(header_row)
        report.append("  ".join("-" * col_widths[i] for i in range(len(headers))))
        
        # Format data rows
        for row in rows:
            formatted_row = "  ".join(str(cell).ljust(col_widths[i]) for i, cell in enumerate(row))
            report.append(formatted_row)
        
        report.append("")

def main():
    parser = argparse.ArgumentParser(description='Generate team member PR report')
    parser.add_argument('usernames', nargs='+', help='GitHub usernames of team members')
    parser.add_argument('--token', help='GitHub personal access token (or set GITHUB_TOKEN env var)')
    parser.add_argument('--output', '-o', help='Output file (default: stdout)')
    
    args = parser.parse_args()
    
    # Get GitHub token
    token = args.token or os.getenv('GITHUB_TOKEN')
    if not token:
        print("Error: GitHub token required. Set GITHUB_TOKEN environment variable or use --token flag.")
        sys.exit(1)
    
    reporter = GitHubTeamPRReporter(token)
    
    try:
        report = reporter.generate_report(args.usernames)
        
        if args.output:
            with open(args.output, 'w') as f:
                f.write(report)
            print(f"Report saved to {args.output}")
        else:
            print(report)
            
    except Exception as e:
        print(f"Error generating report: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()