/**
 * 🗄️ FOC → Prepare for next meeting: turns a freshly duplicated Meeting tab (renamed to the meeting date,
 * YYYY-MM-DD) into a blank agenda, carrying last meeting's plans into the Expected column.
 *
 * Flow: the menu item checks preconditions and asks for confirmation, then opens Sidebar.html, which calls
 * runPrepStep() once per step so each ✅/⏭️/⚠️/❌ appears live. Steps are independent; one failing does not stop
 * the rest. Design and decisions: ../README.md and ../GLOSSARY.md.
 *
 * Source of truth is GitHub (https://github.com/FilOzone/tpm-utils/tree/master/weekly-engineering-sync/apps-script).
 * Edits made in the Apps Script editor are overwritten by the next `clasp push`.
 */

var EXPECTED_YELLOW = '#ffffa6';
var CHECKBOX_RANGE_NAME = 'foc-prep-checkbox';
var PREPARED_KEY_PREFIX = 'prepared:';

var PREP_STEPS = [
  { id: 'workstreams', label: 'Workstream tables: plan → Expected (yellow); clear plan and actual' },
  { id: 'syncTopics', label: 'Clear the Sync topics table' },
  { id: 'groupSnaps', label: 'Clear Group Snaps' },
  { id: 'topSpNeeds', label: 'Clear Top SP needs' },
  { id: 'spStatus', label: 'Clear the SP status numbers' },
  { id: 'opsEvents', label: 'Clear Summary of operational events' },
  { id: 'ooo', label: 'Remove past Upcoming OOO entries' },
  { id: 'checkboxes', label: 'Reset checkboxes (Individual updates, Start recording)' },
  { id: 'reviewStats', label: 'Clear FOC review stats' },
  { id: 'recording', label: 'Clear the Recording link' },
  { id: 'aiNotes', label: 'Clear AI Meeting Notes' },
  { id: 'dateVariables', label: 'Date variables' },
];

var STEP_HANDLERS = {
  workstreams: stepWorkstreams_,
  syncTopics: function (ctx) { return clearNamedTable_(ctx, ['Sync Topic'], 'Sync topics'); },
  groupSnaps: stepGroupSnaps_,
  topSpNeeds: stepTopSpNeeds_,
  spStatus: stepSpStatus_,
  opsEvents: function (ctx) { return clearNamedTable_(ctx, ['Date/window'], 'Summary of operational events'); },
  ooo: stepOoo_,
  checkboxes: stepCheckboxes_,
  reviewStats: function (ctx) { return clearNamedTable_(ctx, ['Contributor', 'Rev/PR'], 'FOC review stats'); },
  recording: stepRecording_,
  aiNotes: stepAiNotes_,
  dateVariables: stepDateVariables_,
};

function done_(detail) { return { status: 'done', detail: detail || '' }; }
function warn_(detail) { return { status: 'warn', detail: detail }; }
function skipped_(detail) { return { status: 'skipped', detail: detail }; }

// ---------------------------------------------------------------- menu entry point

function prepareForNextMeeting() {
  var ui = DocumentApp.getUi();
  var doc = DocumentApp.getActiveDocument();
  var tab = doc.getActiveTab();
  var title = tab.getTitle().trim();
  var problem = preconditionProblem_(doc, tab);
  if (problem) {
    ui.alert('Prepare for next meeting', problem, ui.ButtonSet.OK);
    return;
  }
  var meetingDate = parseMeetingDate(title);
  var answer = ui.alert(
    'Prepare for next meeting (v' + SCRIPT_VERSION + ')',
    'Prepare tab "' + title + '" for the meeting on ' + meetingDate + '?\n\n' +
      'This only changes this tab. It carries each workstream\'s plan into the Expected column and clears last ' +
      'meeting\'s content (sync topics, snaps, SP status, operational events, past OOO, checkboxes, review stats, ' +
      'recording and AI notes).\n\nIt can run once per tab. To undo, use File → Version history.',
    ui.ButtonSet.YES_NO
  );
  if (answer !== ui.Button.YES) return;

  // Mark before running so a second run can't shift plan → Expected twice, even if this run fails partway.
  PropertiesService.getDocumentProperties().setProperty(PREPARED_KEY_PREFIX + tab.getId(), new Date().toISOString());

  var template = HtmlService.createTemplateFromFile('Sidebar');
  template.payload = JSON.stringify({
    tabId: tab.getId(),
    title: title,
    meetingDate: meetingDate,
    version: SCRIPT_VERSION,
    steps: PREP_STEPS,
    sourceUrl: SOURCE_URL,
    issuesUrl: ISSUES_URL,
  }).replace(/</g, '\\u003c');
  ui.showSidebar(template.evaluate().setTitle('Prepare for next meeting'));
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

// ---------------------------------------------------------------- sidebar entry point

/** Called by the sidebar once per step. Never throws: failures come back as { status: 'failed' }. */
function runPrepStep(stepId, tabId) {
  try {
    var handler = STEP_HANDLERS[stepId];
    if (!handler) throw new StepError('Unknown step "' + stepId + '".');
    var doc = DocumentApp.getActiveDocument();
    var tab = doc.getTab(tabId);
    if (!tab) throw new StepError('The tab being prepared no longer exists.');
    var ctx = {
      doc: doc,
      tab: tab,
      body: tab.asDocumentTab().getBody(),
      meetingDate: parseMeetingDate(tab.getTitle()),
    };
    if (!ctx.meetingDate) throw new StepError('The tab title is no longer a YYYY-MM-DD date.');
    return handler(ctx);
  } catch (e) {
    return { status: 'failed', detail: (e && e.message) || String(e) };
  }
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
    var h = headerTexts_(table);
    var expected = colIndex_(h, needles[0]);
    var actual = colIndex_(h, needles[1]);
    var plan = colIndex_(h, needles[2]);
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
  var items = sectionElements_(heading, 6).filter(function (el) {
    return el.getType() === DocumentApp.ElementType.LIST_ITEM;
  });
  if (!items.length) return skipped_('No snaps to clear.');
  var removed = collapseListToOneEmptyItem_(items);
  return done_((removed + 1) + ' snaps cleared');
}

function stepTopSpNeeds_(ctx) {
  var label = findParagraphStartingWith_(ctx.body, 'Top SP needs');
  if (!label) throw new StepError('Could not find the "Top SP needs:" line.');
  var items = [];
  for (var el = label.getNextSibling(); el && el.getType() === DocumentApp.ElementType.LIST_ITEM; el = el.getNextSibling()) {
    items.push(el.asListItem());
  }
  if (!items.length) return skipped_('No bullets under "Top SP needs:".');
  collapseListToOneEmptyItem_(items);
  return done_(items.length + ' bullets cleared');
}

function stepSpStatus_(ctx) {
  var table = findTable_(ctx.body, ['Mainnet', 'Calibration'], 'SP status');
  // Only cells that hold nothing but a number are cleared, so labels, ✔️/❌ headers and the chart image stay.
  var cleared = 0;
  for (var r = 1; r < table.getNumRows(); r++) {
    var row = table.getRow(r);
    for (var c = 1; c < row.getNumCells(); c++) {
      var cell = row.getCell(c);
      if (/^\s*\d[\d,.\s]*$/.test(cell.getText())) {
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
  var h = headerTexts_(table);
  return { table: table, person: colIndex_(h, 'Person'), ooo: colIndex_(h, 'Upcoming OOO') };
}

function isAddAnyoneRow_(row, personCol) {
  return row.getCell(personCol).getText().trim().toLowerCase().indexOf('add anyone') === 0;
}

function stepOoo_(ctx) {
  var iu = individualUpdates_(ctx);
  var removed = [];
  var unsure = [];
  for (var r = 1; r < iu.table.getNumRows(); r++) {
    var row = iu.table.getRow(r);
    if (row.getNumCells() <= iu.ooo) continue;
    var who = row.getCell(iu.person).getText().trim() || 'row ' + r;
    var cell = row.getCell(iu.ooo);
    for (var i = cell.getNumChildren() - 1; i >= 0; i--) {
      var el = cell.getChild(i);
      if (!isParagraphLike_(el)) continue;
      var text = el.asText().getText().trim();
      var kind = classifyOooElement_(el, text, ctx.meetingDate);
      if (kind === 'past') {
        removed.push('"' + text + '" (' + who + ')');
        if (cell.getNumChildren() > 1) el.removeFromParent();
        else el.clear();
      } else if (kind === 'unparseable') {
        unsure.push('"' + text + '" (' + who + ')');
      }
    }
  }
  var detail = removed.length ? 'Removed ' + removed.length + ': ' + removed.join('; ') + '.' : 'Nothing past to remove.';
  if (unsure.length) return warn_(detail + ' Check by hand, dates unclear: ' + unsure.join('; ') + '.');
  return done_(detail);
}

/** Date chips win over text; otherwise classify the text (see Dates.gs). */
function classifyOooElement_(el, text, meetingDate) {
  var E = DocumentApp.ElementType;
  var end = null;
  for (var i = 0; E.DATE && i < el.getNumChildren(); i++) {
    var child = el.getChild(i);
    if (child.getType() === E.DATE) {
      var iso = Utilities.formatDate(child.asDate().getTimestamp(), 'UTC', 'yyyy-MM-dd');
      if (!end || iso > end) end = iso;
    }
  }
  if (end) return end < meetingDate ? 'past' : 'upcoming';
  return classifyOoo(text, meetingDate);
}

/**
 * Apps Script can't create checklist bullets or read whether a box is checked, so each checklist paragraph is
 * replaced by a fresh one, tagged with a named range, and the Docs API turns the tagged paragraphs into new,
 * unchecked BULLET_CHECKBOX lists. A zero-width placeholder character keeps each tagged range non-empty and is
 * deleted in the same API batch.
 */
function stepCheckboxes_(ctx) {
  var dt = ctx.tab.asDocumentTab();
  dt.getNamedRanges(CHECKBOX_RANGE_NAME).forEach(function (nr) { nr.remove(); }); // leftovers from a failed run
  var tagged = 0;
  var tag = function (paragraph) {
    dt.addNamedRange(CHECKBOX_RANGE_NAME, dt.newRange().addElement(paragraph).build());
    tagged++;
  };

  var iu = individualUpdates_(ctx);
  for (var r = 1; r < iu.table.getNumRows(); r++) {
    var row = iu.table.getRow(r);
    if (isAddAnyoneRow_(row, iu.person)) continue;
    for (var c = iu.person + 1; c < iu.ooo && c < row.getNumCells(); c++) {
      var cell = row.getCell(c);
      var p = cell.insertParagraph(0, '​');
      for (var i = cell.getNumChildren() - 1; i > 0; i--) cell.getChild(i).removeFromParent();
      tag(p);
    }
  }

  var recording = findParagraphStartingWith_(ctx.body, 'Start recording');
  if (recording) {
    var idx = ctx.body.getChildIndex(recording);
    var replacement = ctx.body.insertParagraph(idx, '​' + recording.asText().getText().trim());
    recording.removeFromParent();
    tag(replacement);
  }

  var docId = ctx.doc.getId();
  var tabId = ctx.tab.getId();
  ctx.doc.saveAndClose(); // flush DocumentApp edits before the Docs API reads indices; no DocumentApp calls after this
  var ranges = namedRangeIndexes_(docId, tabId, CHECKBOX_RANGE_NAME);
  var requests = [];
  ranges
    .sort(function (a, b) { return b.startIndex - a.startIndex; }) // bottom-up so deletions don't shift later ranges
    .forEach(function (rg) {
      var range = { tabId: tabId, startIndex: rg.startIndex, endIndex: Math.max(rg.endIndex, rg.startIndex + 1) };
      requests.push({ createParagraphBullets: { range: range, bulletPreset: 'BULLET_CHECKBOX' } });
      requests.push({ deleteContentRange: { range: { tabId: tabId, startIndex: rg.startIndex, endIndex: rg.startIndex + 1 } } });
    });
  requests.push({ deleteNamedRange: { name: CHECKBOX_RANGE_NAME, tabsCriteria: { tabIds: [tabId] } } });
  Docs.Documents.batchUpdate({ requests: requests }, docId);

  if (ranges.length !== tagged) throw new StepError('Tagged ' + tagged + ' checkboxes but the API found ' + ranges.length + '.');
  return done_(tagged + ' checkboxes reset' + (recording ? ', including "Start recording"' : ' ("Start recording" not found)'));
}

/** Start/end indexes (Docs API) of every range in the named range `name` on one tab. */
function namedRangeIndexes_(docId, tabId, name) {
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
  var group = found && found.documentTab.namedRanges && found.documentTab.namedRanges[name];
  var out = [];
  ((group && group.namedRanges) || []).forEach(function (nr) {
    nr.ranges.forEach(function (rg) { out.push({ startIndex: rg.startIndex || 0, endIndex: rg.endIndex || 0 }); });
  });
  return out;
}

function stepRecording_(ctx) {
  var heading = findHeading_(ctx.body, 'Recording');
  var els = sectionElements_(heading, headingLevel_(heading));
  if (!els.length) {
    ctx.body.insertParagraph(ctx.body.getChildIndex(heading) + 1, '');
    return skipped_('Nothing under "Recording" to clear.');
  }
  for (var i = els.length - 1; i > 0; i--) removeOrClear_(els[i]);
  if (isParagraphLike_(els[0])) els[0].clear();
  else {
    ctx.body.insertParagraph(ctx.body.getChildIndex(els[0]), '');
    els[0].removeFromParent();
  }
  return done_();
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
