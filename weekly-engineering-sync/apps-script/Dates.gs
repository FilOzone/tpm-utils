/**
 * Pure date logic for "Prepare for next meeting": no Apps Script services, so test/Dates.test.js runs it in Node.
 *
 * Source of truth is GitHub (https://github.com/FilOzone/tpm-utils/tree/master/weekly-engineering-sync/apps-script).
 * Edits made in the Apps Script editor are overwritten by the next `clasp push`.
 *
 * Dates are ISO strings ("2026-11-10") and arithmetic is done in UTC so time zones never shift a day.
 * Top-level declarations are `function`/`var` (not `const`) so the Node test sandbox can see them.
 */

var ISO_DATE_RE = /^(\d{4})-(\d{2})-(\d{2})$/;

var MONTHS = {
  jan: 1, january: 1, feb: 2, february: 2, mar: 3, march: 3, apr: 4, april: 4, may: 5, jun: 6, june: 6,
  jul: 7, july: 7, aug: 8, august: 8, sep: 9, sept: 9, september: 9, oct: 10, october: 10,
  nov: 11, november: 11, dec: 12, december: 12,
};

/** Return the ISO date if `title` is exactly a valid YYYY-MM-DD date, else null. */
function parseMeetingDate(title) {
  var m = ISO_DATE_RE.exec(String(title).trim());
  if (!m) return null;
  return isoIfValid_(+m[1], +m[2], +m[3]);
}

function isoIfValid_(y, mo, d) {
  var t = new Date(Date.UTC(y, mo - 1, d));
  if (t.getUTCFullYear() !== y || t.getUTCMonth() !== mo - 1 || t.getUTCDate() !== d) return null;
  return t.toISOString().slice(0, 10);
}

function addDays(iso, days) {
  var t = new Date(iso + 'T00:00:00Z');
  t.setUTCDate(t.getUTCDate() + days);
  return t.toISOString().slice(0, 10);
}

function daysBetween_(a, b) {
  return Math.abs(new Date(a + 'T00:00:00Z') - new Date(b + 'T00:00:00Z')) / 86400000;
}

/**
 * The latest meeting date before `meetingDate` among tab titles that start with a date
 * ("2026-04-07 (async)" counts). Returns null if there is none.
 */
function previousMeetingDate(titles, meetingDate) {
  var best = null;
  titles.forEach(function (title) {
    var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(title).trim());
    var iso = m && isoIfValid_(+m[1], +m[2], +m[3]);
    if (iso && iso < meetingDate && (!best || iso > best)) best = iso;
  });
  return best;
}

/** Values for the doc's date variables. `previousDate` may be null when no earlier meeting tab exists. */
function dateVariableValues(meetingDate, previousDate) {
  return {
    lastWeekReportDate: previousDate,
    thisWeekReportDate: meetingDate,
    nextWeekReportDate: addDays(meetingDate, 7),
  };
}

/**
 * Best-effort end date of a free-text OOO entry such as "Nov 23-27 (Thanksgiving)", "8th december" or
 * "29 Dec - 2 Jan". Returns the latest date mentioned, or null when any part is ambiguous.
 *
 * Day numbers bind to a month by the entry's style: month-first text ("Nov 30 - Dec 2") binds a day to the month
 * before it; day-first text ("29 Dec - 2 Jan", "8-10 december") binds a day to the month after it. Without an
 * explicit year, each date takes the year that puts it nearest the meeting.
 */
function parseOooEndDate(text, meetingDate) {
  var lower = String(text).toLowerCase();
  var explicit = []; // ISO dates found verbatim
  var invalid = false;

  // ISO dates are unambiguous: take them first and blank them out so their digits are not re-read as days.
  lower = lower.replace(/\b(\d{4})-(\d{1,2})-(\d{1,2})\b/g, function (_, y, mo, d) {
    var iso = isoIfValid_(+y, +mo, +d);
    if (iso) explicit.push(iso);
    else invalid = true;
    return ' ';
  });
  if (invalid) return null;

  // "may" is only the month when a day number sits right next to it ("May 4", "4th of May"); otherwise it is the
  // verb ("I may be out"), and reading it as a month could delete an entry that is not past.
  lower = lower.replace(/\bmay\b/g, function (word, offset, whole) {
    var after = whole.slice(offset + word.length);
    var before = whole.slice(0, offset);
    var nearDay = /^[\s.\-]*\d/.test(after) || /\d(?:st|nd|rd|th)?(?:\s+of)?[\s.\-]*$/.test(before);
    return nearDay ? word : ' ';
  });

  // Tokens: 4-digit years, 1-2 digit days (optional ordinal suffix), and words. "11/23" yields two bare numbers
  // with no month, so it is rejected as ambiguous.
  var tokenRe = /(\d{4})|(\d{1,2})(?:st|nd|rd|th)?(?!\d)|([a-z]+)/g;
  var tokens = [];
  var year = null;
  var m;
  while ((m = tokenRe.exec(lower))) {
    if (m[1]) year = +m[1];
    else if (m[2]) tokens.push({ day: +m[2] });
    else if (MONTHS[m[3]]) tokens.push({ month: MONTHS[m[3]] });
  }
  var end = latestMention_(tokens, year, meetingDate);
  if (end === false) return null;
  explicit.forEach(function (iso) {
    if (!end || iso > end) end = iso;
  });
  // "week of July 6" means the whole week, so it is not past until that week is over.
  if (end && /\bweek of\b/.test(lower)) end = addDays(end, 6);
  return end;
}

/** Latest date named by month/day tokens, null if none, or false if some day number cannot be placed. */
function latestMention_(tokens, year, meetingDate) {
  if (!tokens.length) return null;

  var dayFirst = tokens[0].day !== undefined;
  var mentions = [];
  var pending = [];
  var current = null;
  tokens.forEach(function (t) {
    if (t.month) {
      pending.forEach(function (d) { mentions.push([t.month, d]); });
      pending = [];
      current = t.month;
    } else if (dayFirst || !current) {
      pending.push(t.day);
    } else {
      mentions.push([current, t.day]);
    }
  });
  if (pending.length) {
    if (!current) return false; // days with no month at all
    pending.forEach(function (d) { mentions.push([current, d]); });
  }

  var meetingYear = +meetingDate.slice(0, 4);
  var end = null;
  for (var i = 0; i < mentions.length; i++) {
    var mo = mentions[i][0];
    var d = mentions[i][1];
    var iso = null;
    if (year) {
      iso = isoIfValid_(year, mo, d);
    } else {
      [meetingYear - 1, meetingYear, meetingYear + 1].forEach(function (y) {
        var c = isoIfValid_(y, mo, d);
        if (c && (!iso || daysBetween_(c, meetingDate) < daysBetween_(iso, meetingDate))) iso = c;
      });
    }
    if (!iso) return false;
    if (!end || iso > end) end = iso;
  }
  return end;
}

/**
 * Classify one OOO entry against the meeting date:
 * "past" (ended before the meeting), "upcoming", "unparseable" (looks like a date but is ambiguous; keep it and
 * ask a human), or "none" (empty or no date-like content, such as "None").
 */
function classifyOoo(text, meetingDate) {
  var trimmed = String(text).trim();
  if (!trimmed) return 'none';
  var end = parseOooEndDate(trimmed, meetingDate);
  if (end) return end < meetingDate ? 'past' : 'upcoming';
  var words = trimmed.toLowerCase().match(/[a-z]+/g) || [];
  var looksDated = /\d/.test(trimmed) || words.some(function (w) { return MONTHS[w]; });
  return looksDated ? 'unparseable' : 'none';
}
