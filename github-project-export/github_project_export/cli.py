#!/usr/bin/env python3
"""CLI: JSON config → GitHub Project v2 items → TSV."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import requests

from github_project_export.config_schema import ConfigError, load_export_config
from github_project_export.rest_export import FieldResolutionError, export_rows
from github_project_export.tsv_write import write_tsv


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Export GitHub Organization Project v2 items to TSV using a JSON configuration file. "
            "Board URL, filter, fields, and output path are read only from the config (not CLI flags)."
        ),
    )
    parser.add_argument(
        "config",
        type=Path,
        help="Path to JSON configuration file",
    )
    parser.add_argument(
        "--token",
        help="GitHub token (default: GITHUB_TOKEN environment variable)",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Less progress output on stderr",
    )
    args = parser.parse_args()

    token = args.token or os.environ.get("GITHUB_TOKEN")
    if not token:
        print("Error: set GITHUB_TOKEN or pass --token", file=sys.stderr)
        sys.exit(1)

    try:
        cfg = load_export_config(args.config)
    except ConfigError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(1)

    session = requests.Session()
    session.headers.update(
        {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
    )

    try:
        rows = export_rows(
            session,
            cfg.org,
            cfg.project_number,
            cfg.query,
            cfg.fields,
            verbose=not args.quiet,
        )
    except FieldResolutionError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(1)
    except requests.HTTPError as e:
        resp = e.response
        detail = ""
        if resp is not None:
            try:
                body = resp.json()
                if isinstance(body, dict) and "message" in body:
                    detail = f": {body['message']}"
            except Exception:  # noqa: S110
                detail = f": {resp.text[:500]}"
        print(
            f"GitHub API error ({resp.status_code if resp else 'n/a'}){detail}",
            file=sys.stderr,
        )
        sys.exit(2)
    except Exception as e:  # noqa: BLE001 — surface client errors as API-class
        # foc_project14_client raises Exception for GraphQL/scope errors; normalize to stderr + exit 2
        msg = str(e)
        print(f"GitHub error: {msg}", file=sys.stderr)
        if "INSUFFICIENT_SCOPES" in msg or "read:project" in msg:
            sys.exit(2)
        sys.exit(2)

    out_stream = sys.stdout
    out_path: Path | None = None
    if cfg.output_path:
        out_path = Path(cfg.output_path)

    try:
        if out_path is not None:
            # Write file as UTF-8; do not leak file content to stdout on success
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with out_path.open("w", encoding="utf-8", newline="") as fh:
                write_tsv(list(cfg.fields), rows, fh)
            if not args.quiet:
                print(f"Wrote {cfg.output_path}", file=sys.stderr)
        else:
            # stdout: TSV only
            write_tsv(list(cfg.fields), rows, out_stream)
    except OSError as e:
        print(f"Output error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
