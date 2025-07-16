#!/usr/bin/env python3
"""
Slack Search Script

This script performs search queries against a Slack workspace using the Slack Web API.
It reads search queries from stdin (one per line) and outputs matching messages/threads.
"""

import os
import sys
import json
import requests
from datetime import datetime
from typing import List, Dict, Any
import argparse
import time

class SlackSearcher:
    def __init__(self, token: str, workspace: str = "filecoinproject"):
        self.token = token
        self.workspace = workspace
        self.headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        self.base_url = 'https://slack.com/api'
        self.session = requests.Session()
        self.session.headers.update(self.headers)
    
    def search_messages(self, query: str, count: int = 10) -> Dict[str, Any]:
        """Search for messages in the Slack workspace."""
        url = f"{self.base_url}/search.messages"
        params = {
            'query': query,
            'count': count,
            'sort': 'timestamp',
            'sort_dir': 'desc'
        }
        
        try:
            response = self.session.get(url, params=params, timeout=30)
            
            if response.status_code != 200:
                print(f"Error searching messages: {response.status_code}")
                if response.status_code == 429:
                    print("Rate limit exceeded. Waiting...")
                    time.sleep(60)
                    return self.search_messages(query, count)
                return {}
                
            data = response.json()
            if not data.get('ok'):
                print(f"Slack API error: {data.get('error', 'Unknown error')}")
                return {}
                
            return data
            
        except requests.exceptions.Timeout:
            print(f"Timeout searching for query: {query}")
            return {}
        except requests.exceptions.RequestException as e:
            print(f"Request error for query '{query}': {e}")
            return {}
    
    def get_channel_info(self, channel_id: str) -> str:
        """Get channel name from channel ID."""
        url = f"{self.base_url}/conversations.info"
        params = {'channel': channel_id}
        
        try:
            response = self.session.get(url, params=params, timeout=30)
            data = response.json()
            
            if data.get('ok') and data.get('channel'):
                return data['channel'].get('name', channel_id)
            return channel_id
            
        except:
            return channel_id
    
    def get_user_info(self, user_id: str) -> str:
        """Get user name from user ID."""
        url = f"{self.base_url}/users.info"
        params = {'user': user_id}
        
        try:
            response = self.session.get(url, params=params, timeout=30)
            data = response.json()
            
            if data.get('ok') and data.get('user'):
                return data['user'].get('name', user_id)
            return user_id
            
        except:
            return user_id
    
    def format_message(self, message: Dict[str, Any]) -> str:
        """Format a message for display."""
        # Extract basic info
        text = message.get('text', '')
        user_id = message.get('user', '')
        channel_id = message.get('channel', {}).get('id', '')
        timestamp = message.get('ts', '')
        
        # Convert timestamp to readable date
        if timestamp:
            try:
                dt = datetime.fromtimestamp(float(timestamp))
                date_str = dt.strftime('%Y-%m-%d %H:%M:%S')
            except:
                date_str = timestamp
        else:
            date_str = 'Unknown'
        
        # Get channel and user names
        channel_name = self.get_channel_info(channel_id) if channel_id else 'Unknown'
        user_name = self.get_user_info(user_id) if user_id else 'Unknown'
        
        # Format message
        output = []
        output.append(f"Channel: #{channel_name}")
        output.append(f"User: {user_name}")
        output.append(f"Date: {date_str}")
        output.append(f"Message: {text}")
        
        # Add permalink if available
        if message.get('permalink'):
            output.append(f"Link: {message['permalink']}")
        
        return '\n'.join(output)
    
    def search_and_format(self, query: str) -> str:
        """Search for messages and format the results."""
        print(f"Searching for: '{query}'", file=sys.stderr)
        
        results = self.search_messages(query)
        
        if not results or not results.get('messages'):
            return f"No results found for query: '{query}'"
        
        messages = results['messages']['matches']
        total_count = results['messages']['total']
        
        # Limit to 10 most recent results
        messages = messages[:10]
        
        output = []
        output.append(f"=== Search Results for: '{query}' ===")
        output.append(f"Total matches: {total_count}")
        output.append(f"Showing: {len(messages)} most recent results")
        output.append("")
        
        for i, message in enumerate(messages, 1):
            output.append(f"--- Result {i} ---")
            output.append(self.format_message(message))
            output.append("")
        
        return '\n'.join(output)

def main():
    parser = argparse.ArgumentParser(description='Search Slack workspace for messages')
    parser.add_argument('--token', help='Slack User OAuth Token (or set SLACK_USER_TOKEN env var)')
    parser.add_argument('--workspace', default='filecoinproject', help='Slack workspace name (default: filecoinproject)')
    parser.add_argument('--output', '-o', help='Output file (default: stdout)')
    parser.add_argument('--count', '-c', type=int, default=10, help='Number of results per query (default: 10)')
    parser.add_argument('queries', nargs='*', help='Search queries (or read from stdin)')
    
    args = parser.parse_args()
    
    # Get Slack token
    token = args.token or os.getenv('SLACK_USER_TOKEN')
    if not token:
        print("Error: Slack user token required. Set SLACK_USER_TOKEN environment variable or use --token flag.")
        print("To get a user token:")
        print("1. Go to https://api.slack.com/apps")
        print("2. Create a new app using the provided manifest")
        print("3. Go to 'OAuth & Permissions'")
        print("4. Install the app to your workspace")
        print("5. Copy the 'User OAuth Token' (starts with xoxp-)")
        print("Note: User tokens can search all channels you have access to (including private channels)")
        sys.exit(1)
    
    searcher = SlackSearcher(token, args.workspace)
    
    # Get queries from command line args or stdin
    if args.queries:
        queries = args.queries
    else:
        print("Enter search queries (one per line, Ctrl+D to finish):", file=sys.stderr)
        queries = []
        try:
            for line in sys.stdin:
                query = line.strip()
                if query:
                    queries.append(query)
        except KeyboardInterrupt:
            print("\nSearch cancelled.", file=sys.stderr)
            sys.exit(1)
    
    if not queries:
        print("No queries provided.", file=sys.stderr)
        sys.exit(1)
    
    # Perform searches
    results = []
    for query in queries:
        try:
            result = searcher.search_and_format(query)
            results.append(result)
            results.append("=" * 80)
            results.append("")
        except Exception as e:
            print(f"Error searching for '{query}': {e}", file=sys.stderr)
            continue
    
    # Output results
    output_text = '\n'.join(results)
    
    if args.output:
        with open(args.output, 'w') as f:
            f.write(output_text)
        print(f"Results saved to {args.output}", file=sys.stderr)
    else:
        print(output_text)

if __name__ == '__main__':
    main()