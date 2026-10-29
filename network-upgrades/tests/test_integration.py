"""Live test against a throwaway copy of the coordination doc template.

Opt-in: set UPGRADE_DOC_TEST_TEMPLATE to the template doc ID (and GOG_ACCOUNT / UPGRADE_DOC_TEST_TAB if needed),
then run `uv run pytest -m integration`. The copy is moved to Drive trash afterwards.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import upgrade_doc as ud

TEMPLATE = os.environ.get("UPGRADE_DOC_TEST_TEMPLATE")
TAB = os.environ.get("UPGRADE_DOC_TEST_TAB", "Coordination Meat")
ACCOUNT = os.environ.get("GOG_ACCOUNT")
SCRIPT = Path(__file__).resolve().parent.parent / "upgrade_doc.py"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not TEMPLATE, reason="set UPGRADE_DOC_TEST_TEMPLATE to run live tests"
    ),
]


def gog(*args: str) -> str:
    cmd = ["gog", *(["-a", ACCOUNT] if ACCOUNT else []), *args]
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout


@pytest.fixture(scope="module")
def doc_copy():
    out = json.loads(
        gog(
            "docs",
            "copy",
            TEMPLATE,
            "TEST upgrade_doc.py integration (safe to delete)",
            "-j",
        )
    )
    doc_id = out["file"]["id"]
    yield doc_id
    gog("drive", "delete", doc_id, "--force")  # moves to trash


def run(doc_id: str, *args: str) -> str:
    env = {**os.environ, "UPGRADE_DOC": doc_id, "UPGRADE_TAB": TAB}
    p = subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True, env=env
    )
    assert p.returncode == 0, p.stderr
    return p.stdout


def test_round_trip_edits(doc_copy):
    task = "Lotus stable release"
    url = "https://github.com/filecoin-project/lotus/releases/tag/v0.0.0-test"
    run(doc_copy, "status", task, "done")
    run(doc_copy, "set", task, "Output", f"GitHub release: {url}")
    run(doc_copy, "set", task, "Calendar", "3d")
    run(doc_copy, "append", task, "Description", "Added by integration test")
    shown = run(doc_copy, "show", task)
    assert shown.startswith(f"✅ {task}")
    assert f"Output: GitHub release: {url}" in shown
    assert "Calendar: 3d" in shown
    assert "- Added by integration test" in shown

    g = ud.Gog(doc_copy, TAB, ACCOUNT)
    g.resolve_tab()
    raw = g.raw()
    links = [
        e["textRun"]["textStyle"]["link"].get("url")
        for c in raw["body"]["content"]
        for e in c.get("paragraph", {}).get("elements", [])
        if "link" in e.get("textRun", {}).get("textStyle", {})
    ]
    assert url in links


def test_tester_on_upgrade_day_task(doc_copy):
    run(
        doc_copy,
        "tester",
        "power baseline",
        "--phase",
        "Mainnet Upgrade Day",
        "Integration Tester",
    )
    assert "tester: Integration Tester" in run(
        doc_copy, "show", "power baseline", "--phase", "Mainnet Upgrade Day"
    )
