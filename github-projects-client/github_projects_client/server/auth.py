"""Bearer token extraction and validation as a FastAPI dependency."""

from __future__ import annotations

import requests as req
from fastapi import Depends, HTTPException
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


def get_validated_token(
    token: str = Depends(get_token),
) -> str:
    """Extract and validate bearer token against the GitHub API.

    Calls GET /user to confirm the token is real. Raises 401 if
    GitHub rejects it.
    """
    try:
        resp = req.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
    except req.RequestException:
        raise HTTPException(
            status_code=502, detail="Unable to reach GitHub API for token validation"
        )
    if not resp.ok:
        raise HTTPException(status_code=401, detail="Invalid or expired bearer token")
    return token


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
