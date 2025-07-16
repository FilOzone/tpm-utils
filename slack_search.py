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
from typing import List, Dict, Any, Optional
import argparse
import time
from dataclasses import dataclass, asdict

@dataclass
class SearchResult:
    """Represents a single search result message."""
    channel_id: str
    channel_name: str
    user_id: str
    user_name: str
    timestamp: str
    date: str
    text: str
    permalink: str
    query: str
    result_number: int

@dataclass
class QueryResults:
    """Represents all results for a single query."""
    query: str
    total_matches: int
    results: List[SearchResult]
    filtered_count: int = 0

@dataclass
class SearchSession:
    """Represents a complete search session with multiple queries."""
    queries: List[QueryResults]
    excluded_urls: List[str]
    timestamp: str
    workspace: str

class SlackSearcher:
    def __init__(self, token: str, workspace: str = "filecoinproject", excluded_urls: List[str] = None):
        self.token = token
        self.workspace = workspace
        self.excluded_urls = set(excluded_urls) if excluded_urls else set()
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
    
    def search_and_collect(self, query: str, count: int = 10) -> QueryResults:
        """Search for messages and collect data into structured format."""
        print(f"Searching for: '{query}'", file=sys.stderr)
        
        results = self.search_messages(query, count)
        
        if not results or not results.get('messages'):
            return QueryResults(query=query, total_matches=0, results=[])
        
        messages = results['messages']['matches']
        total_count = results['messages']['total']
        
        # Filter out excluded URLs
        filtered_count = 0
        if self.excluded_urls:
            original_count = len(messages)
            messages = [msg for msg in messages if msg.get('permalink') not in self.excluded_urls]
            filtered_count = original_count - len(messages)
            if filtered_count > 0:
                print(f"Filtered out {filtered_count} excluded messages", file=sys.stderr)
        
        # Limit to specified count
        messages = messages[:count]
        
        print(f"Resolving channel and user names...", file=sys.stderr)
        
        search_results = []
        for i, message in enumerate(messages, 1):
            # Extract basic info
            text = message.get('text', '')
            user_id = message.get('user', '')
            channel_id = message.get('channel', {}).get('id', '')
            timestamp = message.get('ts', '')
            permalink = message.get('permalink', '')
            
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
            
            # Clean up code block formatting
            cleaned_text = text
            if '```' in cleaned_text:
                import re
                cleaned_text = re.sub(r'```([^\n])', r'```\n\1', cleaned_text)
                cleaned_text = re.sub(r'([^\n])```', r'\1\n```', cleaned_text)
            
            search_result = SearchResult(
                channel_id=channel_id,
                channel_name=channel_name,
                user_id=user_id,
                user_name=user_name,
                timestamp=timestamp,
                date=date_str,
                text=cleaned_text,
                permalink=permalink,
                query=query,
                result_number=i
            )
            search_results.append(search_result)
        
        # Print cache statistics
        print(f"Cache stats - Channels: {len(self.channel_cache)}, Users: {len(self.user_cache)}", file=sys.stderr)
        
        return QueryResults(
            query=query,
            total_matches=total_count,
            results=search_results,
            filtered_count=filtered_count
        )

class SearchResultsRenderer:
    """Renders search results data model to various formats."""
    
    @staticmethod
    def to_json(session: SearchSession) -> str:
        """Convert search session to JSON string."""
        return json.dumps(asdict(session), indent=2)
    
    @staticmethod
    def from_json(json_str: str) -> SearchSession:
        """Create search session from JSON string."""
        data = json.loads(json_str)
        
        # Convert back to dataclass instances
        queries = []
        for query_data in data['queries']:
            results = [SearchResult(**result) for result in query_data['results']]
            query_results = QueryResults(
                query=query_data['query'],
                total_matches=query_data['total_matches'],
                results=results,
                filtered_count=query_data.get('filtered_count', 0)
            )
            queries.append(query_results)
        
        return SearchSession(
            queries=queries,
            excluded_urls=data['excluded_urls'],
            timestamp=data['timestamp'],
            workspace=data['workspace']
        )
    
    @staticmethod
    def to_markdown(session: SearchSession) -> str:
        """Convert search session to markdown format."""
        if not session.queries:
            return "# Slack Search Results\n\nNo queries found."
        
        output = []
        
        # Generate table of contents
        toc = ["# Slack Search Results", "", "## Table of Contents", ""]
        import re
        
        for i, query_results in enumerate(session.queries, 1):
            # Create markdown-friendly anchor link for query
            query_anchor = query_results.query.lower().replace(' ', '-')
            query_anchor = re.sub(r'[^a-z0-9\-]', '', query_anchor)
            toc.append(f"{i}. [{query_results.query}](#{query_anchor})")
            
            # Add sub-items for each result
            for j, result in enumerate(query_results.results, 1):
                # Extract just the date part (YYYY-MM-DD)
                date = result.date.split(' ')[0] if ' ' in result.date else result.date
                
                # Create anchor for the result heading
                result_anchor = f"{query_results.query}-result-{j}".lower().replace(' ', '-')
                result_anchor = re.sub(r'[^a-z0-9\-]', '', result_anchor)
                toc.append(f"   {i}.{j} [{date} - {result.channel_name} - {result.user_name}](#{result_anchor})")
        
        toc.append("")
        output.extend(toc)
        
        # Add search results
        for query_results in session.queries:
            output.append(f"## {query_results.query}")
            output.append("")
            output.append(f"**Total matches:** {query_results.total_matches}")
            output.append(f"**Showing:** {len(query_results.results)} most recent results")
            output.append("")
            
            for result in query_results.results:
                output.append(f"### {query_results.query} Result {result.result_number}")
                output.append("")
                output.append(f"**Channel:** #{result.channel_name}")
                output.append(f"**User:** {result.user_name}")
                output.append(f"**Date:** {result.date}")
                
                # Add permalink if available
                if result.permalink:
                    output.append(f"**Link:** {result.permalink}")
                
                output.append(f"**Message:**\n{result.text}")
                output.append("")
            
            output.append("")
        
        return '\n'.join(output)

def main():
    parser = argparse.ArgumentParser(description='Search Slack workspace for messages')
    parser.add_argument('--token', help='Slack User OAuth Token (or set SLACK_USER_TOKEN env var)')
    parser.add_argument('--workspace', default='filecoinproject', help='Slack workspace name (default: filecoinproject)')
    parser.add_argument('--output', '-o', help='Output file (default: stdout)')
    parser.add_argument('--count', '-c', type=int, default=10, help='Number of results per query (default: 10)')
    parser.add_argument('--exclude-url', action='append', help='Exclude messages with these URLs from results (can be used multiple times)')
    parser.add_argument('--exclude-urls-file', help='File containing URLs to exclude (one per line)')
    
    # New workflow options
    parser.add_argument('--export-json', help='Export search results to JSON file')
    parser.add_argument('--import-json', help='Import search results from JSON file and convert to markdown')
    parser.add_argument('--format', choices=['markdown', 'json'], default='markdown', help='Output format (default: markdown)')
    
    parser.add_argument('queries', nargs='*', help='Search queries (or read from stdin)')
    
    args = parser.parse_args()
    
    # Handle import mode
    if args.import_json:
        try:
            with open(args.import_json, 'r') as f:
                json_data = f.read()
            
            session = SearchResultsRenderer.from_json(json_data)
            
            if args.format == 'markdown':
                output_text = SearchResultsRenderer.to_markdown(session)
            else:
                output_text = SearchResultsRenderer.to_json(session)
            
            if args.output:
                with open(args.output, 'w') as f:
                    f.write(output_text)
                print(f"Results saved to {args.output}", file=sys.stderr)
            else:
                print(output_text)
            
            return
            
        except FileNotFoundError:
            print(f"Error: JSON file not found: {args.import_json}", file=sys.stderr)
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON in {args.import_json}: {e}", file=sys.stderr)
            sys.exit(1)
    
    # Normal search mode - need token and queries
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
    
    # Process excluded URLs
    excluded_urls = []
    if args.exclude_url:
        excluded_urls.extend(args.exclude_url)
    
    if args.exclude_urls_file:
        try:
            with open(args.exclude_urls_file, 'r') as f:
                for line in f:
                    url = line.strip()
                    if url and not url.startswith('#'):  # Skip empty lines and comments
                        excluded_urls.append(url)
        except FileNotFoundError:
            print(f"Error: Exclude URLs file not found: {args.exclude_urls_file}", file=sys.stderr)
            sys.exit(1)
    
    if excluded_urls:
        print(f"Excluding {len(excluded_urls)} URLs from results", file=sys.stderr)
    
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
    
    # Perform searches and collect data
    searcher = SlackSearcher(token, args.workspace, excluded_urls)
    query_results = []
    
    for query in queries:
        try:
            result = searcher.search_and_collect(query, args.count)
            query_results.append(result)
        except Exception as e:
            print(f"Error searching for '{query}': {e}", file=sys.stderr)
            continue
    
    # Create search session
    session = SearchSession(
        queries=query_results,
        excluded_urls=excluded_urls,
        timestamp=datetime.now().isoformat(),
        workspace=args.workspace
    )
    
    # Export to JSON if requested
    if args.export_json:
        json_output = SearchResultsRenderer.to_json(session)
        with open(args.export_json, 'w') as f:
            f.write(json_output)
        print(f"Data exported to {args.export_json}", file=sys.stderr)
    
    # Generate output
    if args.format == 'json':
        output_text = SearchResultsRenderer.to_json(session)
    else:
        output_text = SearchResultsRenderer.to_markdown(session)
    
    if args.output:
        with open(args.output, 'w') as f:
            f.write(output_text)
        print(f"Results saved to {args.output}", file=sys.stderr)
    else:
        print(output_text)

if __name__ == '__main__':
    main()