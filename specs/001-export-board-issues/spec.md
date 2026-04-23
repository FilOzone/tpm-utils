# Feature Specification: Export project board items to TSV

**Feature Branch**: `001-export-board-issues`  
**Created**: 2026-04-06  
**Status**: Draft  
**Input**: User description: "I want to create a cli utility for being able to pull issues from a project board. Inputs: Project board URL, Project filter, List of fields to include. Output: CSV of the project board items that match the project, filter. Fields should be the items exported. Output should either be able to stdout or to a file. Use case: easily export a given project with a filter to a spreadsheet."

## Clarifications

### Session 2026-04-07

- Q: Should query input be `queryParts` only, `query` only, or both? → A: Support both `query` and `queryParts`; if both are present, a non-empty `query` takes precedence; if `query` is omitted, `null`, or empty/whitespace, fall back to `queryParts`.
- Q: JSON file vs CLI for primary inputs? → A: JSON configuration file only—no equivalent CLI flags for project, filter, or field list (invocation supplies the config path only, aside from documented credential handling).
- Q: May `queryParts` contain non-strings (e.g. numbers)? → A: No—every `queryParts` element MUST be a string; otherwise the config is invalid and the tool MUST fail with a clear error.
- Q: How should JSON choose stdout vs file output? → A: Optional `outputFile`: when the key is omitted or the value is JSON `null`, write TSV to **stdout**; when the value is a non-empty string, write to that file path (overwrite).
- Q: May `fields` include only native project fields? → A: No—`fields` MAY list **project field display names** and **documented synthetic keys** derived from linked issue/PR content (e.g. repository, URL); synthetic keys and name-matching rules MUST be documented.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Export filtered board items to a spreadsheet-ready file (Priority: P1)

A user supplies a **JSON configuration file** that identifies the project board, filter criteria, and which attributes become columns. They receive **TSV** (tab-separated values), suitable for opening in a spreadsheet—one row per matching item and columns in the configured order.

**Why this priority**: This is the core outcome: turning a filtered view of a board into portable tabular data for analysis and sharing.

**Independent Test**: Run the utility with a known-good JSON config; verify TSV row count and column headers match expectations for that board and filter.

**Acceptance Scenarios**:

1. **Given** a board the user can access, a filter that matches a known subset of items, and a non-empty field list in the JSON config, **When** the user runs the export, **Then** the output is TSV with a header row of the requested fields and one data row per matching item.
2. **Given** the same config with multiple items matching the filter, **When** the user runs the export, **Then** every matching item appears exactly once (no duplicates, no omissions attributable to ordering).

---

### User Story 2 - Send output to the terminal or to a file (Priority: P2)

A user chooses, **via the JSON configuration**, whether the TSV is printed to standard output or written to a specified file path so they can script pipelines or save directly to disk.

**Why this priority**: Supports automation (pipes) and the common “save as file” workflow for spreadsheets without changing the meaning of the data.

**Independent Test**: Same export parameters with output directed to stdout versus a file path in the config; TSV body matches byte-for-byte except for line-ending normalization if the environment differs.

**Acceptance Scenarios**:

1. **Given** a valid export configuration with `outputFile` omitted or `null`, **When** the user runs the export, **Then** the full TSV is written to standard output and nothing is required to be written to a file.
2. **Given** a valid export configuration with `outputFile` set to a non-empty writable path string, **When** the user runs the export, **Then** the TSV is created or overwritten at that path with correct content.

---

### User Story 3 - Understand failures without misleading data (Priority: P3)

When the board cannot be resolved, access is denied, the filter is invalid, the JSON config is malformed, or no items match, the user gets a clear result: either a deliberate empty result (headers only or documented convention) or a clear error message—not a partial or ambiguous export.

**Why this priority**: Prevents silent wrong data in spreadsheets, which is worse than a visible failure.

**Independent Test**: Exercise invalid JSON, invalid URL, invalid filter, empty match set, and unauthorized access; verify outcomes match the documented behavior for each case.

**Acceptance Scenarios**:

1. **Given** inputs that the tool cannot apply (for example, bad config, unreachable board, or unusable filter), **When** the user runs the export, **Then** the process fails with a message that indicates failure and does not claim success for a full export.
2. **Given** a valid configuration where zero items match the filter, **When** the user runs the export, **Then** the behavior is consistent and documented (for example, TSV with only a header row—see Assumptions).

---

### Edge Cases

- No items match the filter: output convention is explicit and consistent (assumption: TSV with header row only).
- User requests an empty field list: tool rejects the request or uses a documented default—assumption: empty list is rejected with guidance.
- Cell values include tabs or newlines: output remains valid TSV per documented escaping rules (tabs/newlines in fields must not break column alignment).
- Very large boards: export completes without requiring manual chunking by the user for typical org-scale boards (exact limits out of scope unless product defines them).
- Duplicate field names in the requested list: tool deduplicates or rejects with a clear error (assumption: duplicate names are rejected).
- A `fields` entry is neither a recognized project field nor a documented synthetic key: invalid configuration; fail with a clear error listing valid options.
- `queryParts` contains a non-string value: invalid configuration; fail before calling the API.
- `outputFile` is present but is an empty string: invalid configuration; fail with a clear error (treat as neither stdout nor a valid path).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The utility MUST load export settings from a **JSON configuration file** provided at invocation (path is the primary argument). Project board locator, filter, field list, and output destination MUST be read from that file. The utility MUST NOT expose separate CLI flags that duplicate those settings (e.g., no `--project-url`, `--filter`, or `--fields` flags).
- **FR-001a**: The JSON configuration MUST include a project board locator (e.g., `projectUrl` matching the browser URL pattern for an organization project). Credentials MUST follow the same environment/session mechanisms as other tools in this repository (e.g., token via environment variable); the spec does not require storing secrets in the JSON file.
- **FR-002**: The utility MUST accept filter criteria that restrict which items on that board are included in the export, using the same notion of “filter” as the board product supports, encoded in the JSON config.
- **FR-002a**: The JSON MAY include either a string `query` **or** a `queryParts` array; when both are present, `query` MUST take precedence and `queryParts` MUST be ignored. When `queryParts` is present, every element MUST be a **string**; any other type MUST make the configuration invalid with a clear error. When only `queryParts` is present and valid, the utility MUST join elements with a single ASCII space to form the server-side `q` string.
- **FR-003**: The utility MUST accept an explicit list (`fields`) in the JSON config; each entry names one exported column in list order. Each entry MUST be either (a) the display name of a **project field** present on that board, after the documented name-matching rules, or (b) a **synthetic key** from the documented set (values derived from the linked issue or pull request, not from custom project fields). The utility MUST reject any entry that matches neither (a) nor (b).
- **FR-003a**: TSV header cells MUST use the same strings as in `fields` (the user’s configured names), in order, so exports round-trip visually in spreadsheets.
- **FR-004**: The utility MUST produce output in **TSV** format: first row is column headers corresponding to the requested fields; subsequent rows are one per included item; fields separated by tab characters.
- **FR-005**: The utility MUST use optional **`outputFile`** in the JSON configuration to select the output sink: if `outputFile` is **omitted** or **`null`**, the full TSV MUST be written to **standard output**; if `outputFile` is a **non-empty string**, the full TSV MUST be written to that filesystem path (replacing any existing file). An **`outputFile` value that is an empty string** MUST be treated as invalid configuration.
- **FR-006**: The utility MUST NOT include items that do not satisfy the supplied filter.
- **FR-007**: When the user lacks access to the board, the locator is invalid, or the config is invalid, the utility MUST fail with a clear error and MUST NOT emit TSV that looks like a successful export of real items.
- **FR-008**: The utility MUST document how zero matching items are represented in the TSV output, the full set of **synthetic keys** and their meanings, the rules for matching **project field** names, and the JSON configuration schema with at least one validated example (including filter, `fields`, and `outputFile`).

### Key Entities

- **Export configuration (JSON file)**: User-authored file listing `projectUrl`, filter (`query` and/or `queryParts`), `fields`, and optional `outputFile` (`null`/omitted → stdout; non-empty string → file path); supplied at runtime as the invocation input.
- **Project board**: A named collection of work items the user can view in a browser; identified by `projectUrl` in the configuration.
- **Board item**: A single row-worthy record on the board (for example an issue or work item); has a stable identity within the export and multiple optional attributes.
- **Project field**: A column defined on the board; referenced in `fields` by its display name per documented matching rules.
- **Synthetic column key**: A reserved name in `fields` that maps to linked content (issue/PR) data (e.g. repository full name, web URL), documented in shipped help—not a board-defined custom field.
- **Filter**: Criteria that subset board items; only items passing the filter appear in the TSV.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On a board with a known number of items matching a test filter, 100% of exported rows correspond to those items (counts and identities checkable against the board).
- **SC-002**: For a requested set of N fields in the JSON config, the TSV contains exactly N columns (with correct header labels) on every successful export.
- **SC-003**: A user can complete a typical export (under 500 items, handful of fields) from invocation to saved file or captured stdout in under two minutes, including reading brief help and a sample JSON config if needed.
- **SC-004**: In user acceptance testing, at least 90% of participants successfully produce an importable spreadsheet on the first try when given a valid JSON configuration file and token setup instructions.

## Assumptions

- Users are already able to open the board in a browser and sign in when needed; the utility relies on credentials or session mechanisms consistent with other CLI tools in this repository (not specified in this spec).
- “Project filter” means product-supported filtering of which items belong to the export (not redefined ad hoc in the utility).
- If a requested field is missing on an item, the cell is left empty or a single documented placeholder is used—never silently swapped with another field’s value.
- Zero matches: TSV contains the header row and zero data rows unless a different convention is documented before implementation.
- Empty field list is invalid input and produces a clear error.
- Duplicate field names in the user’s list are rejected with a clear error.
- Out of scope: editing board data, incremental sync, scheduling, or additional export formats beyond **TSV** unless added in a later specification.
