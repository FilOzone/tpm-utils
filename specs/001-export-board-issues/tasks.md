# Tasks: GitHub project board → TSV export (`github-project-export`)

**Input**: Design documents from `/specs/001-export-board-issues/`  
**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [data-model.md](./data-model.md), [contracts/cli.md](./contracts/cli.md), [research.md](./research.md), [quickstart.md](./quickstart.md)

**Tests**: Not required by spec; verify via manual runs and [quickstart.md](./quickstart.md).

**Organization**: Phases follow user story priorities P1 → P3 in [spec.md](./spec.md).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Parallelizable within the phase
- **[Story]**: `[US1]` … `[US3]` for user-story phases only

## Path conventions

Package root: `github-project-export/` (parallel to `foc-pr-report/`). Shared: `foc_project14_client.py` at repo root.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: uv package skeleton and lockfile

- [x] T001 Create `github-project-export/github_project_export/__init__.py` as package marker
- [x] T002 Add `github-project-export/pyproject.toml` with hatchling, `requests` dependency, and `github-project-export` console script entrypoint
- [x] T003 [P] Add `github-project-export/.gitignore` for `.venv/`, `__pycache__/`, and `*.pyc`
- [x] T004 Generate `github-project-export/uv.lock` by running `uv lock` in `github-project-export/`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: URL parse, config validation, synthetic keys, TSV primitive, REST row extraction—before CLI wiring

**⚠️ CRITICAL**: No user story completion until this phase is done

- [x] T005 [P] Implement `projectUrl` → `(org, project_number)` parsing and validation in `github-project-export/github_project_export/board_url.py`
- [x] T006 [P] Implement documented synthetic column resolvers (e.g. repository, url, type) in `github-project-export/github_project_export/synthetic.py`
- [x] T007 [P] Implement tab-delimited writer (UTF-8, `csv.writer` with `delimiter='\t'`) in `github-project-export/github_project_export/tsv_write.py`
- [x] T008 Implement JSON load and validation per spec in `github-project-export/github_project_export/config_schema.py` (`projectUrl`, `query`/`queryParts` precedence, string-only `queryParts`, non-empty non-duplicate `fields`, `outputFile` null/omit vs non-empty string vs reject `""`, reject unknown `fields` entries after board field names are loaded—may expose a two-phase validate hook from `rest_export` or fetch fields map first)
- [x] T009 Implement field-name → REST field ID mapping (case-insensitive board match), `fetch_project_v2_items_rest` call with `q` and `fields` param, and per-item ordered cell values for mixed project + synthetic columns in `github-project-export/github_project_export/rest_export.py` (handle both issue and pull_request REST `content` shapes)

**Checkpoint**: Given a parsed config object and `requests.Session`, `rest_export` yields rows aligned to `fields` order

---

## Phase 3: User Story 1 — Export filtered items to TSV (Priority: P1) 🎯 MVP

**Goal**: `github-project-export <config.json>` writes TSV with correct headers and one row per item when `outputFile` is omitted or null.

**Independent Test**: JSON fixture + token; stdout TSV row count and headers match board for filter.

### Implementation for User Story 1

- [x] T010 [US1] Implement `github-project-export/github_project_export/cli.py`: argparse for positional `config.json`, `--help`, optional `--token` and `--quiet`; inject repo root into `sys.path`; build session; load+validate config; run `rest_export`; write TSV to **stdout** when `outputFile` is null/omitted using `tsv_write.py`

**Checkpoint**: MVP stdout export works

---

## Phase 4: User Story 2 — File output via JSON (Priority: P2)

**Goal**: Same as US1 but write to `outputFile` when set to a non-empty path; diagnostics on stderr unless `--quiet`.

**Independent Test**: Same config with `outputFile` set; file bytes match prior stdout capture.

### Implementation for User Story 2

- [x] T011 [US2] Extend `github-project-export/github_project_export/cli.py` to write TSV to the `outputFile` path when provided (overwrite) and keep data on stdout only in stdout mode

**Checkpoint**: File and pipe workflows both work

---

## Phase 5: User Story 3 — Failures and empty results (Priority: P3)

**Goal**: Exit **1** vs **2** per [contracts/cli.md](./contracts/cli.md); zero matches → header-only TSV, exit 0; API/auth errors → no “successful-looking” data rows.

**Independent Test**: Malformed JSON, bad `projectUrl`, bad token, empty result set.

### Implementation for User Story 3

- [x] T012 [US3] Harden `github-project-export/github_project_export/cli.py` (and validation paths in `github-project-export/github_project_export/config_schema.py` / `github-project-export/github_project_export/rest_export.py` as needed) for exit codes, clear stderr messages, and header-only success on zero items

**Checkpoint**: Spec User Story 3 acceptance scenarios satisfied

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: FR-008 documentation and repo navigation

- [x] T013 [P] Write `github-project-export/README.md` documenting full JSON schema, synthetic keys table, project field matching rules, `read:project` / `gh auth refresh`, zero-row behavior, and prohibiting duplicate CLI settings per spec
- [x] T014 [P] Add a concise “GitHub project TSV export” bullet in root `README.md` linking to `github-project-export/README.md`
- [x] T015 [P] Reconcile `specs/001-export-board-issues/quickstart.md` with final CLI invocation and JSON keys after implementation

---

## Dependencies & Execution Order

### Phase Dependencies

- Phase 1 → Phase 2 → Phase 3 (US1) → Phase 4 (US2) → Phase 5 (US3) → Phase 6
- **US2** builds on US1 (file branch is additive)
- **US3** refines US1/US2 error paths

### Parallel opportunities

- **Phase 1**: T003 parallel with T001–T002 before T004
- **Phase 2**: **T005**, **T006**, **T007** in parallel; **T008** after T005 (and may need small refactor once T009 defines field validation order); **T009** after T006 and T008
- **Phase 6**: **T013**, **T014**, **T015** in parallel

### Parallel example: Phase 2 kickoff

```text
T005 → github-project-export/github_project_export/board_url.py
T006 → github-project-export/github_project_export/synthetic.py
T007 → github-project-export/github_project_export/tsv_write.py
→ then T008 config_schema.py → T009 rest_export.py
```

---

## Implementation Strategy

### MVP (User Story 1)

1. Complete Phases 1–2  
2. Complete Phase 3 (T010)—stdout TSV  
3. Validate before adding file output

### Incremental delivery

1. Phase 4 (file sink)  
2. Phase 5 (errors / empty)  
3. Phase 6 docs

---

## Task summary

| Phase | Task IDs | Count |
|-------|----------|-------|
| Setup | T001–T004 | 4 |
| Foundational | T005–T009 | 5 |
| US1 | T010 | 1 |
| US2 | T011 | 1 |
| US3 | T012 | 1 |
| Polish | T013–T015 | 3 |
| **Total** | **T001–T015** | **15** |

**Format validation**: Every task uses `- [x] Tnnn` (all completed), includes an explicit file path, and story phases include `[US1]`–`[US3]` as required.
