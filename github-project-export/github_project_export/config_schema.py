"""Load and validate JSON export configuration (structure only; field names validated after board fetch)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional

from github_project_export.board_url import parse_org_project_url


class ConfigError(Exception):
    """Invalid configuration (exit code 1)."""


@dataclass(frozen=True)
class ExportConfig:
    org: str
    project_number: int
    query: str
    fields: List[str]
    """Column headers exactly as the user configured (TSV header row)."""
    output_path: Optional[str]
    """None → stdout; non-empty string → file path."""


def _require_non_empty_query(data: dict[str, Any]) -> str:
    q = data.get("query")
    qp = data.get("queryParts")

    if q is not None and not isinstance(q, str):
        raise ConfigError("'query' must be a string when present")
    if qp is not None:
        if not isinstance(qp, list):
            raise ConfigError("'queryParts' must be an array when present")
        for i, part in enumerate(qp):
            if not isinstance(part, str):
                raise ConfigError(
                    f"queryParts[{i}] must be a string, not {type(part).__name__}",
                )

    q_chars = q.strip() if isinstance(q, str) else ""

    if q_chars:
        return q_chars

    if qp is not None and len(qp) > 0:
        joined = " ".join(p.strip() for p in qp)
        if not joined.strip():
            raise ConfigError(
                "'query' is empty and 'queryParts' produces an empty filter",
            )
        return joined

    raise ConfigError(
        "Provide a non-empty 'query' or a non-empty 'queryParts' array",
    )


def _parse_output_file(data: dict[str, Any]) -> Optional[str]:
    if "outputFile" not in data:
        return None
    of = data["outputFile"]
    if of is None:
        return None
    if not isinstance(of, str):
        raise ConfigError("'outputFile' must be a string or null")
    if of == "":
        raise ConfigError("'outputFile' must not be an empty string")
    return of


def _parse_fields(data: dict[str, Any]) -> List[str]:
    fields = data.get("fields")
    if not isinstance(fields, list) or len(fields) == 0:
        raise ConfigError("'fields' must be a non-empty array of strings")
    out: List[str] = []
    seen: set[str] = set()
    for i, f in enumerate(fields):
        if not isinstance(f, str):
            raise ConfigError(f"fields[{i}] must be a string")
        fold = f.strip().casefold()
        if fold in seen:
            raise ConfigError(f"Duplicate field (case-insensitive): {f!r}")
        seen.add(fold)
        out.append(f)
    return out


def load_export_config(path: Path) -> ExportConfig:
    """Read JSON from path and validate structure (FR-001, FR-002a, FR-005)."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as e:
        raise ConfigError(f"Cannot read config file: {e}") from e

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ConfigError(f"Invalid JSON: {e}") from e

    if not isinstance(data, dict):
        raise ConfigError("Configuration root must be a JSON object")

    url = data.get("projectUrl")
    if not isinstance(url, str) or not url.strip():
        raise ConfigError("'projectUrl' must be a non-empty string")

    try:
        org, project_number = parse_org_project_url(url.strip())
    except ValueError as e:
        raise ConfigError(str(e)) from e
    query = _require_non_empty_query(data)
    fields = _parse_fields(data)
    output_path = _parse_output_file(data)

    return ExportConfig(
        org=org,
        project_number=project_number,
        query=query,
        fields=fields,
        output_path=output_path,
    )
