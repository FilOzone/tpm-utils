"""Unit tests for the persisted TSV mutation log."""

from __future__ import annotations

from foc_mechanical_rules.state import MutationRecord, append_mutation, load_mutations


def test_append_and_load_round_trip(tmp_path):
    path = tmp_path / "mutations.tsv"
    record = MutationRecord(
        timestamp="2026-08-21T00:00:00+00:00",
        rule="R-FC-012",
        item="FilOzone/dealbot#458",
        field="cycle",
        old_value="",
        new_value="202608-2",
    )

    append_mutation(record, path=path)
    loaded = load_mutations(path=path)

    assert loaded == [record]


def test_multiple_appends_accumulate(tmp_path):
    path = tmp_path / "mutations.tsv"
    for i in range(3):
        append_mutation(
            MutationRecord(
                timestamp=f"2026-08-2{i}T00:00:00+00:00",
                rule="R-PR-001",
                item=f"FilOzone/dealbot#{i}",
                field="assignee",
                old_value="",
                new_value="alice",
            ),
            path=path,
        )

    loaded = load_mutations(path=path)
    assert len(loaded) == 3
    assert [r.item for r in loaded] == [
        "FilOzone/dealbot#0",
        "FilOzone/dealbot#1",
        "FilOzone/dealbot#2",
    ]


def test_load_mutations_missing_file_returns_empty(tmp_path):
    assert load_mutations(path=tmp_path / "does-not-exist.tsv") == []
