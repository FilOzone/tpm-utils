"""Unit tests for output format helpers (_format_json, _format_compact).

These are pure-logic tests — no network access or GITHUB_TOKEN required.

Run:
    cd filozzy-mcp
    uv run pytest tests/test_format.py -v
"""

from __future__ import annotations

import json

from filozzy_mcp.server import _format_json, _format_compact


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

SAMPLE_ITEMS = [
    {
        "Repository": "curio",
        "Title": "Fix X",
        "Status": "⌨️ In Progress",
        "Node ID": "PVTI_abc",
        "Assignees": "alice",
    },
    {
        "Repository": "dealbot",
        "Title": "Add Y",
        "Status": "📌 Triage",
        # Node ID and Assignees intentionally missing (sparse row)
    },
    {
        "Repository": "curio",
        "Title": "Refactor Z",
        "Status": "👀 Awaiting review",
        "Node ID": "PVTI_xyz",
        "Assignees": "bob, carol",
    },
]


def _parse(result: str) -> dict:
    return json.loads(result)


# ---------------------------------------------------------------------------
# _format_json
# ---------------------------------------------------------------------------


class TestFormatJson:
    def test_basic_structure(self):
        out = _parse(_format_json(SAMPLE_ITEMS, has_more=False, next_cursor=None))
        assert out["total_in_page"] == 3
        assert len(out["items"]) == 3
        assert "has_more" not in out
        assert "next_cursor" not in out

    def test_items_are_original_dicts(self):
        out = _parse(_format_json(SAMPLE_ITEMS, has_more=False, next_cursor=None))
        assert out["items"][0]["Repository"] == "curio"
        assert out["items"][1]["Title"] == "Add Y"

    def test_pagination_fields(self):
        out = _parse(_format_json(SAMPLE_ITEMS, has_more=True, next_cursor="cur_42"))
        assert out["has_more"] is True
        assert out["next_cursor"] == "cur_42"

    def test_empty_items(self):
        out = _parse(_format_json([], has_more=False, next_cursor=None))
        assert out["items"] == []
        assert out["total_in_page"] == 0


# ---------------------------------------------------------------------------
# _format_compact
# ---------------------------------------------------------------------------


class TestFormatCompact:
    def test_columns_are_union_of_all_keys(self):
        out = _parse(_format_compact(SAMPLE_ITEMS, has_more=False, next_cursor=None))
        assert set(out["columns"]) == {
            "Repository", "Title", "Status", "Node ID", "Assignees",
        }

    def test_column_order_follows_first_seen(self):
        out = _parse(_format_compact(SAMPLE_ITEMS, has_more=False, next_cursor=None))
        # First item's keys define the initial order
        cols = out["columns"]
        assert cols.index("Repository") < cols.index("Title")
        assert cols.index("Title") < cols.index("Status")

    def test_row_count_matches_items(self):
        out = _parse(_format_compact(SAMPLE_ITEMS, has_more=False, next_cursor=None))
        assert len(out["rows"]) == 3
        assert out["total_in_page"] == 3

    def test_row_values_match_items(self):
        out = _parse(_format_compact(SAMPLE_ITEMS, has_more=False, next_cursor=None))
        cols = out["columns"]
        first_row = dict(zip(cols, out["rows"][0]))
        assert first_row["Repository"] == "curio"
        assert first_row["Title"] == "Fix X"
        assert first_row["Node ID"] == "PVTI_abc"

    def test_sparse_rows_get_empty_string(self):
        """Items missing a column that other items have should get ''."""
        out = _parse(_format_compact(SAMPLE_ITEMS, has_more=False, next_cursor=None))
        cols = out["columns"]
        second_row = dict(zip(cols, out["rows"][1]))
        assert second_row["Node ID"] == ""
        assert second_row["Assignees"] == ""

    def test_pagination_fields(self):
        out = _parse(
            _format_compact(SAMPLE_ITEMS, has_more=True, next_cursor="cur_99")
        )
        assert out["has_more"] is True
        assert out["next_cursor"] == "cur_99"

    def test_no_pagination_fields_when_not_needed(self):
        out = _parse(_format_compact(SAMPLE_ITEMS, has_more=False, next_cursor=None))
        assert "has_more" not in out
        assert "next_cursor" not in out

    def test_empty_items(self):
        out = _parse(_format_compact([], has_more=False, next_cursor=None))
        assert out["columns"] == []
        assert out["rows"] == []
        assert out["total_in_page"] == 0

    def test_roundtrip_via_jq_reconstruction(self):
        """Verify the documented jq reconstruction produces the original items."""
        out = _parse(_format_compact(SAMPLE_ITEMS, has_more=False, next_cursor=None))
        cols = out["columns"]
        # Simulate: jq '[.columns as $c | .rows[] | [$c, .] | transpose | map({(.[0]): .[1]}) | add]'
        reconstructed = [
            {col: val for col, val in zip(cols, row)}
            for row in out["rows"]
        ]
        # First and third items should match exactly
        assert reconstructed[0] == SAMPLE_ITEMS[0]
        assert reconstructed[2] == SAMPLE_ITEMS[2]
        # Second item had missing fields — reconstruction has "" instead
        for key in SAMPLE_ITEMS[1]:
            assert reconstructed[1][key] == SAMPLE_ITEMS[1][key]

    def test_compact_is_smaller_than_json(self):
        """The whole point: compact should use fewer bytes than json."""
        json_out = _format_json(SAMPLE_ITEMS, has_more=False, next_cursor=None)
        compact_out = _format_compact(SAMPLE_ITEMS, has_more=False, next_cursor=None)
        assert len(compact_out) < len(json_out), (
            f"compact ({len(compact_out)}) should be smaller than json ({len(json_out)})"
        )

    def test_unicode_preserved(self):
        """Emoji status values should survive the round-trip."""
        out = _parse(_format_compact(SAMPLE_ITEMS, has_more=False, next_cursor=None))
        cols = out["columns"]
        first_row = dict(zip(cols, out["rows"][0]))
        assert first_row["Status"] == "⌨️ In Progress"
