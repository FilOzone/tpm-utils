# Agent instructions: sync doc Apps Script

## Versioning

`SCRIPT_VERSION` in `Code.gs` uses `X.Y` and is shown in the doc's menu title, so people can see which version is live.

- **Every commit that changes the script** (`*.gs`, `Sidebar.html`, `appsscript.json`) bumps Y in the same commit (`'1.3'` → `'1.4'`). Do not wait for a deploy; a committed version may not be deployed yet, and that is fine.
- **Bump X** (`'1.7'` → `'2.0'`) only when the doc itself must change for the script to work (renamed anchors, new tables or sections the script relies on), and say so in the commit body. The maintainer decides; ask if unsure.
- Do not use the `version` field in `appsscript.json`.

## Deploying

Deploy only when asked: `clasp --user filoz push` from this directory pushes to the live doc for everyone. See README.md for setup and for testing on a copy first (`-P .clasp.test.json`). Never push to production to test.

## Before committing

- Run `node --test test/` (from this directory). Add tests for any change to `Dates.gs`; keep `Dates.gs` free of Apps Script services so it stays testable in Node.
- Keep the "What it does" table in README.md in sync with the steps in `PrepareNextMeeting.gs`, including the anchor text each step looks for.
- Every source file starts with the "source of truth is GitHub" header; keep it.
- Top-level declarations in `.gs` files use `function`/`var`, not `const`/`let`, so the Node test sandbox can see them.

## Design constraints

- Steps find tables by header text and sections by heading text, never by position.
- A step must not delete content it isn't sure about (see the OOO rules); flag it as ⚠️ instead.
- Each step is a function `run(ctx)` that returns `{status, detail}`; throw `StepError` for problems a person can fix in the doc. All steps run in one server call (`prepareActiveTab`), because opening the doc loads every tab and takes ~25s: don't add per-step server calls or extra Docs API `documents.get` reads (~16s each).
