"""Tests for OR syntax validation at config load time (T012)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from github_project_export.config_schema import ConfigError, load_export_config


def _write_config(tmp_path: Path, query: str) -> Path:
    config = {
        "projectUrl": "https://github.com/orgs/FilOzone/projects/14",
        "query": query,
        "fields": ["Title"],
    }
    p = tmp_path / "config.json"
    p.write_text(json.dumps(config), encoding="utf-8")
    return p


class TestOrSyntaxConfigValidation:
    """Verify malformed OR queries raise ConfigError at config load time."""

    def test_unmatched_open_paren(self, tmp_path: Path):
        p = _write_config(tmp_path, "(a b")
        with pytest.raises(ConfigError, match="Unmatched opening parenthesis"):
            load_export_config(p)

    def test_or_without_parens(self, tmp_path: Path):
        p = _write_config(tmp_path, "a OR b")
        with pytest.raises(ConfigError, match="OR requires parenthesized groups"):
            load_export_config(p)

    def test_nested_parens(self, tmp_path: Path):
        p = _write_config(tmp_path, "((a)) OR (b)")
        with pytest.raises(ConfigError, match="Nested parentheses"):
            load_export_config(p)

    def test_empty_group(self, tmp_path: Path):
        p = _write_config(tmp_path, "(a) OR ()")
        with pytest.raises(ConfigError, match="Empty group"):
            load_export_config(p)

    def test_trailing_terms(self, tmp_path: Path):
        p = _write_config(tmp_path, "(a) OR (b) extra")
        with pytest.raises(ConfigError, match="Filter terms after the last group"):
            load_export_config(p)

    def test_valid_or_query_loads_ok(self, tmp_path: Path):
        p = _write_config(tmp_path, "is:issue (status:A) OR (status:B)")
        config = load_export_config(p)
        assert config.query == "is:issue (status:A) OR (status:B)"

    def test_valid_plain_query_loads_ok(self, tmp_path: Path):
        p = _write_config(tmp_path, "is:issue")
        config = load_export_config(p)
        assert config.query == "is:issue"

    def test_query_parts_or_validation(self, tmp_path: Path):
        config = {
            "projectUrl": "https://github.com/orgs/FilOzone/projects/14",
            "queryParts": ["is:issue", "(a OR b)"],
            "fields": ["Title"],
        }
        p = tmp_path / "config.json"
        p.write_text(json.dumps(config), encoding="utf-8")
        with pytest.raises(ConfigError, match="OR inside parentheses"):
            load_export_config(p)
