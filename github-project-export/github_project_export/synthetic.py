"""Synthetic column values derived from linked issue/PR ``content`` (not board fields)."""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

# Header alias (lowercase) -> internal synthetic key used by ``synthetic_cell_value``
_SYNTHETIC_KEYS: dict[str, str] = {
    "repository": "repository",
    "repo": "repository",
    "url": "url",
    "link": "url",
    "html_url": "url",
    "kind": "type",
    "id": "id",
    "number": "id",
    "title": "title",
}


def documented_synthetic_headers() -> list[str]:
    """Stable list for error messages / README (unique display-ish names)."""
    return ["Repository", "url", "Type", "Kind", "Id", "title"]


def normalize_synthetic_key(header: str) -> Optional[str]:
    """
    If ``header`` matches a documented synthetic column, return internal key
    (repository, url, type, id, title). Otherwise return None.

    Matching is case-insensitive; ``Type`` and ``Id`` are accepted as headers.
    """
    key = header.strip().lower()
    if key == "type":
        return "type"
    if key == "id":
        return "id"
    return _SYNTHETIC_KEYS.get(key)


def _repo_from_html_url(html_url: str) -> str:
    if not html_url:
        return ""
    m = re.match(
        r"^https://github\.com/([^/]+/[^/]+)/(?:pull|issues)/[0-9]+",
        html_url.strip(),
    )
    return m.group(1) if m else ""


def synthetic_cell_value(internal_key: str, content: Optional[Dict[str, Any]]) -> str:
    """Return string cell for a synthetic column from REST ``content`` (or empty)."""
    if not content or not isinstance(content, dict):
        return ""

    if internal_key == "repository":
        repo = content.get("repository")
        if isinstance(repo, dict):
            nwo = repo.get("full_name")
            if isinstance(nwo, str) and nwo:
                return nwo
        return _repo_from_html_url(str(content.get("html_url") or ""))

    if internal_key == "url":
        u = content.get("html_url")
        return str(u) if isinstance(u, str) else ""

    if internal_key == "type":
        t = content.get("type")
        if isinstance(t, str) and t:
            return t.lower().replace(" ", "_")
        api_url = str(content.get("url") or "")
        if "/pulls/" in api_url:
            return "pull_request"
        if "/issues/" in api_url:
            return "issue"
        return ""

    if internal_key == "id":
        n = content.get("number")
        if n is not None:
            return str(n)
        return ""

    if internal_key == "title":
        t = content.get("title")
        return str(t) if isinstance(t, str) else ""

    return ""
