# Meeting prep is a doc-bound Apps Script, not an agent skill

Preparing a Meeting tab for the next meeting is a fixed sequence of mechanical edits with no judgment involved, and whoever hosts that week should be able to do it from the doc without Claude Code, this repo, or Google API credentials. So it is an Apps Script bound to the sync doc (a "🗄️ FOC" menu), with its source kept here and deployed with `clasp push`, rather than a skill in this mostly Python, agent-driven repo. Agent skills remain the right fit for steps that need judgment (for example drafting SP status or summarizing operational events), layered on top of this script later.

## Consequences

- Docs variables can't be set by any API (writing a chip's text desyncs it from the variable; tested 2026-11-09), so the date variables stay a manual step the script spells out.
- The doc's structure is the script's contract: tables are found by header text and sections by heading text, so renaming those means changing the script (a major version bump).
