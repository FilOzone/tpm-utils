# Sync doc Apps Script (🗄️ FOC menu)

Apps Script bound to the [FOC Weekly Engineering Sync doc](https://docs.google.com/document/d/1NPRQSbDfTcvAJo2cEIBOTax6VdBg1nboUomcml1EuLE/edit). It adds a **🗄️ FOC (vX.Y)** menu; the version in the menu title is the version that is live for everyone (reload the doc after a deploy to see a new one). Its **About this menu** item opens this README. Terms follow [../GLOSSARY.md](../GLOSSARY.md); why this is an Apps Script is in [ADR 0001](../docs/adr/0001-doc-bound-apps-script-for-meeting-prep.md).

This GitHub folder is the source of truth. Edits made in the Apps Script editor are overwritten by the next `clasp push`.

## Prepare for next meeting

### For the host

1. Duplicate the last Meeting tab (tab menu ⋮ → Duplicate).
2. Rename the copy to the next meeting's date as `YYYY-MM-DD` (for example `2026-11-17`). Everything the script does is based on that date.
3. With that tab open, choose **🗄️ FOC → Prepare for next meeting…** and click **Prepare**.
4. Wait about a minute; the dialog blocks the doc while it works, because the doc has many tabs and Apps Script loads all of them. It then closes and the results open in a sidebar: each step shows ✅ (done), ⚠️ (done, but something needs a look), ⏭️ (left for you, with instructions) or ❌ (failed; the rest still run). If the tab can't be prepared (title not a date, already prepared), the dialog says why instead.
5. Do the ⏭️ and ⚠️ items by hand. The date variables are always one of them: click any date in the tab, choose ↗ to open Variables, and set the three values the sidebar shows.

The first run asks each person to authorize the script (it needs to edit the doc and show a sidebar). The consent screen opens as a popup; if the doc only shows "Running script", look for it behind the window or allow popups for docs.google.com. To undo a run, use File → Version history.

### What it does

| Step | What changes | Found by |
|---|---|---|
| Workstream tables | Each row's Expected column gets a copy of its "Plan until next meeting" cell (bullets, links and chips kept) and a yellow `#ffffa6` background; the plan and "What actually happened" cells are emptied. Project, Owner(s) and Callouts are untouched. | Every table whose header row contains "What we expected", "What actually happened" and "Plan until next meeting", so new workstreams are picked up automatically |
| Sync topics | Text cleared in every row below the header; rows kept, reset to white | Header containing "Sync Topic" |
| Group Snaps | Everything under the heading (snaps, images, stray paragraphs) removed except the prompt line; one empty bullet left | Heading containing "Group Snaps" |
| Top SP needs | Bullets replaced by one empty bullet | Paragraph starting "Top SP needs" |
| SP status numbers | Cells holding only a number (optionally with `~`, a sign, `%` or a unit like `PiB`) are emptied; labels, ✔️/❌ headers, colors and the chart stay | Header containing "Mainnet" and "Calibration" |
| Operational events | Text cleared in every row below the header; status row colors reset to white | Header containing "Date/window" |
| Upcoming OOO | Entries whose end date is before the meeting are removed. Entries with unclear dates (e.g. "16th-21st", "9/7/26", "mid August", "Nov 9, out 2 weeks") are kept and listed as ⚠️. Date chips and the text around them are read together | "Upcoming OOO" column of the Individual updates table (header containing "Person" and "Upcoming OOO") |
| FOC review stats | Text cleared in every row below the header; Rev/PR shading reset to white | Header containing "Contributor" and "Rev/PR" |
| Recording | Emptied | Heading exactly "Recording" |
| AI Meeting Notes | Everything under the heading removed, up to the next heading of the same or higher level | Heading containing "AI Meeting Notes" |
| Date variables | ⏭️ always: shows the values to set (`lastWeekReportDate` = latest dated tab before this one, `thisWeekReportDate` = tab title, `nextWeekReportDate` = title + 7 days) | Tab titles |
| Checkboxes | Every person row's checklist cells (the columns between Person and Upcoming OOO) get one fresh unchecked checkbox; the "Add anyone else…" row is skipped. "Start recording" under Agenda keeps its text and gets a new unchecked checkbox (⚠️ if that line is missing). Runs last (see below) | Individual updates table (as for Upcoming OOO); paragraph starting "Start recording" |

If a "Found by" anchor is renamed in the doc, that step fails with ❌ and names the text it looked for; update the step in [PrepareNextMeeting.gs](PrepareNextMeeting.gs) (and bump the major version, see [AGENTS.md](AGENTS.md)).

### Guards

The script refuses to run when the active tab's title is not a real `YYYY-MM-DD` date, when another tab has the same title, or when the tab was already prepared. Preparing is recorded per tab (document properties) as soon as you confirm, because running twice would copy the now-empty plan column over the Expected column. Only one run at a time per doc: a second one waits up to a minute for the first, then sees the tab is already prepared (or says someone else is preparing a tab).

### Running it twice

If a run was interrupted and you really want to run it again on the same tab, open Extensions → Apps Script, select `resetPreparedMarkers` and Run. That clears the marker for every tab. Better: delete the tab and duplicate again.

### Why some steps are the way they are

- **Date variables are manual.** No API can set a Docs variable's value: writing a chip's text through the Docs API changes only that one instance and leaves the variable (and its other instances) behind. Tested on a copy of the doc on 2026-11-09.
- **Checkboxes are re-created, not unchecked.** Neither Apps Script nor the Docs API exposes whether a checklist item is checked, and Apps Script can't create checklists. The step replaces each checklist cell's content with a new paragraph, tags it with a named range, and has the Docs API (advanced service) turn the tagged paragraphs into new `BULLET_CHECKBOX` lists. "Start recording" keeps its paragraph; the API removes its bullet and creates a new checkbox. The step checks that the API sees every tagged paragraph before writing anything.
- **One server call, one Docs API read.** Opening the doc loads every tab, however little is asked for: measured 2026-11-09 on a 42-tab copy, `DocumentApp.getActiveDocument()` took 25s and a Docs API `documents.get` that asked only for tab titles took 16s; everything else is quick. So the dialog opens without touching the doc, the guards and all steps run in the one call after you confirm (the confirmation can't name the tab, since reading it costs the 25s; the results do), and the checkbox step reads the Docs API once. A run takes about a minute, about half of it opening the doc; the sidebar's last line shows the timings. The checkbox step runs last because it saves and closes the doc for the Docs API. Fewer tabs (for example, archiving old Meeting tabs to another doc) would make it faster.
- **Empty bullets are fresh copies.** Clearing a body list item that is followed by a non-list paragraph deletes it (and can take the paragraph before it along), so Group Snaps and Top SP needs get a cleared copy of their first bullet, inserted before the old bullets are removed.
- **OOO parsing is deliberately cautious.** Only entries it can date with certainty are removed. Notable rules (see [Dates.gs](Dates.gs)): a number counts as a day only right next to a month name ("Nov 9", "23-27 Nov", "Dec 7/8th"), so any other number ("out 2 weeks", "12/3", "until 2027") or a month without a day ("mid December") makes the entry unclear; a year applies only to the date right before it, and a date without one takes the year nearest the meeting; "week of X" lasts until X + 6 days; "may" counts as a month only next to a day number; the entry ends at the latest date in its text and date chips.

## Development

Files:

| File | Purpose |
|---|---|
| [Code.gs](Code.gs) | `SCRIPT_VERSION`, links, the `onOpen` menu, and "About this menu" |
| [PrepareNextMeeting.gs](PrepareNextMeeting.gs) | Menu entry point, guards, and one function per step |
| [DocEdits.gs](DocEdits.gs) | DocumentApp helpers: find tables/headings, clear and copy cells |
| [Dates.gs](Dates.gs) | Pure date logic (meeting date, variables, OOO parsing); no Apps Script services |
| [PrepareDialog.html](PrepareDialog.html) | Confirmation and progress dialog; makes the one server call |
| [Sidebar.html](Sidebar.html) | Results of a run |
| [AboutDialog.html](AboutDialog.html) | "About this menu": opens this README |
| [test/](test/) | Node tests for `Dates.gs` |

Run the tests (Node 18+, no dependencies):

```bash
cd weekly-engineering-sync/apps-script
node --test test/
```

DocumentApp code can't run locally, so test document changes on a copy of the doc (below) before deploying.

### One-time setup

1. Install clasp: `npm install -g @google/clasp`.
2. Turn on the Apps Script API for your Google account at https://script.google.com/home/usersettings.
3. Log in with the account that can edit the doc. A named user keeps it separate from other clasp logins: `clasp login --user filoz`.

### Deploy to the real doc

The production project is bound to the doc; its ID is in `.clasp.json`. For every deploy:

```bash
cd weekly-engineering-sync/apps-script
clasp --user filoz push
```

Reload the doc and check the menu title shows the version you pushed. Deploys can lag commits; the menu title tells you what is live.

If `.clasp.json` is missing (first deploy), create the bound project once. Run `create-script` in an empty directory, because it also downloads a default `appsscript.json` over the local one, and leave out `--type docs`: in clasp 3 it creates a new document and ignores `--parentId`.

```bash
cd "$(mktemp -d)"
clasp --user filoz create-script --title "FOC sync doc menu" --parentId 1NPRQSbDfTcvAJo2cEIBOTax6VdBg1nboUomcml1EuLE
cat .clasp.json   # copy the scriptId
```

Write `weekly-engineering-sync/apps-script/.clasp.json` as `{"scriptId": "<scriptId>"}`, commit it, and push once with `clasp --user filoz push --force` (`--force` replaces the new project's default manifest; without it, clasp asks and a non-interactive shell answers no).

### Test on a copy of the doc

1. Make a copy of the doc (File → Make a copy). The copy carries its own copy of the bound script (a separate Apps Script project, at the version that was live), so it shows the menu; the fewer tabs the doc has, the faster test runs are.
2. Find that project's ID: in the copy, Extensions → Apps Script (pick "FOC sync doc menu" if asked); the ID is in the editor URL, `.../projects/<ID>/edit`. Write it to `weekly-engineering-sync/apps-script/.clasp.test.json` (gitignored) as `{"scriptId": "<ID>"}` and push your version there with an absolute project path (clasp 3 rejects a relative `-P` path as escaping the project root):

   ```bash
   cd weekly-engineering-sync/apps-script
   clasp --user filoz -P "$PWD/.clasp.test.json" push --force
   ```

   Don't bind a second project to the copy with `create-script`: the doc would show two menus.
3. In the copy: duplicate the newest Meeting tab, rename it to the next date, run the menu, and check each row of the "What it does" table above. Also check that a second run is refused. The first run asks you to authorize the test project.

## Suggested host instructions for the doc

The "How to prepare for this meet as the host" section of the Meeting tab (keep the three variable lines with their chips):

- Duplicate the previous Meeting tab (tab menu ⋮ → Duplicate) and rename the copy to the meeting date as `YYYY-MM-DD`.
- On the new tab, run **🗄️ FOC → Prepare for next meeting…** and click Prepare. It takes about a minute, then the results open in a sidebar. The first time, Google asks you to authorize the script; if nothing appears but "Running script", look for a blocked popup.
- Do the ⏭️ / ⚠️ items the sidebar lists. One is always the date variables: click any date in the tab, choose ↗ to open Variables, and set the values the sidebar shows (lastWeekReportDate, thisWeekReportDate, nextWeekReportDate).
- Paste the new FOC review stats (`foc-review-stats --format html`). After the meeting, add the recording link and the AI meeting notes.
- Details or problems: 🗄️ FOC → About this menu.
- Collapse this section so it doesn't clutter for everyone else…
