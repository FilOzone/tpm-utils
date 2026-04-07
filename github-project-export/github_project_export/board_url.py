"""Parse GitHub organization project URLs."""

from __future__ import annotations

import re
from typing import Tuple


_ORG_PROJECT_RE = re.compile(
    r"^https://github\.com/orgs/(?P<org>[^/]+)/projects/(?P<num>[0-9]+)/?(?:\?.*)?$",
    re.IGNORECASE,
)


def parse_org_project_url(project_url: str) -> Tuple[str, int]:
    """
    Parse ``https://github.com/orgs/{org}/projects/{n}`` into (org_login, project_number).

    Raises:
        ValueError: if the URL does not match the expected organization-project pattern.
    """
    raw = (project_url or "").strip()
    m = _ORG_PROJECT_RE.match(raw.split("#", 1)[0].strip())
    if not m:
        raise ValueError(
            "projectUrl must look like "
            "https://github.com/orgs/ORG_LOGIN/projects/N "
            f"(got: {project_url!r})",
        )
    org = m.group("org")
    num = int(m.group("num"))
    return org, num
