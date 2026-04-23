# CLI contract: `github-project-export`

**Version**: 2026-04-07 (JSON config + TSV)  
**Package**: `github-project-export/` at repo root

## Purpose

Load a **JSON export configuration**, fetch matching **GitHub Org Project v2** items with server-side filter, emit **TSV** to stdout or to `outputFile`. See [spec.md](../spec.md).

## Invocation

```text
github-project-export <CONFIG.json>
```

- **CONFIG.json**: Path to JSON file (required positional argument).
- **No CLI flags** for `projectUrl`, filter, or `fields` (FR-001).

### Allowed auxiliary flags (non-duplicative)

Document precisely in `github-project-export/README.md`. Recommended:

| Flag | Purpose |
|------|---------|
| `--help` / `-h` | Usage and pointer to JSON schema |
| `--token` | Optional PAT override (else `GITHUB_TOKEN`) |
| `--quiet` | Less stderr progress |

## Authentication

Precedence: `--token` → `GITHUB_TOKEN`. Missing → exit `1`, stderr.

## Exit codes

| Code | Meaning |
|------|--------|
| 0 | Success (including zero data rows, header-only TSV) |
| 1 | Invalid config, bad args, missing token, unknown field names |
| 2 | GitHub API failure (HTTP, auth, rate limit, insufficient scope) |

## Output

- **Encoding**: UTF-8 TSV.
- **Stdout**: TSV body only when `outputFile` is omitted/null; **diagnostics** to stderr unless `--quiet`.
- **File**: When `outputFile` is a non-empty string, write TSV to that path (overwrite).

## Config contract (by reference)

Full shape: [data-model.md](../data-model.md). Spec requirements: FR-001–FR-008.

## Prohibited

- CLI options that mirror JSON: `--project-url`, `--filter`, `--fields`, `--output` / `-o` for export path (those belong in JSON only per spec).
