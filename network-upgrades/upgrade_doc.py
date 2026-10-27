#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Read and update tasks in a network upgrade coordination doc (heading-per-task format).

Each task in the "Coordination Meat" tab is a Heading 3 like
"🥞 Lotus stable release · owner: FilOz · tester: unassigned", followed by field bullets
("Description:", "Depends on:", "Output:", "Time:" with "Calendar:" / "Agent/Human:" sub-bullets, ...).

This script finds a task by its heading and edits the text under it, so agents do not have to do
Google Docs index math by hand. All reads and writes go through the `gog` CLI
(https://github.com/steipete/gogcli), which must be installed and authenticated.

Writes are submitted as a `gog batch`, which records the doc revision and refuses to apply if someone
edited the doc in between. On that conflict the script re-reads the doc and retries.

Examples:
    upgrade_doc.py --doc DOC_ID tasks
    upgrade_doc.py --doc DOC_ID tasks --status todo --phase "Mainnet Upgrade Day"
    upgrade_doc.py --doc DOC_ID show "Lotus stable release"
    upgrade_doc.py --doc DOC_ID status "Lotus stable release" done
    upgrade_doc.py --doc DOC_ID set "Lotus stable release" Output "GitHub release: https://github.com/filecoin-project/lotus/releases/tag/v1.40.0"
    upgrade_doc.py --doc DOC_ID set "Lotus stable release" Agent/Human "Steve: 1h, Claude: 15m"
    upgrade_doc.py --doc DOC_ID append "Release final filecoin-ffi" Output "Backport PR: https://github.com/..."
    upgrade_doc.py --doc DOC_ID tester "Verify max FIL is still 2B" --phase Mainnet "Steve"
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field

STATUSES = {
    "todo": "🥞",
    "blocked": "🛑",
    "in-progress": "🏃",
    "progress": "🏃",
    "review": "🔍",
    "confirming": "🔍",
    "done": "✅",
}
DEFAULT_TAB = "Coordination Meat"
HEADING_RE = re.compile(
    r"^(?P<status>\S+)\s+(?P<title>.*?)\s+·\s+owner:\s*(?P<owner>.*?)(?:\s+·\s+tester:\s*(?P<tester>.*))?$"
)
URL_RE = re.compile(r"https?://\S+[^\s.,;)]")
RETRIES = 3


class UsageError(Exception):
    pass


class RevisionChanged(RuntimeError):
    """The doc changed after it was read, so indices computed from that read are stale."""


def u16(s: str) -> int:
    """Length in UTF-16 code units, which is how the Docs API counts indices (an emoji is usually 2)."""
    return len(s.encode("utf-16-le")) // 2


# ---------------------------------------------------------------- gog


@dataclass
class Gog:
    doc: str
    tab: str
    account: str | None

    def run(self, *args: str, capture: bool = True) -> str:
        cmd = ["gog", *(["-a", self.account] if self.account else []), *args]
        p = subprocess.run(cmd, capture_output=capture, text=True)
        if p.returncode != 0:
            raise RuntimeError(
                f"{' '.join(cmd[:4])} ... failed: {(p.stderr or p.stdout).strip()}"
            )
        return p.stdout

    def resolve_tab(self) -> None:
        """Accept a tab ID or a case-insensitive substring of the tab title."""
        if self.tab.startswith("t."):
            return
        rows = [
            line.split("\t")
            for line in self.run("docs", "list-tabs", self.doc, "-p").splitlines()[1:]
        ]
        hits = [r for r in rows if len(r) > 1 and self.tab.lower() in r[1].lower()]
        if len(hits) != 1:
            raise UsageError(
                f"tab {self.tab!r} matched {[h[1] for h in hits] or 'nothing'}; pass --tab with a tab ID"
            )
        self.tab = hits[0][0]

    def raw(self) -> dict:
        return json.loads(self.run("docs", "raw", self.doc, "--tab", self.tab))

    def begin(self) -> str:
        out = self.run(
            "batch", "begin", "--doc", self.doc, "--name", "upgrade_doc", "-j"
        )
        return json.loads(out)["batch_id"]

    def end(self, batch: str, revision: str) -> None:
        """Submit a batch only if it is pinned to the revision the edits were computed from.

        gog pins a batch to whatever revision is live when the first mutation is queued, which can be newer
        than the read used to compute indices. Compare the pin with that read before submitting.
        """
        pinned = json.loads(self.run("batch", "show", batch, "--json"))["batch"].get(
            "required_revision_id"
        )
        if pinned != revision:
            raise RevisionChanged(f"doc changed since it was read ({batch})")
        try:
            self.run("batch", "end", batch)
        except RuntimeError as e:
            if "revision" in str(e).lower():
                raise RevisionChanged(str(e)) from e
            raise

    def submit(self, ops: list[tuple], revision: str) -> None:
        """Submit ops in one batch guarded by `revision`. Ops are ("replace", start, end, text) or ("insert", index, text)."""
        batch = self.begin()
        try:
            # Apply from the end of the doc backwards so earlier indices stay valid.
            for op in sorted(ops, key=lambda o: o[1], reverse=True):
                if op[0] == "replace":
                    _, s, e, text = op
                    self.run(
                        "docs",
                        "update",
                        self.doc,
                        "--tab",
                        self.tab,
                        "--replace-range",
                        f"{s}:{e}",
                        "--text",
                        text,
                        "--batch",
                        batch,
                    )
                else:
                    _, i, text = op
                    self.run(
                        "docs",
                        "insert",
                        self.doc,
                        text,
                        "--tab",
                        self.tab,
                        "--index",
                        str(i),
                        "--batch",
                        batch,
                    )
            self.end(batch, revision)
        except Exception:
            subprocess.run(["gog", "batch", "abort", batch], capture_output=True)
            raise

    def link_url(self, url: str, revision: str) -> None:
        """Link the (unique) occurrence of `url` in the tab, guarded by `revision` like any other edit."""
        batch = self.begin()
        try:
            self.run(
                "docs",
                "format",
                self.doc,
                "--tab",
                self.tab,
                "--match",
                url,
                "--match-case",
                "--link",
                url,
                "--batch",
                batch,
            )
            self.end(batch, revision)
        except Exception:
            subprocess.run(["gog", "batch", "abort", batch], capture_output=True)
            raise


# ---------------------------------------------------------------- doc model


@dataclass
class Para:
    text: str  # without the trailing newline
    start: int
    end: int  # exclusive, includes the trailing newline
    style: str
    heading_id: str | None
    level: int | None  # bullet nesting level, None if not a bullet


@dataclass
class Task:
    heading: Para
    phase: str
    status: str
    title: str
    owner: str
    tester: str | None
    body: list[Para] = field(default_factory=list)

    def fields(self) -> list[tuple[Para, list[Para]]]:
        """Top-level field bullets and their nested children."""
        out: list[tuple[Para, list[Para]]] = []
        for p in self.body:
            if (
                out
                and p.level is not None
                and out[-1][0].level is not None
                and p.level > out[-1][0].level
            ):
                out[-1][1].append(p)
            else:
                out.append((p, []))
        return out


def all_text(raw: dict) -> str:
    """All text in the tab, including table cells (native code blocks are tables)."""

    def walk(content):
        for c in content:
            if "paragraph" in c:
                yield "".join(
                    e.get("textRun", {}).get("content", "")
                    for e in c["paragraph"]["elements"]
                )
            elif "table" in c:
                for row in c["table"]["tableRows"]:
                    for cell in row["tableCells"]:
                        yield from walk(cell["content"])

    return "".join(walk(raw["body"]["content"]))


def paragraphs(raw: dict) -> list[Para]:
    out = []
    for c in raw["body"]["content"]:
        if "paragraph" not in c:
            continue
        p = c["paragraph"]
        text = "".join(e.get("textRun", {}).get("content", "") for e in p["elements"])
        st = p.get("paragraphStyle", {})
        bullet = p.get("bullet")
        out.append(
            Para(
                text.rstrip("\n"),
                c["startIndex"],
                c["endIndex"],
                st.get("namedStyleType", "NORMAL_TEXT"),
                st.get("headingId"),
                bullet.get("nestingLevel", 0) if bullet is not None else None,
            )
        )
    return out


def tasks(raw: dict) -> list[Task]:
    out: list[Task] = []
    phase = ""
    current: Task | None = None
    for p in paragraphs(raw):
        if p.style.startswith("HEADING_"):
            current = None
            if p.style in ("HEADING_1", "HEADING_2"):
                phase = p.text.strip()
            m = HEADING_RE.match(p.text.strip())
            if p.style == "HEADING_3" and m:
                current = Task(
                    p, phase, m["status"], m["title"], m["owner"], m["tester"]
                )
                out.append(current)
        elif current is not None and p.text.strip():
            current.body.append(p)
    return out


def find_task(all_tasks: list[Task], query: str, phase: str | None) -> Task:
    q = query.lower()
    pool = [t for t in all_tasks if phase is None or phase.lower() in t.phase.lower()]
    exact = [t for t in pool if t.title.lower() == q]
    hits = exact or [t for t in pool if q in t.title.lower()]
    if len(hits) != 1:
        listing = "\n".join(f"  [{t.phase}] {t.title}" for t in hits) or "  (none)"
        hint = " Narrow it with --phase." if hits else ""
        raise UsageError(f"task {query!r} matched {len(hits)} tasks:{hint}\n{listing}")
    return hits[0]


def find_field(task: Task, label: str) -> tuple[Para, list[Para]]:
    """Find a field line ("Output:") at any level, so sub-fields like "Calendar:" work too."""
    want = label.lower().rstrip(":") + ":"
    for parent, children in task.fields():
        for p in [parent, *children]:
            if p.text.strip().lower().startswith(want):
                kids = children if p is parent else []
                return p, kids
    labels = [p.text.split(":")[0] for p in task.body if ":" in p.text]
    raise UsageError(
        f"no {label!r} line under {task.title!r}; found: {', '.join(labels)}"
    )


def value_range(p: Para) -> tuple[int, int, str]:
    """Docs range of the text after "Label:" on a field line, plus that text."""
    head, _, rest = p.text.partition(":")
    start = p.start + u16(head) + 1
    lead = len(rest) - len(rest.lstrip(" "))
    return start + lead, p.end - 1, rest.strip()


# ---------------------------------------------------------------- commands


def cmd_tasks(g: Gog, a: argparse.Namespace) -> None:
    want = STATUSES.get(a.status, a.status) if a.status else None
    for t in tasks(g.raw()):
        if a.phase and a.phase.lower() not in t.phase.lower():
            continue
        if want and t.status != want:
            continue
        if a.owner and a.owner.lower() not in t.owner.lower():
            continue
        tester = f" · tester: {t.tester}" if t.tester is not None else ""
        print(
            f"{t.status} [{t.phase}] {t.title} · owner: {t.owner}{tester} (#heading={t.heading.heading_id})"
        )


def cmd_show(g: Gog, a: argparse.Namespace) -> None:
    t = find_task(tasks(g.raw()), a.task, a.phase)
    print(f"{t.heading.text}\nphase: {t.phase}\nheading id: {t.heading.heading_id}\n")
    for p in t.body:
        indent = "  " * ((p.level or 0) + 1)
        print(f"{indent}- {p.text}")


def link_new_urls(g: Gog, a: argparse.Namespace) -> None:
    """Make URLs in the new text clickable (the Docs API does not auto-link).

    gog can only format by text match, and markdown edits cannot be revision-guarded, so a URL is linked only
    when its text appears exactly once in the tab. Otherwise it is left as plain text with a warning rather
    than risk linking the wrong occurrence (e.g. a prefix of a longer URL).
    """
    for url in URL_RE.findall(a.text):
        for attempt in range(RETRIES):
            raw = g.raw()
            n = all_text(raw).count(url)
            if n != 1:
                print(
                    f"warning: left {url} as plain text (appears {n} times in the tab); link it in the Docs UI",
                    file=sys.stderr,
                )
                break
            try:
                g.link_url(url, raw["revisionId"])
                break
            except RevisionChanged:
                if attempt == RETRIES - 1:
                    raise
                print("doc changed while linking; retrying", file=sys.stderr)


def with_retry(g: Gog, build) -> None:
    """Re-read the doc and rebuild the edit if the guarded batch hits a concurrent edit."""
    for attempt in range(RETRIES):
        raw = g.raw()
        ops, after = build(raw)
        try:
            g.submit(ops, raw["revisionId"])
        except RevisionChanged:
            if attempt < RETRIES - 1:
                print("doc changed while editing; retrying", file=sys.stderr)
                continue
            raise
        if after:
            after()
        return


def cmd_status(g: Gog, a: argparse.Namespace) -> None:
    emoji = STATUSES.get(a.new_status.lower(), a.new_status)

    def build(raw):
        t = find_task(tasks(raw), a.task, a.phase)
        s = t.heading.start + (u16(t.heading.text) - u16(t.heading.text.lstrip()))
        print(f"{t.status} -> {emoji}  {t.title}")
        return [("replace", s, s + u16(t.status), emoji)], None

    with_retry(g, build)


def cmd_tester(g: Gog, a: argparse.Namespace) -> None:
    def build(raw):
        t = find_task(tasks(raw), a.task, a.phase)
        if t.tester is None:
            raise UsageError(
                f"{t.title!r} has no tester slot (only upgrade-day tasks do)"
            )
        marker = "tester: "
        k = t.heading.text.rindex(marker) + len(marker)
        s = t.heading.start + u16(t.heading.text[:k])
        print(f"tester {t.tester!r} -> {a.name!r}  {t.title}")
        return [("replace", s, t.heading.end - 1, a.name)], None

    with_retry(g, build)


def cmd_set(g: Gog, a: argparse.Namespace) -> None:
    def build(raw):
        t = find_task(tasks(raw), a.task, a.phase)
        p, _ = find_field(t, a.field)
        s, e, old = value_range(p)
        print(f"{p.text.split(':')[0]}: {old!r} -> {a.text!r}  ({t.title})")
        if s == e:  # empty value: add after "Label:" with one space
            return [("insert", e, ("" if p.text.endswith(" ") else " ") + a.text)], (
                lambda: link_new_urls(g, a)
            )
        return [("replace", s, e, a.text)], (lambda: link_new_urls(g, a))

    with_retry(g, build)


def cmd_append(g: Gog, a: argparse.Namespace) -> None:
    """Add a line to a field: a new sub-bullet if the field has them, otherwise after the inline value."""

    def build(raw):
        t = find_task(tasks(raw), a.task, a.phase)
        p, kids = find_field(t, a.field)
        if kids:
            last = kids[-1]
            print(
                f"new sub-bullet under {p.text.split(':')[0]!r}: {a.text!r}  ({t.title})"
            )
            return [("insert", last.end - 1, "\n" + a.text)], (
                lambda: link_new_urls(g, a)
            )
        s, e, old = value_range(p)
        if not old:
            return [
                ("insert", p.end - 1, ("" if p.text.endswith(" ") else " ") + a.text)
            ], (lambda: link_new_urls(g, a))
        print(f"appended to {p.text.split(':')[0]!r}: {a.text!r}  ({t.title})")
        return [("insert", p.end - 1, "; " + a.text)], (lambda: link_new_urls(g, a))

    with_retry(g, build)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--doc",
        default=os.environ.get("UPGRADE_DOC"),
        help="Google Doc ID (or $UPGRADE_DOC)",
    )
    ap.add_argument(
        "--tab",
        default=os.environ.get("UPGRADE_TAB", DEFAULT_TAB),
        help=f"tab ID or title substring (default: {DEFAULT_TAB!r}, or $UPGRADE_TAB)",
    )
    ap.add_argument(
        "--account",
        default=os.environ.get("GOG_ACCOUNT"),
        help="gog account email (or $GOG_ACCOUNT)",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("tasks", help="list tasks with status, owner, and tester")
    p.add_argument(
        "--status", help="todo, blocked, in-progress, review, done (or the emoji)"
    )
    p.add_argument(
        "--phase", help="phase heading substring, e.g. 'Mainnet Upgrade Day'"
    )
    p.add_argument("--owner", help="owner substring")
    p.set_defaults(fn=cmd_tasks)

    def task_parser(name, help_):
        p = sub.add_parser(name, help=help_)
        p.add_argument("task", help="task title or a unique substring of it")
        p.add_argument(
            "--phase", help="phase heading substring, to pick between same-named tasks"
        )
        return p

    task_parser("show", "print one task's heading and fields").set_defaults(fn=cmd_show)
    p = task_parser("status", "change a task's status emoji")
    p.add_argument(
        "new_status", help="todo, blocked, in-progress, review, done (or the emoji)"
    )
    p.set_defaults(fn=cmd_status)
    p = task_parser("tester", "set the tester on an upgrade-day task")
    p.add_argument("name")
    p.set_defaults(fn=cmd_tester)
    p = task_parser(
        "set", "replace the value after 'Field:' (works for sub-fields like Calendar)"
    )
    p.add_argument("field", help="e.g. Output, Calendar, Agent/Human, Emergency")
    p.add_argument("text")
    p.set_defaults(fn=cmd_set)
    p = task_parser("append", "add a line to a field without replacing what is there")
    p.add_argument("field")
    p.add_argument("text")
    p.set_defaults(fn=cmd_append)

    a = ap.parse_args()
    if not a.doc:
        ap.error("--doc or $UPGRADE_DOC is required")
    g = Gog(a.doc, a.tab, a.account)
    try:
        g.resolve_tab()
        a.fn(g, a)
    except UsageError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
