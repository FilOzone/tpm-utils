"""Unit tests for the mutation log: the item -> mutations multimap and its
TSV (de)serialization."""

from __future__ import annotations

from foc_mechanical_rules.mutation_log import (
    MutationLog,
    MutationRecord,
    read_tsv,
    write_tsv,
)


def _record(item="FilOzone/dealbot#458", **overrides):
    defaults = dict(
        timestamp="2026-08-21T00:00:00+00:00",
        rule="R-FC-012",
        item=item,
        field="cycle",
        old_value="",
        new_value="202608-2",
    )
    defaults.update(overrides)
    return MutationRecord(**defaults)


def test_for_item_returns_only_that_items_mutations():
    log = MutationLog([_record(item="a#1"), _record(item="b#2"), _record(item="a#1")])

    assert log.for_item("a#1") == [_record(item="a#1"), _record(item="a#1")]
    assert log.for_item("b#2") == [_record(item="b#2")]


def test_for_item_returns_empty_list_for_unknown_item():
    log = MutationLog()
    assert log.for_item("nobody#1") == []


def test_record_appends_and_is_visible_via_for_item():
    log = MutationLog()
    log.record(_record(item="a#1"))
    log.record(_record(item="a#1", new_value="202608-3"))

    results = log.for_item("a#1")
    assert len(results) == 2
    assert [r.new_value for r in results] == ["202608-2", "202608-3"]


def test_all_returns_every_record_across_items():
    log = MutationLog([_record(item="a#1"), _record(item="b#2")])
    assert len(log.all()) == 2


def test_tsv_round_trip(tmp_path):
    path = tmp_path / "mutations.tsv"
    records = [_record(item="a#1"), _record(item="b#2", new_value="202608-3")]

    write_tsv(path, records)
    loaded = read_tsv(path)

    assert loaded == records


def test_read_tsv_missing_file_returns_empty():
    from pathlib import Path

    assert read_tsv(Path("/nonexistent/mutations.tsv")) == []
