"""Read the projects and epic links used by the FOC review queue."""

import re
import time
from collections.abc import Iterator
from typing import TypedDict
from urllib.parse import urlsplit
from uuid import UUID

from requests import HTTPError, Session

DEFAULT_NOTION_DATA_SOURCE_ID = "3f3dc419-50c1-80b0-bf72-000b0b8133b8"
EPICS_PROPERTY = "GitHub epics"
COMPLETED_STAGES = {"Released", "Launched", "Cancelled", "Engineering complete"}
ISSUE_PATH = re.compile(r"/([A-Za-z0-9-]+)/([A-Za-z0-9_.-]+)/issues/([1-9][0-9]*)/?")


class Project(TypedDict):
    title: str
    workstream: str
    url: str
    epic_urls: list[str]


def _issue_url(value: str) -> str | None:
    try:
        url = urlsplit(value)
    except ValueError:
        return None
    match = ISSUE_PATH.fullmatch(url.path)
    if url.scheme != "https" or url.netloc.lower() != "github.com" or not match:
        return None
    owner, repo, number = match.groups()
    if repo in {".", ".."}:
        return None
    return f"https://github.com/{owner.lower()}/{repo.lower()}/issues/{number}"


def _epic_lines(rich_text: list[dict]) -> Iterator[tuple[str, set[str]]]:
    text = ""
    links: set[str] = set()
    for item in rich_text:
        href = item.get("href")
        for index, part in enumerate(item["plain_text"].split("\n")):
            if index:
                yield text, links
                text, links = "", set()
            text += part
            if href and part.strip():
                links.add(href)
    yield text, links


def _parse_epics(rich_text: list[dict]) -> tuple[list[str], list[str]]:
    epics: dict[str, None] = {}
    problems = []
    for number, (text, links) in enumerate(_epic_lines(rich_text), start=1):
        if not text.strip():
            continue
        if len(links) > 1:
            problems.append(f"line {number} contains multiple links. Use one per line.")
            continue
        url = _issue_url(next(iter(links), text.strip()))
        if url:
            epics[url] = None
        else:
            problems.append(f"line {number} is not a GitHub issue link.")
    if not epics and not problems:
        problems.append("add at least one epic issue link.")
    return list(epics), problems


def _query_projects(session: Session, source_id: str) -> Iterator[dict]:
    url = f"https://api.notion.com/v1/data_sources/{UUID(source_id)}/query"
    body = {
        "page_size": 100,
        "result_type": "page",
        "filter": {
            "and": [
                {"property": "Type", "select": {"equals": "Release milestone"}},
                {"property": "Workstream", "select": {"equals": "Product"}},
            ]
        },
    }
    cursors = set()
    while True:
        for attempt in range(3):
            response = session.post(
                url,
                json=body,
                headers={"Notion-Version": "2026-03-11"},
                timeout=30,
            )
            if response.status_code not in {429, 529} or attempt == 2:
                break
            retry_after = response.headers.get("Retry-After", "")
            delay = int(retry_after) if retry_after.isdecimal() else 2**attempt
            if delay > 60:
                break
            time.sleep(delay)

        if response.status_code in {401, 403, 404}:
            raise HTTPError(
                f"Notion returned HTTP {response.status_code}. Check the integration "
                "token, its access to the source database, and the data source ID.",
                response=response,
            )
        response.raise_for_status()
        result = response.json()
        if (result.get("request_status") or {}).get("type") == "incomplete":
            raise RuntimeError("Notion returned an incomplete project query.")
        yield from result["results"]
        if not result["has_more"]:
            return
        cursor = result["next_cursor"]
        if not cursor or cursor in cursors:
            raise RuntimeError("Notion returned an invalid project pagination cursor.")
        cursors.add(cursor)
        body["start_cursor"] = cursor


def fetch_projects(
    notion_session: Session, data_source_id: str = DEFAULT_NOTION_DATA_SOURCE_ID
) -> tuple[list[Project], list[str]]:
    """Return active Product release milestones and diagnostics for their epic links."""
    projects: list[Project] = []
    diagnostics: list[str] = []
    for page in _query_projects(notion_session, data_source_id):
        if page.get("in_trash") or page.get("is_archived"):
            continue
        properties = page["properties"]
        stage = (properties["Delivery stage"]["select"] or {}).get("name")
        if stage in COMPLETED_STAGES:
            continue
        title = "".join(part["plain_text"] for part in properties["Name"]["title"])
        title = title.strip() or "Untitled release milestone"
        epics_property = properties.get(EPICS_PROPERTY, {})
        if epics_property.get("type") != "rich_text":
            raise RuntimeError(
                f'Notion requires a Text property named "{EPICS_PROPERTY}".'
            )
        epic_urls, problems = _parse_epics(epics_property["rich_text"])
        diagnostics.extend(
            f"{title} ({page['url']}) · {EPICS_PROPERTY}: {p}" for p in problems
        )
        projects.append(
            {
                "title": title,
                "workstream": properties["Workstream"]["select"]["name"],
                "url": page["url"],
                "epic_urls": epic_urls,
            }
        )
    return projects, diagnostics
