/**
 * 🗄️ FOC menu for the FOC Weekly Engineering Sync doc.
 *
 * Source of truth is GitHub (https://github.com/FilOzone/tpm-utils/tree/master/weekly-engineering-sync/apps-script).
 * Edits made in the Apps Script editor are overwritten by the next `clasp push`; change the code in GitHub instead.
 */

// Bump the minor (Y in X.Y) in the same commit as any script change; bump the major by hand when the doc itself must
// change for the script to work. See AGENTS.md.
var SCRIPT_VERSION = '1.1';

var SOURCE_URL = 'https://github.com/FilOzone/tpm-utils/tree/master/weekly-engineering-sync/apps-script';
var ISSUES_URL = 'https://github.com/FilOzone/tpm-utils/issues';

function onOpen() {
  DocumentApp.getUi()
    .createMenu('🗄️ FOC (v' + SCRIPT_VERSION + ')')
    .addItem('Prepare for next meeting…', 'prepareForNextMeeting')
    .addToUi();
}
