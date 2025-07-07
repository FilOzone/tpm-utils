#!/usr/bin/env python3
"""
GitHub PR Report Generator

This script queries GitHub repositories for PR information and generates
a report with open non-draft PR counts and detailed PR summaries.
"""

import os
import sys
import json
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Any
import argparse

class GitHubPRReporter:
    def __init__(self, token: str):
        self.token = token
        self.headers = {
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        self.base_url = 'https://api.github.com'
    
    def get_repo_prs(self, repo: str, state: str = 'open') -> List[Dict[str, Any]]:
        """Get all PRs for a repository."""
        url = f"{self.base_url}/repos/{repo}/pulls"
        params = {'state': state, 'per_page': 100}
        
        all_prs = []
        page = 1
        
        while True:
            params['page'] = page
            response = requests.get(url, headers=self.headers, params=params)
            
            if response.status_code != 200:
                print(f"Error fetching PRs for {repo}: {response.status_code}")
                break
                
            prs = response.json()
            if not prs:
                break
                
            all_prs.extend(prs)
            page += 1
            
        return all_prs
    
    def count_open_non_draft_prs(self, repo: str) -> int:
        """Count open non-draft PRs for a repository."""
        prs = self.get_repo_prs(repo, 'open')
        return len([pr for pr in prs if not pr.get('draft', False)])
    
    def get_pr_summary(self, repo: str, months: int = 3) -> List[Dict[str, Any]]:
        """Get PR summary for the last N months."""
        cutoff_date = datetime.now() - timedelta(days=months * 30)
        
        # Get both open and closed PRs
        open_prs = self.get_repo_prs(repo, 'open')
        closed_prs = self.get_repo_prs(repo, 'closed')
        
        all_prs = open_prs + closed_prs
        
        recent_prs = []
        for pr in all_prs:
            created_date = datetime.strptime(pr['created_at'], '%Y-%m-%dT%H:%M:%SZ')
            updated_date = datetime.strptime(pr['updated_at'], '%Y-%m-%dT%H:%M:%SZ')
            
            # Include PRs that were created or modified in the last N months
            if created_date >= cutoff_date or updated_date >= cutoff_date:
                status = "draft" if pr.get('draft', False) else "ready for review"
                if pr['state'] == 'closed':
                    status = "closed"
                
                recent_prs.append({
                    'repo': repo,
                    'number': pr['number'],
                    'title': pr['title'],
                    'author': pr['user']['login'],
                    'created_date': created_date.strftime('%Y-%m-%d'),
                    'updated_date': updated_date.strftime('%Y-%m-%d'),
                    'status': status,
                    'url': pr['html_url']
                })
        
        return sorted(recent_prs, key=lambda x: x['updated_date'], reverse=True)
    
    def generate_report(self, repos: List[str]) -> str:
        """Generate the full report."""
        report = []
        
        # Summary table
        report.append("=== Open Non-Draft PR Count Summary ===")
        report.append("Repository\tOpen Non-Draft PRs")
        
        total_prs = 0
        for repo in repos:
            count = self.count_open_non_draft_prs(repo)
            total_prs += count
            report.append(f"{repo}\t{count}")
        
        report.append(f"TOTAL\t{total_prs}")
        report.append("")
        
        # Detailed PR information
        report.append("=== PR Details (Last 3 Months) ===")
        report.append("Repository\tPR Number\tCreated Date\tLast Modified\tTitle\tAuthor\tStatus\tURL")
        
        all_recent_prs = []
        for repo in repos:
            recent_prs = self.get_pr_summary(repo)
            all_recent_prs.extend(recent_prs)
        
        # Sort by last modified date
        all_recent_prs.sort(key=lambda x: x['updated_date'], reverse=True)
        
        for pr in all_recent_prs:
            report.append(f"{pr['repo']}\t{pr['number']}\t{pr['created_date']}\t{pr['updated_date']}\t{pr['title']}\t{pr['author']}\t{pr['status']}\t{pr['url']}")
        
        return "\n".join(report)

def main():
    parser = argparse.ArgumentParser(description='Generate GitHub PR report')
    parser.add_argument('repos', nargs='+', help='GitHub repositories in format owner/repo')
    parser.add_argument('--token', help='GitHub personal access token (or set GITHUB_TOKEN env var)')
    parser.add_argument('--output', '-o', help='Output file (default: stdout)')
    
    args = parser.parse_args()
    
    # Get GitHub token
    token = args.token or os.getenv('GITHUB_TOKEN')
    if not token:
        print("Error: GitHub token required. Set GITHUB_TOKEN environment variable or use --token flag.")
        sys.exit(1)
    
    reporter = GitHubPRReporter(token)
    
    try:
        report = reporter.generate_report(args.repos)
        
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