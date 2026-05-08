"""Bearer token extraction as a FastAPI dependency."""

from __future__ import annotations

import requests as req
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer_scheme = HTTPBearer()


def get_token(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> str:
    """Extract bearer token from Authorization header.

    Uses FastAPI's HTTPBearer scheme so Swagger UI shows a proper
    "Authorize" button instead of a raw header text field.

    Returns the raw token string for use with the GitHub API.
    """
    return credentials.credentials


def build_session(token: str) -> req.Session:
    """Build a requests.Session authenticated with the given token."""
    session = req.Session()
    session.headers.update(
        {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
    )
    return session
