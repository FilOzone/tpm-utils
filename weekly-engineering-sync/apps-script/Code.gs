/**
 * 🗄️ FOC menu for the FOC Weekly Engineering Sync doc.
 *
 * Source of truth is GitHub (https://github.com/FilOzone/tpm-utils/tree/master/weekly-engineering-sync/apps-script).
 * Edits made in the Apps Script editor are overwritten by the next `clasp push`; change the code in GitHub instead.
 */

// Bump the minor (Y in X.Y) in the same commit as any script change; bump the major by hand when the doc itself must
// change for the script to work. See AGENTS.md.
var SCRIPT_VERSION = '1.3';

var SOURCE_URL = 'https://github.com/FilOzone/tpm-utils/tree/master/weekly-engineering-sync/apps-script';
var ISSUES_URL = 'https://github.com/FilOzone/tpm-utils/issues';
var README_URL = 'https://github.com/FilOzone/tpm-utils/blob/master/weekly-engineering-sync/apps-script/README.md';

function onOpen() {
  DocumentApp.getUi()
    .createMenu('🗄️ FOC (v' + SCRIPT_VERSION + ')')
    .addItem('Prepare for next meeting…', 'prepareForNextMeeting')
    .addSeparator()
    .addItem('About this menu', 'showAbout')
    .addToUi();
}

/** Opens the README in a new browser tab. Menu items can't open URLs, so a small dialog does it (with a link). */
function showAbout() {
  var template = HtmlService.createTemplateFromFile('AboutDialog');
  template.payload = jsonForHtml_({ version: SCRIPT_VERSION, readmeUrl: README_URL, issuesUrl: ISSUES_URL });
  DocumentApp.getUi().showModalDialog(template.evaluate().setWidth(380).setHeight(190), '🗄️ FOC menu (v' + SCRIPT_VERSION + ')');
}
