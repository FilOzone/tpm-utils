"""Offline tests for upgrade_doc.py.

The doc is simulated: `FakeDoc` builds Docs-API-shaped JSON from a list of paragraphs, computing indices in
UTF-16 code units like the real API, and applies the script's edit ops to that text. This checks that edits land
exactly where intended, including after emoji (2 code units each).
"""

from __future__ import annotations

import argparse

import pytest

import upgrade_doc as ud

TAB = "t.test"

# (style, text, bullet nesting level or None)
DOC = [
    ("HEADING_1", "🔥 nvXX Burndown list", None),
    ("HEADING_2", "🟡 Before Mainnet Tasks", None),
    ("HEADING_3", "🥞 Lotus stable release · owner: FilOz", None),
    ("NORMAL_TEXT", "Description:", 0),
    ("NORMAL_TEXT", "❗Complete 2 weeks before the upgrade", 1),
    ("NORMAL_TEXT", "Depends on: Release final filecoin-ffi", 0),
    ("NORMAL_TEXT", "Output: GitHub release: link", 0),
    ("NORMAL_TEXT", "Time:", 0),
    ("NORMAL_TEXT", "Calendar:", 1),
    ("NORMAL_TEXT", "Agent/Human:", 1),
    ("NORMAL_TEXT", "Emergency: ⏩Skip", 0),
    ("HEADING_3", "🥞 Release final filecoin-ffi · owner: FilOz", None),
    ("NORMAL_TEXT", "Output:", 0),
    ("NORMAL_TEXT", "PR: link", 1),
    ("NORMAL_TEXT", "GitHub release: link", 1),
    ("HEADING_2", "👉 Calibration Upgrade Day Tasks", None),
    (
        "HEADING_3",
        "🥞 Capture a power baseline before the upgrade · owner: FilOz · tester: unassigned",
        None,
    ),
    ("NORMAL_TEXT", "Output:", 0),
    ("HEADING_2", "🤘Mainnet Upgrade Day Tasks", None),
    (
        "HEADING_3",
        "🥞 Capture a power baseline before the upgrade · owner: FilOz · tester: unassigned",
        None,
    ),
    ("NORMAL_TEXT", "Output: ", 0),
    ("HEADING_1", "🧪 Test Plans", None),
]


class FakeDoc:
    """A doc held as paragraphs; edit ops are applied to its UTF-16 text and re-split into paragraphs."""

    def __init__(self, paras):
        self.paras = [list(p) for p in paras]
        self.revision = 0
        self.links: list[str] = []
        self.ops: list[tuple] = []

    def raw(self) -> dict:
        content, i = [], 1
        for n, (style, text, level) in enumerate(self.paras):
            end = i + ud.u16(text) + 1
            st = {"namedStyleType": style}
            if style.startswith("HEADING"):
                st["headingId"] = f"h.{n}"
            para = {
                "elements": [{"textRun": {"content": text + "\n"}}],
                "paragraphStyle": st,
            }
            if level is not None:
                para["bullet"] = {"nestingLevel": level}
            content.append({"startIndex": i, "endIndex": end, "paragraph": para})
            i = end
        return {"body": {"content": content}, "revisionId": str(self.revision)}

    def _flat(self) -> str:
        return "".join(t + "\n" for _, t, _ in self.paras)

    def apply(self, ops) -> None:
        # Index 1 is the first character, as in the Docs API.
        units = self._flat().encode("utf-16-le")
        for op in sorted(ops, key=lambda o: o[1], reverse=True):
            if op[0] == "replace":
                _, s, e, text = op
            else:
                _, s, text = op
                e = s
            units = (
                units[: (s - 1) * 2] + text.encode("utf-16-le") + units[(e - 1) * 2 :]
            )
        lines = units.decode("utf-16-le").split("\n")[:-1]
        # Re-pair text with styles. Inserting "\n" + text after a paragraph creates a new paragraph that
        # inherits the style of the paragraph it was split from, as in Google Docs.
        new, j = [], 0
        for line in lines:
            if j < len(self.paras) and (
                line == self.paras[j][1] or self._edited(line, j)
            ):
                new.append([self.paras[j][0], line, self.paras[j][2]])
                j += 1
            else:
                new.append([new[-1][0], line, new[-1][2]])
        self.paras = new
        self.revision += 1

    def _edited(self, line: str, j: int) -> bool:
        """Heuristic for tests: an edited paragraph keeps its first two characters (label or emoji)."""
        old = self.paras[j][1]
        return line[:2] == old[:2] or (
            old.split(":")[0] and line.startswith(old.split(":")[0] + ":")
        )

    def text(self) -> list[str]:
        return [t for _, t, _ in self.paras]


class FakeGog(ud.Gog):
    def __init__(self, doc: FakeDoc):
        super().__init__("doc", TAB, None)
        self.fake = doc

    def raw(self) -> dict:
        return self.fake.raw()

    def _check(self, revision: str) -> None:
        # Mirrors the real guard: edits computed from an older read must not apply.
        if revision != str(self.fake.revision):
            raise ud.RevisionChanged("doc changed since it was read")

    def submit(self, ops, revision) -> None:
        self._check(revision)
        self.fake.ops.append(ops)
        self.fake.apply(ops)

    def link_url(self, url, revision) -> None:
        self._check(revision)
        self.fake.links.append(url)


@pytest.fixture
def doc():
    return FakeDoc(DOC)


def args(**kw) -> argparse.Namespace:
    kw.setdefault("phase", None)
    return argparse.Namespace(**kw)


def para_text(doc: FakeDoc, start: int, end: int) -> str:
    units = doc._flat().encode("utf-16-le")
    return units[(start - 1) * 2 : (end - 1) * 2].decode("utf-16-le")


# ---------------------------------------------------------------- parsing


def test_u16_counts_emoji_as_two():
    assert ud.u16("🥞") == 2
    assert ud.u16("❗") == 1
    assert ud.u16("abc") == 3


def test_tasks_parses_heading_parts_and_phase(doc):
    ts = ud.tasks(doc.raw())
    assert [t.title for t in ts] == [
        "Lotus stable release",
        "Release final filecoin-ffi",
        "Capture a power baseline before the upgrade",
        "Capture a power baseline before the upgrade",
    ]
    lotus = ts[0]
    assert (lotus.status, lotus.owner, lotus.tester, lotus.phase) == (
        "🥞",
        "FilOz",
        None,
        "🟡 Before Mainnet Tasks",
    )
    assert ts[3].tester == "unassigned"
    assert ts[3].phase == "🤘Mainnet Upgrade Day Tasks"
    assert [p.text for p in lotus.body][0] == "Description:"
    assert len(lotus.body) == 8  # stops at the next heading


def test_find_task_prefers_exact_then_substring_and_reports_ambiguity(doc):
    ts = ud.tasks(doc.raw())
    assert ud.find_task(ts, "lotus stable", None).title == "Lotus stable release"
    with pytest.raises(ud.UsageError, match="matched 2 tasks"):
        ud.find_task(ts, "power baseline", None)
    assert (
        ud.find_task(ts, "power baseline", "Mainnet Upgrade Day").phase
        == "🤘Mainnet Upgrade Day Tasks"
    )
    with pytest.raises(ud.UsageError, match="matched 0 tasks"):
        ud.find_task(ts, "nope", None)


def test_find_field_finds_top_level_and_sub_fields(doc):
    lotus = ud.tasks(doc.raw())[0]
    p, kids = ud.find_field(lotus, "Description")
    assert p.text == "Description:" and [k.text for k in kids] == [
        "❗Complete 2 weeks before the upgrade"
    ]
    p, kids = ud.find_field(lotus, "calendar")
    assert p.text == "Calendar:" and kids == []
    with pytest.raises(ud.UsageError, match="no 'Why' line"):
        ud.find_field(lotus, "Why")


def test_value_range_covers_text_after_label(doc):
    lotus = ud.tasks(doc.raw())[0]
    p, _ = ud.find_field(lotus, "Output")
    s, e, old = ud.value_range(p)
    assert old == "GitHub release: link"
    assert para_text(doc, s, e) == "GitHub release: link"


# ---------------------------------------------------------------- commands


def test_status_replaces_emoji_only(doc):
    ud.cmd_status(FakeGog(doc), args(task="Lotus stable release", new_status="done"))
    assert "✅ Lotus stable release · owner: FilOz" in doc.text()


def test_status_accepts_emoji_and_keeps_later_headings_intact(doc):
    ud.cmd_status(FakeGog(doc), args(task="filecoin-ffi", new_status="🏃"))
    assert "🏃 Release final filecoin-ffi · owner: FilOz" in doc.text()
    assert "🥞 Lotus stable release · owner: FilOz" in doc.text()


def test_tester_replaces_only_the_named_phase(doc):
    ud.cmd_tester(
        FakeGog(doc),
        args(task="power baseline", phase="Mainnet Upgrade Day", name="Steve"),
    )
    headings = [t for t in doc.text() if t.startswith("🥞 Capture")]
    assert headings == [
        "🥞 Capture a power baseline before the upgrade · owner: FilOz · tester: unassigned",
        "🥞 Capture a power baseline before the upgrade · owner: FilOz · tester: Steve",
    ]


def test_tester_rejects_task_without_tester_slot(doc):
    with pytest.raises(ud.UsageError, match="no tester slot"):
        ud.cmd_tester(FakeGog(doc), args(task="Lotus stable release", name="Steve"))


def test_set_replaces_existing_value_and_links_urls(doc):
    url = "https://github.com/filecoin-project/lotus/releases/tag/v1.40.0"
    g = FakeGog(doc)
    ud.cmd_set(
        g,
        args(
            task="Lotus stable release", field="Output", text=f"GitHub release: {url}"
        ),
    )
    assert f"Output: GitHub release: {url}" in doc.text()
    assert doc.links == [url]


def test_url_that_appears_more_than_once_is_not_linked(doc, capsys):
    # The new URL is a prefix of one already in the doc, so a text match could link the wrong place.
    doc.paras[4][1] = "See https://github.com/filecoin-project/lotus/pull/12271"
    ud.cmd_append(
        FakeGog(doc),
        args(
            task="Lotus stable release",
            field="Output",
            text="PR: https://github.com/filecoin-project/lotus/pull/1",
        ),
    )
    assert doc.links == []
    assert "appears 2 times" in capsys.readouterr().err


def test_set_fills_empty_sub_field(doc):
    ud.cmd_set(
        FakeGog(doc), args(task="Lotus stable release", field="Calendar", text="3d")
    )
    ud.cmd_set(
        FakeGog(doc),
        args(task="Lotus stable release", field="Agent/Human", text="Steve: 1h"),
    )
    assert "Calendar: 3d" in doc.text() and "Agent/Human: Steve: 1h" in doc.text()


def test_set_on_label_with_trailing_space_does_not_double_space(doc):
    ud.cmd_set(
        FakeGog(doc),
        args(
            task="power baseline",
            phase="Mainnet Upgrade Day",
            field="Output",
            text="done",
        ),
    )
    assert "Output: done" in doc.text()


def test_append_adds_sub_bullet_when_field_has_them(doc):
    ud.cmd_append(
        FakeGog(doc),
        args(task="filecoin-ffi", field="Output", text="Backport PR: link"),
    )
    t = doc.text()
    i = t.index("GitHub release: link")
    assert t[i + 1] == "Backport PR: link"
    assert doc.paras[i + 1][2] == 1  # same nesting as its siblings


def test_append_to_inline_value_uses_separator(doc):
    ud.cmd_append(
        FakeGog(doc),
        args(task="Lotus stable release", field="Output", text="Notes: link"),
    )
    assert "Output: GitHub release: link; Notes: link" in doc.text()


def test_append_to_empty_value_just_sets_it(doc):
    ud.cmd_append(
        FakeGog(doc),
        args(
            task="power baseline",
            phase="Calibration",
            field="Output",
            text="baseline posted",
        ),
    )
    assert "Output: baseline posted" in doc.text()


def test_edit_after_read_forces_rebuild_instead_of_stale_indices(doc):
    class Conflicting(FakeGog):
        calls = 0

        def submit(self, ops, revision):
            Conflicting.calls += 1
            if Conflicting.calls == 1:
                # Someone inserts a paragraph above the task between our read and our batch.
                self.fake.paras.insert(1, ["NORMAL_TEXT", "🎉 new intro line", None])
                self.fake.revision += 1
            super().submit(ops, revision)

    ud.cmd_status(
        Conflicting(doc), args(task="Lotus stable release", new_status="done")
    )
    assert Conflicting.calls == 2
    assert len(doc.ops) == 1  # the stale first attempt never applied
    assert "✅ Lotus stable release · owner: FilOz" in doc.text()
    assert "🎉 new intro line" in doc.text()


def test_link_retries_when_doc_changes_after_read(doc):
    class Conflicting(FakeGog):
        calls = 0

        def link_url(self, url, revision):
            Conflicting.calls += 1
            if Conflicting.calls == 1:
                self.fake.revision += 1
            super().link_url(url, revision)

    url = "https://github.com/filecoin-project/lotus/releases/tag/v1.40.0"
    ud.cmd_set(
        Conflicting(doc),
        args(
            task="Lotus stable release", field="Output", text=f"GitHub release: {url}"
        ),
    )
    assert Conflicting.calls == 2 and doc.links == [url]


# ---------------------------------------------------------------- Gog revision pin


class RecordingGog(ud.Gog):
    """Gog with `run` stubbed: `batch show` reports the given pinned revision."""

    def __init__(self, pinned: str):
        super().__init__("doc", TAB, None)
        self.pinned = pinned
        self.calls: list[tuple] = []

    def run(self, *args, capture=True):
        self.calls.append(args)
        if args[:2] == ("batch", "begin"):
            return '{"batch_id": "b1"}'
        if args[:2] == ("batch", "show"):
            return '{"batch": {"required_revision_id": "%s"}}' % self.pinned
        return ""


def test_end_refuses_batch_pinned_to_a_newer_revision():
    g = RecordingGog(pinned="rev-2")
    with pytest.raises(ud.RevisionChanged):
        g.end("b1", "rev-1")
    assert ("batch", "end", "b1") not in g.calls


def test_end_submits_batch_pinned_to_the_read_revision():
    g = RecordingGog(pinned="rev-1")
    g.end("b1", "rev-1")
    assert ("batch", "end", "b1") in g.calls


# ---------------------------------------------------------------- show: links and code blocks


def run_(text, start, link=None):
    style = {"link": link} if link else {}
    return {"startIndex": start, "textRun": {"content": text, "textStyle": style}}


def rich_raw() -> dict:
    """A task whose Output has a hyperlinked label and whose Description has a native code block (a table)."""
    url = "https://github.com/filecoin-project/lotus/releases/tag/v1.40.0"
    return {
        "revisionId": "0",
        "body": {
            "content": [
                {
                    "startIndex": 1,
                    "endIndex": 40,
                    "paragraph": {
                        "elements": [
                            run_("🥞 Benchmark the migration · owner: FilOz\n", 1)
                        ],
                        "paragraphStyle": {
                            "namedStyleType": "HEADING_3",
                            "headingId": "h.b",
                        },
                    },
                },
                {
                    "startIndex": 40,
                    "endIndex": 53,
                    "paragraph": {
                        "elements": [run_("Description:\n", 40)],
                        "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                        "bullet": {"nestingLevel": 0},
                    },
                },
                {
                    "startIndex": 53,
                    "endIndex": 90,
                    "table": {
                        "tableRows": [
                            {
                                "tableCells": [
                                    {
                                        "content": [
                                            {
                                                "paragraph": {
                                                    "elements": [run_("## Tasks\n", 55)]
                                                }
                                            },
                                            {
                                                "paragraph": {
                                                    "elements": [
                                                        run_(
                                                            "Output: not a field\n", 64
                                                        )
                                                    ]
                                                }
                                            },
                                        ]
                                    }
                                ]
                            }
                        ]
                    },
                },
                {
                    "startIndex": 90,
                    "endIndex": 120,
                    "paragraph": {
                        "elements": [
                            run_("Output: ", 90),
                            run_("GitHub release", 98, {"url": url}),
                            run_(" and ", 112),
                            run_(
                                "deps", 117, {"heading": {"id": "h.d", "tabId": "t.x"}}
                            ),
                            run_("\n", 121),
                        ],
                        "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                        "bullet": {"nestingLevel": 0},
                    },
                },
            ]
        },
    }


class RawGog(ud.Gog):
    def __init__(self, raw):
        super().__init__("doc", TAB, None)
        self._raw = raw

    def raw(self):
        return self._raw


def test_show_includes_link_destinations_and_code_blocks(capsys):
    ud.cmd_show(RawGog(rich_raw()), args(task="Benchmark"))
    out = capsys.readouterr().out
    url = "https://github.com/filecoin-project/lotus/releases/tag/v1.40.0"
    assert f"Output: GitHub release ({url}) and deps (?tab=t.x#heading=h.d)" in out
    assert "```\n    ## Tasks\n    Output: not a field\n    ```" in out


def test_link_destinations_do_not_change_index_text():
    t = ud.tasks(rich_raw())[0]
    p, _ = ud.find_field(t, "Output")
    assert p.text == "Output: GitHub release and deps"  # raw text, used for indices
    assert "(https://" in p.display


def test_fields_ignore_text_inside_code_blocks():
    t = ud.tasks(rich_raw())[0]
    p, _ = ud.find_field(t, "Output")
    assert p.start == 90  # the real field, not the "Output:" line inside the table
    assert [f.text for f, _ in t.fields()] == [
        "Description:",
        "Output: GitHub release and deps",
    ]


def test_show_renders_native_code_block_paragraph(capsys):
    # Google Docs stores a native code block as one paragraph starting with U+E907, lines split by \x0b.
    raw = rich_raw()
    raw["body"]["content"][2] = {
        "startIndex": 53,
        "endIndex": 90,
        "paragraph": {
            "elements": [
                run_("", 53),
                run_("## Tasks\x0b- [ ] Calibration\x0bOutput: not a field", 54),
                run_("\n", 89),
            ],
            "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
        },
    }
    ud.cmd_show(RawGog(raw), args(task="Benchmark"))
    out = capsys.readouterr().out
    assert (
        "    ```\n    ## Tasks\n    - [ ] Calibration\n    Output: not a field\n    ```"
        in out
    )
    t = ud.tasks(raw)[0]
    assert ud.find_field(t, "Output")[0].start == 90
