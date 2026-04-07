# Data model: JSON → TSV export

**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

## Export configuration (JSON)

| Field | Type | Required | Rules |
|-------|------|----------|--------|
| `projectUrl` | string | Yes | Organization project URL, e.g. `https://github.com/orgs/{org}/projects/{n}` — parse to `org`, `project_number`. |
| `query` | string | No* | Server-side project search string. If present with `queryParts`, **`query` is used** and `queryParts` ignored. |
| `queryParts` | string[] | No* | Only strings; joined with single space → `q` when `query` absent. |
| `fields` | string[] | Yes | Non-empty; no duplicates; each token must resolve to a **project field** (after matching rules) or a **synthetic key**. Order = column order. |
| `outputFile` | string \| null | No | Omitted or `null` → write TSV to stdout. Non-empty string → path. **Empty string invalid.** |

\* At least one of `query` or `queryParts` must yield a non-empty `q` after processing; if both absent or join yields empty, treat as invalid config (document behavior in implementation).

## Derived entities

### Resolved board target

- `org_login`, `project_number` from `projectUrl`.

### Filter string (`q`)

- From `query` if set; else ` " ".join(queryParts) ` if valid.

### Column resolution

For each string `f` in `fields` (preserved for TSV header):

1. If `f` matches a **synthetic key** (case rules in README): value from `content` (issue/PR REST object). No REST field id.
2. Else map `f` → project field display name → REST field id from `list_project_v2_field_ids_by_name`. If no match → configuration error with hints (list board field names + synthetic table).

### Board item row

- Source: one REST `/items` array element.
- Includes `fields[]` (subset requested via `fields` param) and `content` (issue, pull request, or empty).

## Validation summary (from spec)

- Malformed JSON → exit user-error class.
- `queryParts` non-string element → invalid.
- `outputFile` `""` → invalid.
- Unknown `fields` entry → invalid.
- Duplicate `fields` → invalid.
- Zero API matches → header-only TSV, exit 0.

## Synthetic keys (planning set — finalize in FR-008 / README)

Illustrative v1 set (exact spellings to document):

| Key (as user may type) | Source |
|------------------------|--------|
| `Repository` | `content` repository full name (`repos/{owner}/{repo}` path or nested fields) |
| `url` / `URL` | `content.html_url` |
| `Type` | literal `issue` or `pull_request` from GitHub type discriminator |

Project-native names like `Title`, `Status`, `Assignees` resolve via board fields when present.
