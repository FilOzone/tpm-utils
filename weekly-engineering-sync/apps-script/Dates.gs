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

// Month names, longest first so "sept" wins over "sep" in a regex alternation.
var MONTH_ALT = Object.keys(MONTHS).sort(function (a, b) { return b.length - a.length; }).join('|');
// One day number, or several joined by a hyphen, en or em dash, slash or & ("23-27", "7/8th"), with optional ordinal suffixes.
var DAYS_RE = '(\\d{1,2}(?:st|nd|rd|th)?(?:\\s*[-\\u2013\\u2014/&]\\s*\\d{1,2}(?:st|nd|rd|th)?)*)(?!\\d)';
var YEAR_RE = '(?:,?\\s*(\\d{4}))?(?!\\d)';
// "Nov 9", "Dec-9", "Nov 23-27", "January 5, 2027".
var MONTH_FIRST_RE = new RegExp('\\b(' + MONTH_ALT + ')\\b\\.?\\s*[-.]?\\s*' + DAYS_RE + YEAR_RE, 'g');
// "8th december", "29 Dec 2026", "8-10 december", "4th of May".
var DAY_FIRST_RE = new RegExp('(?<!\\d)' + DAYS_RE + '(?:\\s+of)?\\s*[-.]?\\s*\\b(' + MONTH_ALT + ')\\b\\.?' + YEAR_RE, 'g');

/**
 * Best-effort end date of a free-text OOO entry such as "Nov 23-27 (Thanksgiving)", "8th december" or
 * "29 Dec - 2 Jan". Returns the latest date mentioned, or null when any part is ambiguous.
 *
 * Strict on purpose, because a wrong date deletes an entry that is not over: a number counts as a day only when it
 * sits next to a month name ("Nov 9", "23-27 Nov", "Dec 7/8th"), and a year only right after such a date. Any other
 * number ("out 2 weeks", "12/3", "until 2027") or a month without a day ("mid December") makes the whole entry
 * ambiguous. The entry's style picks how days bind: month-first text ("Nov 30 - Dec 2") or day-first text
 * ("29 Dec - 2 Jan"). A date without a year takes the year that puts it nearest the meeting.
 */
function parseOooEndDate(text, meetingDate) {
  var lower = String(text).toLowerCase();
  var dates = []; // ISO dates found
  var invalid = false;

  // ISO dates are unambiguous: take them first and blank them out so their digits are not re-read as days.
  lower = lower.replace(/\b(\d{4})-(\d{1,2})-(\d{1,2})\b/g, function (_, y, mo, d) {
    var iso = isoIfValid_(+y, +mo, +d);
    if (iso) dates.push(iso);
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

  // Day-first when a number comes before the first month name.
  var firstDigit = lower.search(/\d/);
  var firstMonth = lower.search(new RegExp('\\b(' + MONTH_ALT + ')\\b'));
  var dayFirst = firstDigit >= 0 && (firstMonth < 0 || firstDigit < firstMonth);
  var re = new RegExp(dayFirst ? DAY_FIRST_RE.source : MONTH_FIRST_RE.source, 'g');

  lower = lower.replace(re, function (_, a, b, year) {
    var days = dayFirst ? a : b;
    var month = MONTHS[dayFirst ? b : a];
    days.match(/\d{1,2}/g).forEach(function (d) {
      var iso = year ? isoIfValid_(+year, month, +d) : nearestYearIso_(month, +d, meetingDate);
      if (iso) dates.push(iso);
      else invalid = true;
    });
    return ' ';
  });
  // Leftover numbers or month names mean part of the entry was not understood.
  if (invalid || /\d/.test(lower) || new RegExp('\\b(' + MONTH_ALT + ')\\b').test(lower)) return null;
  if (!dates.length) return null;

  var end = dates.sort().pop();
  // "week of July 6" means the whole week, so it is not past until that week is over.
  if (/\bweek of\b/.test(lower)) end = addDays(end, 6);
  return end;
}

/** The ISO date for month/day in the year (meeting year ±1) nearest the meeting, or null if the day is invalid. */
function nearestYearIso_(month, day, meetingDate) {
  var meetingYear = +meetingDate.slice(0, 4);
  var best = null;
  [meetingYear - 1, meetingYear, meetingYear + 1].forEach(function (y) {
    var c = isoIfValid_(y, month, day);
    if (c && (!best || daysBetween_(c, meetingDate) < daysBetween_(best, meetingDate))) best = c;
  });
  return best;
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

/**
 * Like classifyOoo, for an entry that also holds date chips (ISO dates in `chipDates`; Docs leaves chips out of the
 * text). The entry ends at the latest date in the chips or the text; text with dates the parser can't read keeps the
 * entry ("unparseable"), and "week of <chip>" lasts the whole week.
 */
function classifyOooWithChips(text, chipDates, meetingDate) {
  if (!chipDates.length) return classifyOoo(text, meetingDate);
  var kind = classifyOoo(text, meetingDate);
  if (kind === 'unparseable') return kind;
  var ends = chipDates.slice();
  if (kind !== 'none') ends.push(parseOooEndDate(text, meetingDate));
  var end = ends.sort().pop();
  if (/\bweek of\b/i.test(String(text))) end = addDays(end, 6);
  return end < meetingDate ? 'past' : 'upcoming';
}
