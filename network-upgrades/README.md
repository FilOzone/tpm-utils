# Network upgrade coordination doc tools

Helpers for agents (and humans) working in the Filecoin network upgrade coordination Google Doc, which is instantiated per upgrade from the [network upgrade template](https://docs.google.com/document/d/1KKJj2COb0vIqAQh-4F7fflJjxiTgGrU9oT9B461nsgg/edit).

The doc's "Coordination Meat" tab has one Heading 3 per task, e.g. `🥞 Lotus stable release · owner: FilOz · tester: unassigned`, followed by field bullets (`Description:`, `Depends on:`, `Why:`, `Output:`, `Time:` with `Calendar:` / `Agent/Human:` sub-bullets, `Emergency:`). See the doc's Meta tab for the conventions.

## Why a script

Reading the doc is easy (`gog docs export ... --format=md`). Editing it safely is not:

- Field labels like `Output: link` repeat across tasks, so find-replace hits the wrong task. Edits have to go to an exact index under the right heading.
- The Docs API counts indices in UTF-16 code units, so an emoji counts as 2. Nearly every heading starts with one, and an edit placed by Python string length lands one or two characters off without any error.
- During an upgrade several people edit at once. Edits must not land on stale indices.
- Rewriting the whole tab is never OK: it drops manual formatting (native code blocks), orphans comments, and gives every heading a new ID, which breaks the `Depends on` links.

`upgrade_doc.py` finds a task by its heading, edits the text under it, and submits through a `gog batch`. The batch records the doc revision and refuses to apply if someone edited the doc in between; the script then re-reads and retries.

## Setup

- Install [uv](https://docs.astral.sh/uv/) and [gog](https://github.com/steipete/gogcli), and authenticate gog with an account that can edit the doc (`gog auth add you@example.com`).
- Optionally set defaults:

```bash
export UPGRADE_DOC=<doc id>          # from the doc URL
export UPGRADE_TAB="Coordination Meat" # tab ID or title substring (default)
export GOG_ACCOUNT=you@example.com
```

## Usage

```bash
# List tasks, optionally filtered
./upgrade_doc.py tasks
./upgrade_doc.py tasks --phase "Mainnet Upgrade Day" --status todo
./upgrade_doc.py tasks --owner "FF Governance"

# Show one task (title or unique substring; --phase picks between same-named tasks)
./upgrade_doc.py show "Lotus stable release"
./upgrade_doc.py show "power baseline" --phase "Calibration Upgrade Day"

# Change status: todo, blocked, in-progress, review, done (or pass the emoji)
./upgrade_doc.py status "Lotus stable release" done

# Replace a field's value (works for sub-fields like Calendar and Agent/Human)
./upgrade_doc.py set "Lotus stable release" Output "GitHub release: https://github.com/filecoin-project/lotus/releases/tag/v1.40.0"
./upgrade_doc.py set "Lotus stable release" Calendar "3d"
./upgrade_doc.py set "Lotus stable release" Agent/Human "Steve: 1h, Claude: 15m"

# Add to a field without replacing it (new sub-bullet if the field has sub-bullets, otherwise "; text")
./upgrade_doc.py append "Release final filecoin-ffi" Output "Backport PR: https://github.com/filecoin-project/filecoin-ffi/pull/123"

# Set the tester on an upgrade-day task
./upgrade_doc.py tester "Verify max FIL is still 2B" --phase "Mainnet Upgrade Day" "Steve"
```

URLs in the new text are turned into links. Status and tester edits keep the heading ID, so links to the task keep working.

## Limits

- Text is written as plain text (plus auto-linked URLs). For richer formatting, edit in the Docs UI.
- Adding, removing, or renaming headings is not supported. Do that in the Docs UI, then refresh the doc's Table of Contents (the API cannot refresh it).
- The script edits one task at a time. Fetching the doc takes a few seconds, so batch your thinking, not your calls.

## Tests

```bash
cd network-upgrades
uv sync --group dev
uv run pytest -m "not integration"   # offline; runs in CI
```

The offline tests simulate the doc (with UTF-16 indices like the real API) and check that every command edits exactly the right text, including after emoji and when a concurrent edit forces a retry.

The integration tests edit a throwaway copy of the template through `gog`, so they only run locally and only when asked:

```bash
UPGRADE_DOC_TEST_TEMPLATE=<template doc id> UPGRADE_DOC_TEST_TAB="Coordination Meat" GOG_ACCOUNT=you@example.com \
  uv run pytest -m integration
```

The copy is moved to Drive trash at the end.
