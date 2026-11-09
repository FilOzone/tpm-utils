/**
 * Generic DocumentApp helpers used by the prepare steps: find tables by header text, find sections by heading text,
 * and clear or copy table cells while keeping their formatting.
 *
 * Source of truth is GitHub (https://github.com/FilOzone/tpm-utils/tree/master/weekly-engineering-sync/apps-script).
 * Edits made in the Apps Script editor are overwritten by the next `clasp push`.
 */

/** Thrown for problems a person can fix in the doc (a missing anchor); shown as the step's ❌ detail. */
function StepError(message) {
  var e = new Error(message);
  e.name = 'StepError';
  Object.setPrototypeOf(e, StepError.prototype);
  return e;
}
StepError.prototype = Object.create(Error.prototype);
StepError.prototype.constructor = StepError;

var WHITE = '#ffffff';

function headerTexts_(table) {
  var row = table.getRow(0);
  var out = [];
  for (var c = 0; c < row.getNumCells(); c++) out.push(row.getCell(c).getText().trim());
  return out;
}

/** Index of the first header that contains `needle` (case-insensitive), or -1. */
function colIndex_(headers, needle) {
  var n = needle.toLowerCase();
  for (var i = 0; i < headers.length; i++) if (headers[i].toLowerCase().indexOf(n) >= 0) return i;
  return -1;
}

/** Tables whose header row contains every string in `needles`. */
function findTables_(body, needles) {
  return body.getTables().filter(function (t) {
    var h = headerTexts_(t);
    return needles.every(function (n) { return colIndex_(h, n) >= 0; });
  });
}

/** Exactly one table whose header row contains every string in `needles`; StepError otherwise. */
function findTable_(body, needles, name) {
  var hits = findTables_(body, needles);
  var anchor = needles.map(function (n) { return '"' + n + '"'; }).join(' and ');
  if (hits.length === 0) throw new StepError('Could not find the ' + name + ' table (looked for a header row containing ' + anchor + ').');
  if (hits.length > 1) throw new StepError('Found ' + hits.length + ' ' + name + ' tables (header row containing ' + anchor + '); expected one.');
  return hits[0];
}

function isParagraphLike_(el) {
  var t = el.getType();
  return t === DocumentApp.ElementType.PARAGRAPH || t === DocumentApp.ElementType.LIST_ITEM;
}

/** Heading level of a body element: 1-6 for headings, 0 for title/subtitle, Infinity for anything else. */
function headingLevel_(el) {
  if (el.getType() !== DocumentApp.ElementType.PARAGRAPH) return Infinity;
  var H = DocumentApp.ParagraphHeading;
  var levels = [H.TITLE, H.SUBTITLE, H.HEADING1, H.HEADING2, H.HEADING3, H.HEADING4, H.HEADING5, H.HEADING6];
  var i = levels.indexOf(el.asParagraph().getHeading());
  if (i < 0) return Infinity;
  return i < 2 ? 0 : i - 1;
}

/**
 * First top-level heading whose text contains `needle` (case-insensitive), or equals it when `exact` is set;
 * StepError if none.
 */
function findHeading_(body, needle, exact) {
  var n = needle.toLowerCase();
  for (var i = 0; i < body.getNumChildren(); i++) {
    var el = body.getChild(i);
    if (headingLevel_(el) === Infinity) continue;
    var text = el.asParagraph().getText().trim().toLowerCase();
    if (exact ? text === n : text.indexOf(n) >= 0) return el.asParagraph();
  }
  throw new StepError('Could not find the "' + needle + '" heading.');
}

/** Text of a paragraph or list item. */
function textOf_(el) {
  return el.editAsText().getText();
}

/** First top-level paragraph or list item whose text starts with `prefix` (case-insensitive), or null. */
function findParagraphStartingWith_(body, prefix) {
  var p = prefix.toLowerCase();
  for (var i = 0; i < body.getNumChildren(); i++) {
    var el = body.getChild(i);
    if (isParagraphLike_(el) && textOf_(el).trim().toLowerCase().indexOf(p) === 0) return el;
  }
  return null;
}

/** Body elements after `start` up to (not including) the first heading at `maxLevel` or higher. */
function sectionElements_(start, maxLevel) {
  var out = [];
  for (var el = start.getNextSibling(); el; el = el.getNextSibling()) {
    if (headingLevel_(el) <= maxLevel) break;
    out.push(el);
  }
  return out;
}

/** Remove an element, or clear it when it is the last element of its container (which Docs cannot remove). */
function removeOrClear_(el) {
  if (!el.getNextSibling() && isParagraphLike_(el)) {
    el.clear();
  } else {
    el.removeFromParent();
  }
}

/**
 * Remove every element in `els` (bullets, images, stray paragraphs) except `keep`, and leave exactly one empty,
 * top-level bullet: the first list item, emptied, or a new one inserted after `after` when there was none.
 */
function leaveOneEmptyBullet_(body, els, keep, after) {
  var bullet = null;
  els.forEach(function (el) {
    if (!bullet && el.getType() === DocumentApp.ElementType.LIST_ITEM) bullet = el.asListItem();
  });
  for (var i = els.length - 1; i >= 0; i--) {
    if (els[i] !== keep && els[i] !== bullet) els[i].removeFromParent();
  }
  if (bullet) {
    bullet.clear();
    bullet.setNestingLevel(0);
  } else {
    body.insertListItem(body.getChildIndex(keep || after) + 1, '');
  }
}

/** Empty a table cell, keeping its first paragraph (and its bullet, if any) so the cell keeps its shape. */
function clearCell_(cell) {
  if (!isParagraphLike_(cell.getChild(0))) cell.insertParagraph(0, '');
  for (var i = cell.getNumChildren() - 1; i > 0; i--) cell.getChild(i).removeFromParent();
  var first = cell.getChild(0);
  first.clear();
  if (first.getType() === DocumentApp.ElementType.LIST_ITEM) first.asListItem().setNestingLevel(0);
}

/** Replace `dst`'s contents with copies of `src`'s, keeping bullets, links and formatting. */
function replaceCellWithCopy_(dst, src) {
  var oldCount = dst.getNumChildren();
  var E = DocumentApp.ElementType;
  var copied = 0;
  for (var i = 0; i < src.getNumChildren(); i++) {
    var c = src.getChild(i).copy();
    var t = c.getType();
    if (t === E.PARAGRAPH) dst.appendParagraph(c);
    else if (t === E.LIST_ITEM) dst.appendListItem(c);
    else if (t === E.TABLE) dst.appendTable(c);
    else continue;
    copied++;
  }
  if (!copied) dst.appendParagraph('');
  for (var j = oldCount - 1; j >= 0; j--) dst.getChild(j).removeFromParent();
}

/** Clear the text of every data row (all rows after the header) and reset those cells to white. Returns rows cleared. */
function clearTableRows_(table) {
  for (var r = 1; r < table.getNumRows(); r++) {
    var row = table.getRow(r);
    for (var c = 0; c < row.getNumCells(); c++) {
      clearCell_(row.getCell(c));
      row.getCell(c).setBackgroundColor(WHITE);
    }
  }
  return table.getNumRows() - 1;
}
