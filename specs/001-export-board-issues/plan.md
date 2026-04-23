# Implementation Plan: GitHub project board → TSV export (`github-project-export`)

**Branch**: `001-export-board-issues` | **Date**: 2026-04-07 | **Spec**: [spec.md](./spec.md)  
**Input**: Re-run after spec updates: **JSON configuration file** (only) for project/filter/fields/output; **TSV** output; **`query` vs `queryParts`**; optional **`outputFile`**; **project fields + synthetic keys**; reuse **REST list items** with server-side `q` and `foc_project14_client`.

## Summary

Deliver a **uv-packaged CLI** in `github-project-export/` that reads a **JSON export profile**, fetches **GitHub Organization Projects v2** items via **`GET /orgs/{org}/projectsV2/{project_number}/items`** with server-side **`q`**, resolves **project field** columns plus **documented synthetic keys** from linked issue/PR payloads, and writes **TSV** to **stdout** or **`outputFile`**. Invocation is **`github-project-export <config.json>`** (plus non-duplicative flags such as `--help` / optional `--token` for parity with other repo tools—spec forbids duplicating project/filter/fields as CLI flags). Reuse `foc_project14_client` for field-ID discovery and paginated REST fetch.

## Technical Context

**Language/Version**: Python 3.10+ (match `foc-pr-report`)  
**Primary Dependencies**: `requests` (uv); stdlib `json`, `csv` (tab delimiter), `argparse`, `pathlib`, `urllib.parse`  
**Storage**: N/A (read-only export)  
**Testing**: pytest optional; manual validation with JSON fixture per [quickstart.md](./quickstart.md)  
**Target Platform**: macOS/Linux CLI  
**Project Type**: uv CLI package + shared client reuse from `foc-pr-report/foc_pr_report/foc_project14_client.py` (imported as `foc_pr_report.foc_project14_client`)  
**Performance Goals**: Server-side filter minimizes rows transferred; pagination as in existing client  
**Constraints**: Spec FR-007/FR-008; valid JSON schema validation before API; no secrets required in JSON  
**Scale/Scope**: Typical org board slices per spec SC-003

## Constitution Check

`.specify/memory/constitution.md` is a template. Gates from **CLAUDE.md**:

| Gate | Status |
|------|--------|
| Document CLI, token (`GITHUB_TOKEN`), `read:project` | PASS |
| Conventional commits when landing | PASS |
| Reuse shared GitHub project client | PASS |

**Post-design**: No violations.

## Project Structure

### Documentation (feature)

```text
specs/001-export-board-issues/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/cli.md
├── spec.md
├── tasks.md
└── checklists/
```

### Source (repository root)

```text
github-project-export/
├── pyproject.toml
├── README.md
├── uv.lock
└── github_project_export/
    ├── __init__.py
    ├── cli.py              # argparse: config path, --help, --token/--quiet as needed
    ├── config_schema.py    # load/validate JSON, build q string, resolve output sink
    ├── board_url.py        # projectUrl → org, project_number
    ├── rest_export.py      # field IDs, fetch_project_v2_items_rest, row → ordered values
    ├── synthetic.py        # documented synthetic key → value from content dict
    └── tsv_write.py        # tab-separated rows to stream

foc-pr-report/
└── foc_pr_report/
    └── foc_project14_client.py    # existing: list_project_v2_field_ids_by_name, fetch_project_v2_items_rest
```

**Structure Decision**: Single package `github-project-export/` mirroring `foc-pr-report/` layout.

## Complexity Tracking

None required.

---

## Phase 0: Research

**Output**: [research.md](./research.md)

Consolidated decisions:

- **REST + `q`** for listing (not GraphQL bulk) — aligns with [PR #24](https://github.com/FilOzone/tpm-utils/pull/24) / `foc_project14_client.fetch_project_v2_items_rest`.
- **JSON-only** config for board, filter, `fields`, `outputFile` per spec FR-001.
- **TSV**: `csv.writer` with `delimiter='\t'`, `lineterminator='\n'`, quoting=minimal or QUOTE_MINIMAL for tabs/newlines in cells.
- **Synthetic keys**: Small fixed set in v1 (e.g. `Repository` → `owner/repo`, URL → issue/PR `html_url`, `Type` → issue vs PR); exact list in README + `synthetic.py`; project fields matched by **case-insensitive** display name map to REST field IDs for `fields` query param.
- **`query` / `queryParts`**: Precedence and string-only `queryParts` per spec.

## Phase 1: Design

**Outputs**:

- [data-model.md](./data-model.md) — JSON config shape, validation, row derivation
- [contracts/cli.md](./contracts/cli.md) — invocation, exit codes, stderr vs stdout
- [quickstart.md](./quickstart.md) — `uv run` + sample JSON

**Agent context**: Run `update-agent-context.sh cursor-agent` after files are written.

## Phase 2

Implementation tasks live in [tasks.md](./tasks.md); **regenerate with `/speckit.tasks`** so checklist IDs match this plan and spec.
