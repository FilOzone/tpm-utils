/**
 * 🗄️ FOC → Prepare for next meeting: turns a freshly duplicated Meeting tab (renamed to the meeting date,
 * YYYY-MM-DD) into a blank agenda, carrying last meeting's plans into the Expected column.
 *
 * Flow: the menu item opens PrepareDialog.html right away (showing a dialog does not load the document). After the
 * person confirms, the dialog makes one server call, prepareActiveTab(), which opens the document once, checks the
 * guards and runs every step in order, while the modal dialog keeps the editor from being edited. Then the dialog
 * opens Sidebar.html with the results and closes itself.
 *
 * Opening the document is the slow part: Apps Script and the Docs API load every tab (~25s and ~16s for this doc as
 * of 2026-11, regardless of what is asked for), so the run opens it once and reads the Docs API once. Steps are
 * independent; one failing does not stop the rest. What each step does and why: README.md in this folder.
 *
 * Source of truth is GitHub (https://github.com/FilOzone/tpm-utils/tree/master/weekly-engineering-sync/apps-script).
 * Edits made in the Apps Script editor are overwritten by the next `clasp push`.
 */

var EXPECTED_YELLOW = '#ffffa6';
var CHECKBOX_RANGE_NAME = 'foc-prep-checkbox'; // new paragraphs that become checkboxes
var RECHECK_RANGE_NAME = 'foc-prep-recheck'; // existing checklist items whose checkbox is re-created
var ZERO_WIDTH_PLACEHOLDER = '\u200b'; // keeps a tagged empty paragraph non-empty; deleted by the API batch
var PREPARED_KEY_PREFIX = 'prepared:';

/** The steps, in sidebar order. Each `run(ctx)` returns { status, detail } or throws (StepError for doc problems). */
var PREP_STEPS = [
  { id: 'workstreams', label: 'Workstream tables: plan → Expected (yellow); clear plan and actual', run: stepWorkstreams_ },
  { id: 'syncTopics', label: 'Clear the Sync topics table', run: function (ctx) { return clearNamedTable_(ctx, ['Sync Topic'], 'Sync topics'); } },
  { id: 'groupSnaps', label: 'Clear Group Snaps', run: stepGroupSnaps_ },
  { id: 'topSpNeeds', label: 'Clear Top SP needs', run: stepTopSpNeeds_ },
  { id: 'spStatus', label: 'Clear the SP status numbers', run: stepSpStatus_ },
  { id: 'opsEvents', label: 'Clear Summary of operational events', run: function (ctx) { return clearNamedTable_(ctx, ['Date/window'], 'Summary of operational events'); } },
  { id: 'ooo', label: 'Remove past Upcoming OOO entries', run: stepOoo_ },
  { id: 'reviewStats', label: 'Clear FOC review stats', run: function (ctx) { return clearNamedTable_(ctx, ['Contributor', 'Rev/PR'], 'FOC review stats'); } },
  { id: 'recording', label: 'Clear the Recording link', run: stepRecording_ },
  { id: 'aiNotes', label: 'Clear AI Meeting Notes', run: stepAiNotes_ },
  { id: 'dateVariables', label: 'Date variables', run: stepDateVariables_ },
  // Last: it saves and closes the document so the Docs API sees the edits, which ends DocumentApp use for the run.
  { id: 'checkboxes', label: 'Reset checkboxes (Individual updates, Start recording)', run: stepCheckboxes_ },
];

function done_(detail) { return { status: 'done', detail: detail || '' }; }
function warn_(detail) { return { status: 'warn', detail: detail }; }
function skipped_(detail) { return { status: 'skipped', detail: detail }; }
function failed_(detail) { return { status: 'failed', detail: detail }; }

// ---------------------------------------------------------------- menu entry point

function prepareForNextMeeting() {
  var template = HtmlService.createTemplateFromFile('PrepareDialog');
  template.payload = jsonForHtml_({ version: SCRIPT_VERSION, readmeUrl: README_URL });
  DocumentApp.getUi().showModalDialog(template.evaluate().setWidth(460).setHeight(330), 'Prepare for next meeting (v' + SCRIPT_VERSION + ')');
}

/** JSON that is safe to print inside a <script> tag. */
function jsonForHtml_(value) {
  return JSON.stringify(value).replace(/</g, '\\u003c');
}

/** Why the active tab can't be prepared, or null if it can. */
function preconditionProblem_(doc, tab) {
  var title = tab.getTitle().trim();
  if (tab.getType() !== DocumentApp.TabType.DOCUMENT_TAB) return 'The active tab is not a document tab.';
  if (!parseMeetingDate(title)) {
    return 'Rename this tab to the meeting date as YYYY-MM-DD (for example 2026-11-17) and run this again.\n\n' +
      'Everything the script does is based on that date. Current tab title: "' + title + '".';
  }
  var sameTitle = allTabs_(doc).filter(function (t) { return t.getTitle().trim() === title; });
  if (sameTitle.length > 1) return 'Another tab is also titled "' + title + '". Give this tab the date of the next meeting.';
  var prepared = PropertiesService.getDocumentProperties().getProperty(PREPARED_KEY_PREFIX + tab.getId());
  if (prepared) {
    return 'This tab was already prepared (' + prepared + '). Running again would overwrite the Expected column ' +
      'with the now-empty plan column. To run anyway, see "Running it twice" in the README:\n' + SOURCE_URL;
  }
  return null;
}

function allTabs_(doc) {
  var out = [];
  (function walk(tabs) {
    tabs.forEach(function (t) {
      out.push(t);
      walk(t.getChildTabs());
    });
  })(doc.getTabs());
  return out;
}

/** Run from the Apps Script editor to allow every tab to be prepared again (see README). */
function resetPreparedMarkers() {
  var props = PropertiesService.getDocumentProperties();
  Object.keys(props.getProperties()).forEach(function (k) {
    if (k.indexOf(PREPARED_KEY_PREFIX) === 0) props.deleteProperty(k);
  });
}

// ---------------------------------------------------------------- dialog entry points

/**
 * Called by the dialog once the person confirms: prepares the active tab. Returns { problem } when a guard refuses,
 * otherwise { title, meetingDate, seconds, openSeconds, results: [{ id, label, status, detail, seconds }] } in
 * PREP_STEPS order. A failing step comes back as { status: 'failed' } and the rest still run.
 */
function prepareActiveTab() {
  var started = Date.now();
  var doc = DocumentApp.getActiveDocument(); // loads the whole document; the slow part
  var openSeconds = secondsSince_(started);
  var tab = doc.getActiveTab();
  var problem = preconditionProblem_(doc, tab);
  if (problem) return { problem: problem };

  // Mark before running so a second run can't shift plan → Expected twice, even if this run fails partway.
  PropertiesService.getDocumentProperties().setProperty(PREPARED_KEY_PREFIX + tab.getId(), new Date().toISOString());

  var title = tab.getTitle().trim();
  var ctx = { doc: doc, tab: tab, body: tab.asDocumentTab().getBody(), meetingDate: parseMeetingDate(title) };
  var results = PREP_STEPS.map(function (step) {
    var t = Date.now();
    var r;
    try {
      r = step.run(ctx);
    } catch (e) {
      r = failed_((e && e.message) || String(e));
    }
    return { id: step.id, label: step.label, status: r.status, detail: r.detail, seconds: secondsSince_(t) };
  });
  return { title: title, meetingDate: ctx.meetingDate, seconds: secondsSince_(started), openSeconds: openSeconds, results: results };
}

/** Called by the dialog with prepareActiveTab()'s result: shows it in the sidebar so the doc can be scrolled again. */
function showPrepResults(outcome) {
  var template = HtmlService.createTemplateFromFile('Sidebar');
  template.payload = jsonForHtml_({ outcome: outcome, version: SCRIPT_VERSION, sourceUrl: SOURCE_URL, issuesUrl: ISSUES_URL });
  DocumentApp.getUi().showSidebar(template.evaluate().setTitle('Prepare for next meeting'));
}

function secondsSince_(t) {
  return Math.round((Date.now() - t) / 100) / 10;
}

// ---------------------------------------------------------------- steps

function stepWorkstreams_(ctx) {
  var needles = ['What we expected', 'What actually happened', 'Plan until next meeting'];
  var tables = findTables_(ctx.body, needles);
  if (!tables.length) {
    throw new StepError('Could not find any workstream tables (looked for header rows containing "' + needles.join('", "') + '").');
  }
  var rows = 0;
  tables.forEach(function (table) {
    var headers = headerTexts_(table);
    var expected = colIndex_(headers, needles[0]);
    var actual = colIndex_(headers, needles[1]);
    var plan = colIndex_(headers, needles[2]);
    var last = Math.max(expected, actual, plan);
    for (var r = 1; r < table.getNumRows(); r++) {
      var row = table.getRow(r);
      if (row.getNumCells() <= last) continue;
      var expectedCell = row.getCell(expected);
      replaceCellWithCopy_(expectedCell, row.getCell(plan));
      expectedCell.setBackgroundColor(EXPECTED_YELLOW);
      clearCell_(row.getCell(plan));
      clearCell_(row.getCell(actual));
      rows++;
    }
  });
  return done_(tables.length + ' tables, ' + rows + ' rows');
}

function clearNamedTable_(ctx, needles, name) {
  var rows = clearTableRows_(findTable_(ctx.body, needles, name));
  return done_(rows + ' rows cleared');
}

function stepGroupSnaps_(ctx) {
  var heading = findHeading_(ctx.body, 'Group Snaps');
  var els = sectionElements_(heading, 6);
  // The prompt ("Any great work you saw…") is the first plain paragraph with text; everything else is a snap.
  var prompt = els.filter(function (el) {
    return el.getType() === DocumentApp.ElementType.PARAGRAPH && textOf_(el).trim();
  })[0];
  var snaps = els.length - (prompt ? 1 : 0);
  leaveOneEmptyBullet_(ctx.body, els, prompt, heading);
  return done_(snaps + ' items cleared');
}

function stepTopSpNeeds_(ctx) {
  var label = findParagraphStartingWith_(ctx.body, 'Top SP needs');
  if (!label) throw new StepError('Could not find the "Top SP needs:" line.');
  var items = [];
  for (var el = label.getNextSibling(); el && el.getType() === DocumentApp.ElementType.LIST_ITEM; el = el.getNextSibling()) {
    items.push(el);
  }
  leaveOneEmptyBullet_(ctx.body, items, null, label);
  return done_(items.length + ' bullets cleared');
}

// A cell holding only a number, optionally with a sign, "~", "%", or a unit like "PiB" or "k".
var SP_NUMBER_RE = /^\s*[~≈+\-]?\s*\d[\d,.\s]*(%|[kKmM]|\s*[KMGTPE]i?B)?\s*$/;

function stepSpStatus_(ctx) {
  var table = findTable_(ctx.body, ['Mainnet', 'Calibration'], 'SP status');
  // Only number cells are cleared, so labels, ✔️/❌ headers, colors and the chart image stay.
  var cleared = 0;
  for (var r = 1; r < table.getNumRows(); r++) {
    var row = table.getRow(r);
    for (var c = 1; c < row.getNumCells(); c++) {
      var cell = row.getCell(c);
      if (SP_NUMBER_RE.test(cell.getText())) {
        clearCell_(cell);
        cleared++;
      }
    }
  }
  return cleared ? done_(cleared + ' numbers cleared') : skipped_('No numbers to clear.');
}

/** The Individual updates table and its column indexes. */
function individualUpdates_(ctx) {
  var table = findTable_(ctx.body, ['Person', 'Upcoming OOO'], 'Individual updates');
  var headers = headerTexts_(table);
  return { table: table, personCol: colIndex_(headers, 'Person'), oooCol: colIndex_(headers, 'Upcoming OOO') };
}

function isAddAnyoneRow_(row, personCol) {
  return row.getCell(personCol).getText().trim().toLowerCase().indexOf('add anyone') === 0;
}

function stepOoo_(ctx) {
  var updates = individualUpdates_(ctx);
  var removed = [];
  var unsure = [];
  for (var r = 1; r < updates.table.getNumRows(); r++) {
    var row = updates.table.getRow(r);
    if (row.getNumCells() <= updates.oooCol) continue;
    var who = row.getCell(updates.personCol).getText().trim() || 'row ' + r;
    var cell = row.getCell(updates.oooCol);
    for (var i = cell.getNumChildren() - 1; i >= 0; i--) {
      var el = cell.getChild(i);
      if (!isParagraphLike_(el)) continue;
      var text = textOf_(el).trim();
      var kind = classifyOooElement_(el, text, ctx.meetingDate);
      // Date chips are not part of getText(), so name them by their dates.
      var label = '"' + [text].concat(chipDates_(el)).filter(String).join(' ') + '" (' + who + ')';
      if (kind === 'past') {
        removed.push(label);
        if (cell.getNumChildren() > 1) el.removeFromParent();
        else el.clear();
      } else if (kind === 'unparseable') {
        unsure.push(label);
      }
    }
  }
  var detail = removed.length ? 'Removed ' + removed.length + ': ' + removed.join('; ') + '.' : 'Nothing past to remove.';
  if (unsure.length) return warn_(detail + ' Check by hand, dates unclear: ' + unsure.join('; ') + '.');
  return done_(detail);
}

/** ISO dates of the date chips in a paragraph or list item. */
function chipDates_(el) {
  var types = DocumentApp.ElementType;
  var out = [];
  for (var i = 0; types.DATE && i < el.getNumChildren(); i++) {
    var child = el.getChild(i);
    if (child.getType() === types.DATE) out.push(Utilities.formatDate(child.asDate().getTimestamp(), 'UTC', 'yyyy-MM-dd'));
  }
  return out;
}

/** Date chips win over text; otherwise classify the text (see Dates.gs). */
function classifyOooElement_(el, text, meetingDate) {
  var end = chipDates_(el).sort().pop();
  if (end) return end < meetingDate ? 'past' : 'upcoming';
  return classifyOoo(text, meetingDate);
}

/**
 * Apps Script can't create checklists or read whether a box is checked, so checkboxes are re-created through the
 * Docs API (advanced service), which can. DocumentApp tags the paragraphs with named ranges, then one API batch:
 * - Individual updates cells: each checklist cell is replaced by one new paragraph (holding a zero-width
 *   placeholder so its range is non-empty) that becomes a new BULLET_CHECKBOX item; the placeholder is deleted.
 * - "Start recording": the existing item keeps its text and formatting; its bullet is removed and re-created as a
 *   new, unchecked checkbox.
 */
function stepCheckboxes_(ctx) {
  var docTab = ctx.tab.asDocumentTab();
  [CHECKBOX_RANGE_NAME, RECHECK_RANGE_NAME].forEach(function (name) {
    docTab.getNamedRanges(name).forEach(function (nr) { nr.remove(); }); // leftovers from a failed run
  });
  var tag = function (name, element) {
    docTab.addNamedRange(name, docTab.newRange().addElement(element).build());
  };

  var updates = individualUpdates_(ctx);
  var cells = 0;
  for (var r = 1; r < updates.table.getNumRows(); r++) {
    var row = updates.table.getRow(r);
    if (isAddAnyoneRow_(row, updates.personCol)) continue;
    // The checklist columns sit between Person and Upcoming OOO.
    for (var c = updates.personCol + 1; c < updates.oooCol && c < row.getNumCells(); c++) {
      var cell = row.getCell(c);
      var paragraph = cell.insertParagraph(0, ZERO_WIDTH_PLACEHOLDER);
      for (var i = cell.getNumChildren() - 1; i > 0; i--) cell.getChild(i).removeFromParent();
      tag(CHECKBOX_RANGE_NAME, paragraph);
      cells++;
    }
  }
  var recording = findParagraphStartingWith_(ctx.body, 'Start recording');
  if (recording) tag(RECHECK_RANGE_NAME, recording);

  var docId = ctx.doc.getId();
  var tabId = ctx.tab.getId();
  ctx.doc.saveAndClose(); // flush DocumentApp edits before the Docs API reads indices; no DocumentApp calls after this

  var tagged = namedRangeIndexes_(docId, tabId, [CHECKBOX_RANGE_NAME, RECHECK_RANGE_NAME]); // one read: ~16s each
  var freshRanges = tagged[CHECKBOX_RANGE_NAME];
  var recheck = tagged[RECHECK_RANGE_NAME];
  if (freshRanges.length !== cells) {
    // Checked before writing, so the API batch changes nothing; the placeholders are invisible.
    throw new StepError('Prepared ' + cells + ' checkbox cells but the Docs API found ' + freshRanges.length + '; no checkboxes were created.');
  }

  var ops = [];
  freshRanges.forEach(function (rg) {
    ops.push({ at: rg.startIndex, requests: [
      { createParagraphBullets: { range: range_(tabId, rg.startIndex, rg.startIndex + 1), bulletPreset: 'BULLET_CHECKBOX' } },
      { deleteContentRange: { range: range_(tabId, rg.startIndex, rg.startIndex + 1) } },
    ] });
  });
  recheck.forEach(function (rg) {
    var range = range_(tabId, rg.startIndex, Math.max(rg.endIndex, rg.startIndex + 1));
    ops.push({ at: rg.startIndex, requests: [
      { deleteParagraphBullets: { range: range } },
      { createParagraphBullets: { range: range, bulletPreset: 'BULLET_CHECKBOX' } },
    ] });
  });
  var requests = [];
  ops
    .sort(function (a, b) { return b.at - a.at; }) // bottom-up so each deletion can't shift ranges still to come
    .forEach(function (op) { requests = requests.concat(op.requests); });
  [CHECKBOX_RANGE_NAME, RECHECK_RANGE_NAME].forEach(function (name) {
    requests.push({ deleteNamedRange: { name: name, tabsCriteria: { tabIds: [tabId] } } });
  });
  Docs.Documents.batchUpdate({ requests: requests }, docId);

  return done_(cells + ' checkboxes reset' + (recheck.length ? ', plus "Start recording"' : ' ("Start recording" not found)'));
}

function range_(tabId, startIndex, endIndex) {
  return { tabId: tabId, startIndex: startIndex, endIndex: endIndex };
}

/**
 * Start/end indexes (Docs API) of every range in each of the named ranges `names` on one tab (tabs nested up to 3
 * deep), as { name: [{ startIndex, endIndex }] }. One documents.get, since each one loads the whole document.
 */
function namedRangeIndexes_(docId, tabId, names) {
  var tabFields = 'tabProperties(tabId),documentTab(namedRanges)';
  var resp = Docs.Documents.get(docId, {
    includeTabsContent: true,
    fields: 'tabs(' + tabFields + ',childTabs(' + tabFields + ',childTabs(' + tabFields + ')))',
  });
  var found = null;
  (function walk(tabs) {
    (tabs || []).forEach(function (t) {
      if (t.tabProperties.tabId === tabId) found = t;
      walk(t.childTabs);
    });
  })(resp.tabs);
  var all = (found && found.documentTab.namedRanges) || {};
  var out = {};
  names.forEach(function (name) {
    out[name] = [];
    ((all[name] && all[name].namedRanges) || []).forEach(function (nr) {
      nr.ranges.forEach(function (rg) { out[name].push({ startIndex: rg.startIndex || 0, endIndex: rg.endIndex || 0 }); });
    });
  });
  return out;
}

function stepRecording_(ctx) {
  var heading = findHeading_(ctx.body, 'Recording', true);
  var els = sectionElements_(heading, headingLevel_(heading));
  ctx.body.insertParagraph(ctx.body.getChildIndex(heading) + 1, '');
  for (var i = els.length - 1; i >= 0; i--) removeOrClear_(els[i]);
  return els.length ? done_() : done_('Was already empty.');
}

function stepAiNotes_(ctx) {
  var heading = findHeading_(ctx.body, 'AI Meeting Notes');
  var els = sectionElements_(heading, headingLevel_(heading));
  if (!els.length) return skipped_('Nothing under "AI Meeting Notes" to clear.');
  ctx.body.insertParagraph(ctx.body.getChildIndex(heading) + 1, '');
  for (var i = els.length - 1; i >= 0; i--) removeOrClear_(els[i]);
  return done_(els.length + ' paragraphs and tables removed');
}

/**
 * Docs variable values can't be set through any API: writing a chip's text only changes that one instance and
 * leaves the variable's value behind (tested 2026-11-09). So this step tells the person exactly what to set.
 */
function stepDateVariables_(ctx) {
  var titles = allTabs_(ctx.doc).map(function (t) { return t.getTitle(); });
  var v = dateVariableValues(ctx.meetingDate, previousMeetingDate(titles, ctx.meetingDate));
  return skipped_(
    'Set these by hand: click any date in this tab, choose ↗ to open Variables, and edit each value. ' +
      'lastWeekReportDate = ' + (v.lastWeekReportDate || '(no earlier dated tab found)') +
      ', thisWeekReportDate = ' + v.thisWeekReportDate +
      ', nextWeekReportDate = ' + v.nextWeekReportDate + '.'
  );
}
