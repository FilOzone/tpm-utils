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
        
        # In-memory caches for channel and user names
        self.channel_cache = {}
        self.user_cache = {}
    
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
        """Get channel name from channel ID with caching."""
        if not channel_id:
            return 'Unknown'
            
        # Check cache first
        if channel_id in self.channel_cache:
            return self.channel_cache[channel_id]
            
        # Fetch from API
        url = f"{self.base_url}/conversations.info"
        params = {'channel': channel_id}
        
        try:
            response = self.session.get(url, params=params, timeout=30)
            data = response.json()
            
            if data.get('ok') and data.get('channel'):
                channel_name = data['channel'].get('name', channel_id)
                # Cache the result
                self.channel_cache[channel_id] = channel_name
                return channel_name
            else:
                # Cache the fallback too
                self.channel_cache[channel_id] = channel_id
                return channel_id
                
        except Exception as e:
            print(f"Error fetching channel info for {channel_id}: {e}", file=sys.stderr)
            # Cache the fallback
            self.channel_cache[channel_id] = channel_id
            return channel_id
    
    def get_user_info(self, user_id: str) -> str:
        """Get user name from user ID with caching."""
        if not user_id:
            return 'Unknown'
            
        # Check cache first
        if user_id in self.user_cache:
            return self.user_cache[user_id]
            
        # Fetch from API
        url = f"{self.base_url}/users.info"
        params = {'user': user_id}
        
        try:
            response = self.session.get(url, params=params, timeout=30)
            data = response.json()
            
            if data.get('ok') and data.get('user'):
                # Try to get display name first, then real name, then username
                user = data['user']
                user_name = (user.get('profile', {}).get('display_name') or 
                           user.get('real_name') or 
                           user.get('name', user_id))
                # Cache the result
                self.user_cache[user_id] = user_name
                return user_name
            else:
                # Cache the fallback too
                self.user_cache[user_id] = user_id
                return user_id
                
        except Exception as e:
            print(f"Error fetching user info for {user_id}: {e}", file=sys.stderr)
            # Cache the fallback
            self.user_cache[user_id] = user_id
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
        
        # Format message in markdown
        output = []
        output.append(f"**Channel:** #{channel_name}")
        output.append(f"**User:** {user_name}")
        output.append(f"**Date:** {date_str}")
        
        # Add permalink if available
        if message.get('permalink'):
            output.append(f"**Link:** {message['permalink']}")
        
        # Clean up code block formatting - ensure triple backticks are on their own lines
        cleaned_text = text
        if '```' in cleaned_text:
            # Replace cases where text is adjacent to ```
            import re
            # Handle ```text -> ```\ntext
            cleaned_text = re.sub(r'```([^\n])', r'```\n\1', cleaned_text)
            # Handle text``` -> text\n```
            cleaned_text = re.sub(r'([^\n])```', r'\1\n```', cleaned_text)
        
        output.append(f"**Message:**\n{cleaned_text}")
        
        return '\n'.join(output)
    
    def search_and_format(self, query: str) -> str:
        """Search for messages and format the results."""
        print(f"Searching for: '{query}'", file=sys.stderr)
        
        results = self.search_messages(query)
        
        if not results or not results.get('messages'):
            return f"## {query}\n\nNo results found for query: '{query}'"
        
        messages = results['messages']['matches']
        total_count = results['messages']['total']
        
        # Limit to 10 most recent results
        messages = messages[:10]
        
        output = []
        output.append(f"## {query}")
        output.append("")
        output.append(f"**Total matches:** {total_count}")
        output.append(f"**Showing:** {len(messages)} most recent results")
        output.append("")
        
        print(f"Resolving channel and user names...", file=sys.stderr)
        
        for i, message in enumerate(messages, 1):
            # Create anchor-friendly query for result headings
            import re
            query_anchor = query.lower().replace(' ', '-')
            query_anchor = re.sub(r'[^a-z0-9\-]', '', query_anchor)
            
            output.append(f"### Result {i} {{#{query_anchor}-result-{i}}}")
            output.append("")
            output.append(self.format_message(message))
            output.append("")
        
        # Print cache statistics
        print(f"Cache stats - Channels: {len(self.channel_cache)}, Users: {len(self.user_cache)}", file=sys.stderr)
        
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
    query_results = []
    
    for query in queries:
        try:
            result = searcher.search_and_format(query)
            query_results.append({'query': query, 'result': result})
        except Exception as e:
            print(f"Error searching for '{query}': {e}", file=sys.stderr)
            continue
    
    # Generate table of contents
    if query_results:
        toc = ["# Slack Search Results", "", "## Table of Contents", ""]
        import re
        
        for i, qr in enumerate(query_results, 1):
            # Create markdown-friendly anchor link for query
            query_anchor = qr['query'].lower().replace(' ', '-')
            query_anchor = re.sub(r'[^a-z0-9\-]', '', query_anchor)
            toc.append(f"{i}. [{qr['query']}](#{query_anchor})")
            
            # Parse the result to extract result details for TOC
            result_lines = qr['result'].split('\n')
            result_num = 0
            
            i_line = 0
            while i_line < len(result_lines):
                line = result_lines[i_line]
                if line.startswith('### Result '):
                    result_num += 1
                    # Extract date, channel, and user from the next few lines
                    date = channel = user = "Unknown"
                    
                    # Look for the formatted message details in the following lines
                    for j in range(i_line + 1, min(i_line + 10, len(result_lines))):
                        if result_lines[j].startswith('**Channel:**'):
                            channel = result_lines[j].replace('**Channel:** #', '').strip()
                        elif result_lines[j].startswith('**User:**'):
                            user = result_lines[j].replace('**User:** ', '').strip()
                        elif result_lines[j].startswith('**Date:**'):
                            date = result_lines[j].replace('**Date:** ', '').strip()
                            # Extract just the date part (YYYY-MM-DD)
                            date = date.split(' ')[0] if ' ' in date else date
                    
                    result_anchor = f"{query_anchor}-result-{result_num}"
                    toc.append(f"   {i}.{result_num} [{date} - {channel} - {user}](#{result_anchor})")
                
                i_line += 1
                
        toc.append("")
        results.extend(toc)
    
    # Add search results
    for qr in query_results:
        results.append(qr['result'])
        results.append("")
    
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