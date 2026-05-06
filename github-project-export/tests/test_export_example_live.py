"""
Live GitHub API integration test using tests/fixtures/fixture_1_input.json.

Requires GITHUB_TOKEN (e.g. ``GITHUB_TOKEN=$(gh auth token) uv run pytest``).
No mocks — asserts TSV matches fixture_1_output.tsv, with rows sorted by ``url``
so order matches the API response regardless of pagination ordering.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
_FIXTURES = Path(__file__).resolve().parent / "fixtures"
_FIXTURE_INPUT = _FIXTURES / "fixture_1_input.json"
_FIXTURE_OUTPUT = _FIXTURES / "fixture_1_output.tsv"
_FIXTURE_2_INPUT = _FIXTURES / "fixture_2_input.json"
_FIXTURE_2_OUTPUT = _FIXTURES / "fixture_2_output.tsv"


def _subprocess_env() -> dict[str, str]:
    """Same token resolution as typical CI/local: ``GITHUB_TOKEN``, else ``GH_TOKEN``."""
    env = os.environ.copy()
    if not env.get("GITHUB_TOKEN") and env.get("GH_TOKEN"):
        env["GITHUB_TOKEN"] = env["GH_TOKEN"]
    return env


def _needs_github_token() -> bool:
    return not _subprocess_env().get("GITHUB_TOKEN")


def _normalize_tsv(tsv: str) -> str:
    """Header plus data rows sorted by the ``url`` column for stable comparison."""
    lines = [ln for ln in tsv.strip().splitlines() if ln.strip()]
    if not lines:
        return ""
    header, *rows = lines
    cols = header.split("\t")
    try:
        url_idx = cols.index("url")
    except ValueError as e:
        raise AssertionError("TSV header must include a url column") from e

    def row_key(line: str) -> str:
        parts = line.split("\t")
        if len(parts) > url_idx:
            return parts[url_idx]
        return line

    sorted_rows = sorted(rows, key=row_key)
    if not sorted_rows:
        return header + "\n"
    return header + "\n" + "\n".join(sorted_rows) + "\n"


@pytest.mark.integration
@pytest.mark.skipif(
    _needs_github_token(),
    reason="GITHUB_TOKEN not set (or GH_TOKEN); e.g. GITHUB_TOKEN=$(gh auth token) uv run pytest",
)
def test_export_example_matches_golden() -> None:
    expected_raw = _FIXTURE_OUTPUT.read_text(encoding="utf-8")
    expected = _normalize_tsv(expected_raw)

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "github_project_export.cli",
            str(_FIXTURE_INPUT),
            "--quiet",
        ],
        cwd=_PACKAGE_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=_subprocess_env(),
        check=False,
    )

    assert proc.returncode == 0, (
        f"CLI failed (exit {proc.returncode})\nstderr:\n{proc.stderr}\nstdout:\n{proc.stdout}"
    )
    actual = _normalize_tsv(proc.stdout)
    assert actual == expected, (
        f"TSV mismatch (normalized by url column).\n"
        f"--- expected ---\n{expected}\n--- actual ---\n{actual}\n--- stderr ---\n{proc.stderr}"
    )


@pytest.mark.integration
@pytest.mark.skipif(
    _needs_github_token(),
    reason="GITHUB_TOKEN not set (or GH_TOKEN); e.g. GITHUB_TOKEN=$(gh auth token) uv run pytest",
)
def test_export_or_query_matches_golden() -> None:
    """OR-query fixture: two milestones unioned, deduplicated, sorted by url."""
    expected_raw = _FIXTURE_2_OUTPUT.read_text(encoding="utf-8")
    expected = _normalize_tsv(expected_raw)

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "github_project_export.cli",
            str(_FIXTURE_2_INPUT),
            "--quiet",
        ],
        cwd=_PACKAGE_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=_subprocess_env(),
        check=False,
    )

    assert proc.returncode == 0, (
        f"CLI failed (exit {proc.returncode})\nstderr:\n{proc.stderr}\nstdout:\n{proc.stdout}"
    )
    actual = _normalize_tsv(proc.stdout)
    assert actual == expected, (
        f"TSV mismatch (normalized by url column).\n"
        f"--- expected ---\n{expected}\n--- actual ---\n{actual}\n--- stderr ---\n{proc.stderr}"
    )
