"""FastAPI application for GitHub Projects v2 REST API."""

from __future__ import annotations

import os

import requests
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from github_projects_client.api import (
    GitHubAPIError,
    GitHubAuthError,
    GitHubRateLimitError,
    is_rate_limited,
)

from .routes import items, fields, mutations


def _rate_limited_response(response: requests.Response | None) -> JSONResponse:
    headers = response.headers if response is not None else {}
    retry_after = headers.get("Retry-After")
    return JSONResponse(
        status_code=429,
        content={
            "error": "rate_limited",
            "message": "GitHub API rate limit exceeded",
            "details": {
                "retry_after": int(retry_after) if retry_after else None,
                "limit": headers.get("X-RateLimit-Limit"),
                "remaining": 0,
                "reset_at": headers.get("X-RateLimit-Reset"),
            },
        },
    )


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="GitHub Projects API",
        description="REST API for GitHub Projects v2 board operations",
        version="0.1.0",
    )

    # --- Error handlers ---

    @app.exception_handler(HTTPException)
    async def http_exception_handler(
        request: Request, exc: HTTPException
    ) -> JSONResponse:
        """Map FastAPI HTTPExceptions to consistent error JSON."""
        if isinstance(exc.detail, dict):
            return JSONResponse(status_code=exc.status_code, content=exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": "http_error",
                "message": str(exc.detail),
                "details": {},
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Map validation errors to consistent error JSON."""
        return JSONResponse(
            status_code=422,
            content={
                "error": "validation_error",
                "message": "Request validation failed",
                "details": {"errors": exc.errors()},
            },
        )

    @app.exception_handler(requests.HTTPError)
    async def github_http_error_handler(
        request: Request, exc: requests.HTTPError
    ) -> JSONResponse:
        """Map GitHub API HTTP errors to consistent error JSON."""
        response = exc.response
        status = response.status_code if response is not None else 502

        if status == 401:
            return JSONResponse(
                status_code=401,
                content={
                    "error": "unauthorized",
                    "message": "GitHub API authentication failed — check your bearer token",
                    "details": {},
                },
            )

        if status == 404:
            return JSONResponse(
                status_code=404,
                content={
                    "error": "not_found",
                    "message": "Resource not found on GitHub",
                    "details": {},
                },
            )

        if response is not None and is_rate_limited(response):
            return _rate_limited_response(response)

        return JSONResponse(
            status_code=status,
            content={
                "error": "github_api_error",
                "message": str(exc),
                "details": {},
            },
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
        """Map ValueErrors (e.g., invalid query syntax) to 422."""
        return JSONResponse(
            status_code=422,
            content={
                "error": "invalid_request",
                "message": str(exc),
                "details": {},
            },
        )

    @app.exception_handler(GitHubAuthError)
    async def github_auth_error_handler(
        request: Request, exc: GitHubAuthError
    ) -> JSONResponse:
        """Map GitHub auth/scope errors to 401 with actionable message."""
        return JSONResponse(
            status_code=401,
            content={
                "error": "unauthorized",
                "message": str(exc),
                "details": {},
            },
        )

    # Needs its own handler: as a GitHubAPIError subclass listed before
    # requests.HTTPError in its MRO, it would otherwise get the 502 below.
    @app.exception_handler(GitHubRateLimitError)
    async def github_rate_limit_handler(
        request: Request, exc: GitHubRateLimitError
    ) -> JSONResponse:
        return _rate_limited_response(exc.response)

    @app.exception_handler(GitHubAPIError)
    async def github_api_error_handler(
        request: Request, exc: GitHubAPIError
    ) -> JSONResponse:
        """Map GitHub API errors to 502 with the original message preserved."""
        return JSONResponse(
            status_code=502,
            content={
                "error": "github_api_error",
                "message": str(exc),
                "details": {},
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        """Catch-all for unhandled exceptions."""
        import logging

        logging.exception("Unhandled exception in %s %s", request.method, request.url)
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_error",
                "message": "Internal server error",
                "details": {},
            },
        )

    # --- Route registration ---
    app.include_router(items.router)
    app.include_router(mutations.router)
    app.include_router(fields.router)

    return app


app = create_app()


def main() -> None:
    """Entry point for the github-projects-api CLI command."""
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run(app, host=host, port=port)


def main_dev() -> None:
    """Entry point for the github-projects-api-dev CLI command (auto-reload)."""
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run(
        "github_projects_client.server.app:app",
        host=host,
        port=port,
        reload=True,
    )


if __name__ == "__main__":
    main()
