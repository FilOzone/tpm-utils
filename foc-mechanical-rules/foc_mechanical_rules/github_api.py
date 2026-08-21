"""Thin REST helpers for repo-level (non-board) GitHub operations.

Board field reads/writes go through ``github_projects_client``. Everything
here targets issue/PR endpoints that live on the repo, not the project
board (see foc-board-rules/README.md general behavior rule 13).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import requests

# Orgs where we have write access to manage assignees, milestones, reviewers,
# etc. Items from repos outside these orgs are "external items" (see
# foc-board-rules/status-lifecycle.md#terminology).
BLESSED_ORGS = {"FilOzone", "filecoin-project"}

FILOZ_ORG = "FilOzone"
PROJECT_NUMBER = 14


def build_session(token: str) -> requests.Session:
    """Build a requests.Session authenticated with the given token."""
    session = requests.Session()
    session.headers.update(
        {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
    )
    return session


def parse_repo_ref(repository: str) -> tuple[str, str]:
    """Split a 'owner/repo' board Repository field value into (owner, repo)."""
    owner, _, repo = repository.partition("/")
    return owner, repo


def get_pull_request(
    session: requests.Session, *, owner: str, repo: str, number: str
) -> Dict[str, Any]:
    """Fetch a single PR's metadata."""
    resp = session.get(
        f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}",
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def get_issue_events(
    session: requests.Session, *, owner: str, repo: str, number: str
) -> List[Dict[str, Any]]:
    """Fetch an issue/PR's timeline events (used to detect a prior 'unassigned')."""
    events: List[Dict[str, Any]] = []
    url: Optional[str] = (
        f"https://api.github.com/repos/{owner}/{repo}/issues/{number}/events"
    )
    params: Optional[Dict[str, Any]] = {"per_page": 100}
    while url:
        resp = session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        events.extend(resp.json())
        url = resp.links.get("next", {}).get("url")
        params = None
    return events


def add_assignee(
    session: requests.Session, *, owner: str, repo: str, number: str, login: str
) -> None:
    """Add an assignee to an issue/PR."""
    resp = session.post(
        f"https://api.github.com/repos/{owner}/{repo}/issues/{number}/assignees",
        json={"assignees": [login]},
        timeout=30,
    )
    resp.raise_for_status()
