// Offline tests for the pure date logic in Dates.gs. Run: node --test test/
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

// Apps Script files are plain scripts that define globals; load Dates.gs into a sandbox.
const ctx = {};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(path.join(__dirname, '..', 'Dates.gs'), 'utf8'), ctx);
const { parseMeetingDate, previousMeetingDate, addDays, dateVariableValues, parseOooEndDate, classifyOoo, classifyOooWithChips } = ctx;

test('parseMeetingDate accepts only a real YYYY-MM-DD title', () => {
  assert.equal(parseMeetingDate('2026-11-10'), '2026-11-10');
  assert.equal(parseMeetingDate(' 2026-11-10 '), '2026-11-10');
  assert.equal(parseMeetingDate('2026-02-30'), null);
  assert.equal(parseMeetingDate('2026-11-10 (async)'), null);
  assert.equal(parseMeetingDate('Copy of 2026-11-03'), null);
  assert.equal(parseMeetingDate('2026-11-3'), null);
});

test('addDays crosses month and year boundaries', () => {
  assert.equal(addDays('2026-11-10', 7), '2026-11-17');
  assert.equal(addDays('2026-12-29', 7), '2027-01-05');
  assert.equal(addDays('2026-03-01', -1), '2026-02-28');
});

test('previousMeetingDate picks the latest dated tab before this one, tolerating suffixes', () => {
  const titles = ['Meta', '2026-11-10', '2026-11-03', '2026-10-20', '2026-04-07 (async)', 'Copy of 2026-11-03'];
  assert.equal(previousMeetingDate(titles, '2026-11-10'), '2026-11-03');
  assert.equal(previousMeetingDate(titles, '2026-10-27'), '2026-10-20');
  assert.equal(previousMeetingDate(['Meta', '2026-11-10'], '2026-11-10'), null);
});

test('dateVariableValues handles a skipped week', () => {
  assert.deepEqual(
    { ...dateVariableValues('2026-11-10', '2026-11-03') },
    { lastWeekReportDate: '2026-11-03', thisWeekReportDate: '2026-11-10', nextWeekReportDate: '2026-11-17' }
  );
  assert.equal(dateVariableValues('2026-11-03', '2026-10-20').lastWeekReportDate, '2026-10-20');
});

test('parseOooEndDate reads the formats people actually write', () => {
  const m = '2026-11-10';
  const cases = {
    'Dec-9': '2026-12-09',
    '8th december': '2026-12-08',
    'Nov 9th (Madrid public holiday)': '2026-11-09',
    'Dec 7/8th (National public Holiday)': '2026-12-08',
    'Nov 23-27 (Thanksgiving)': '2026-11-27',
    'Nov 24-27 (us thanksgiving and fam bdays)': '2026-11-27',
    'Nov 26–27 (US Thanksgiving)': '2026-11-27',
    'Nov 30 - Dec 2': '2026-12-02',
    '29 Dec - 2 Jan': '2027-01-02',
    'Sept 3': '2026-09-03',
    'January 5, 2027': '2027-01-05',
    '8-10 december': '2026-12-10',
  };
  for (const [text, want] of Object.entries(cases)) {
    assert.equal(parseOooEndDate(text, m), want, text);
  }
});

test('parseOooEndDate reads ISO dates, including several in one entry', () => {
  assert.equal(parseOooEndDate('Parental leave 2026-08-17 to 2026-09-28', '2026-08-04'), '2026-09-28');
  assert.equal(parseOooEndDate('OOO 2026-09-04 & 2026-09-07', '2026-08-25'), '2026-09-07');
  assert.equal(parseOooEndDate('2026-10-07 (Wednesday)', '2026-10-06'), '2026-10-07');
});

test('parseOooEndDate treats "week of X" as running through the end of that week', () => {
  assert.equal(parseOooEndDate('OOO week of July 6', '2026-07-07'), '2026-07-12');
  assert.equal(parseOooEndDate('Week of 2026-10-12 (next week)', '2026-10-06'), '2026-10-18');
});

test('parseOooEndDate does not read the verb "may" as a month', () => {
  // Real entry: deleting it as "past May 30" would be wrong.
  assert.equal(
    parseOooEndDate('I may actually get to work Wednesday (7/1). I’ll know 2026-06-30.', '2026-06-30'),
    null
  );
  assert.equal(parseOooEndDate('Jury duty may be coming in October.', '2026-09-01'), null);
  assert.equal(parseOooEndDate('May 4-5', '2026-04-20'), '2026-05-05');
  assert.equal(parseOooEndDate('4th of May', '2026-04-20'), '2026-05-04');
});

test('parseOooEndDate picks the year nearest the meeting', () => {
  assert.equal(parseOooEndDate('Jan 3', '2026-12-15'), '2027-01-03');
  assert.equal(parseOooEndDate('Dec 20', '2027-01-05'), '2026-12-20');
});

test('parseOooEndDate returns null when it cannot be sure', () => {
  for (const text of ['next week', 'out 2 weeks', '23-27', 'TBD', '11/23']) {
    assert.equal(parseOooEndDate(text, '2026-11-10'), null, text);
  }
});

test('classifyOoo separates past, upcoming, unparseable and non-date text', () => {
  const m = '2026-11-10';
  assert.equal(classifyOoo('Nov 9th (Madrid public holiday)', m), 'past');
  assert.equal(classifyOoo('Nov 10', m), 'upcoming'); // on the meeting day still counts
  assert.equal(classifyOoo('Nov 23-27', m), 'upcoming');
  assert.equal(classifyOoo('out 2 weeks', m), 'unparseable');
  assert.equal(classifyOoo('Maybe late Dec', m), 'unparseable');
  assert.equal(classifyOoo('None', m), 'none');
  assert.equal(classifyOoo('', m), 'none');
});

test('parseOooEndDate only counts a number as a day when it sits next to a month', () => {
  // Each of these used to be read as a past date and deleted (PR #73 review).
  const m = '2026-11-17';
  for (const text of [
    'Nov 9 and 12/3', // 12/3 is not November 12
    'Nov 9; 12/1',
    'Nov 9, out 2 weeks', // a duration, not November 2
    'Nov 9 - mid December', // a month without a day
    'Nov 9 until 2027', // a year that belongs to no date
  ]) {
    assert.equal(parseOooEndDate(text, m), null, text);
    assert.equal(classifyOoo(text, m), 'unparseable', text);
  }
});

test('parseOooEndDate binds each year to its own date', () => {
  // The last year used to apply to every date, so the Dec 28 2026 start hid the Jan 4 2027 end.
  assert.equal(parseOooEndDate('Jan 4 2027 (starting Dec 28 2026)', '2027-01-01'), '2027-01-04');
  assert.equal(parseOooEndDate('Dec 28 2026 - Jan 4 2027', '2027-01-01'), '2027-01-04');
  assert.equal(parseOooEndDate('29 Dec 2026 - 2 Jan', '2026-12-15'), '2027-01-02');
});

test('classifyOooWithChips weighs date chips and text together', () => {
  const m = '2026-11-10';
  assert.equal(classifyOooWithChips('', ['2026-11-09'], m), 'past');
  assert.equal(classifyOooWithChips('(Madrid holiday)', ['2026-11-09'], m), 'past');
  assert.equal(classifyOooWithChips('', ['2026-11-09', '2026-11-12'], m), 'upcoming');
  // A Nov 9 chip followed by "through Nov 23" is still running.
  assert.equal(classifyOooWithChips('through Nov 23', ['2026-11-09'], m), 'upcoming');
  assert.equal(classifyOooWithChips('through Nov 9', ['2026-11-02'], m), 'past');
  // Text the parser can't read keeps the entry, whatever the chip says.
  assert.equal(classifyOooWithChips('out 2 weeks', ['2026-11-02'], m), 'unparseable');
  // "week of" a chip lasts the whole week.
  assert.equal(classifyOooWithChips('week of', ['2026-11-09'], m), 'upcoming');
  assert.equal(classifyOooWithChips('Nov 23-27', [], m), 'upcoming');
});
