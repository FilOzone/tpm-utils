# Research: GitHub project board → TSV (JSON config)

**Feature**: [spec.md](./spec.md) | **Date**: 2026-04-07 (refresh after clarifications)

## 1. Listing API: REST with server-side `q`

**Decision**: Use `GET /orgs/{org}/projectsV2/{project_number}/items` with `q` and comma-separated numeric **`fields`** (project field IDs) via `foc_project14_client.fetch_project_v2_items_rest`.

**Rationale**: Same scalability argument as `foc-pr-report` ([PR #24](https://github.com/FilOzone/tpm-utils/pull/24)): filter runs on GitHub, not client-side over all cards.

**Alternatives considered**: GraphQL `projectV2.items` full listing — rejected for large filtered exports.

## 2. Configuration: JSON file only

**Decision**: All board locator, filter, column list, and output destination come from one JSON file; **no** `--project-url`, `--filter`, or `--fields` CLI flags (FR-001). Invocation passes **path to JSON** as the primary argument. Token via `GITHUB_TOKEN` / optional `--token` consistent with `foc-pr-report` (not duplicative of “settings” in spec sense).

**Rationale**: Reproducible exports; matches clarify session.

## 3. Filter encoding: `query` vs `queryParts`

**Decision**: If both exist, **`query` wins** and `queryParts` is ignored. If only `queryParts`, every element must be a **string**; join with ASCII space for `q`. Invalid types → fail before API.

**Rationale**: Spec FR-002a + clarifications.

## 4. Output: TSV and `outputFile`

**Decision**: **TSV** (UTF-8). Optional `outputFile`: absent or `null` → stdout; non-empty string → overwrite file; empty string → invalid config.

**Rationale**: Spec FR-004, FR-005 + clarification.

**Alternatives considered**: CSV — superseded by spec TSV.

## 5. Columns: project fields + synthetic keys

**Decision**:

- Resolve each `fields[i]` to either a **REST project field** (match display name with **documented case-folding**, e.g. insensitive trim + exact fold) or a **synthetic key** from a **closed set** documented in README (`Repository`, URL/`url`, issue-vs-PR type, etc.—final list in `synthetic.py` + FR-008).
- Request REST `fields` param only for **numeric IDs** corresponding to project field columns; synthetic columns come from `content` blob in each item.
- Header row = literal strings from `fields[]` (FR-003a).

**Rationale**: Spec FR-003; user example mixed board columns and repository/title-style data.

**Alternatives considered**: GraphQL-shaped normalization only — insufficient; `rest_board_item_to_graphql_node` is PR-skewed; exporter should read REST `item["fields"]` and `item["content"]` directly.

## 6. TSV writing

**Decision**: Python `csv.writer` with `delimiter='\t'`, `quoting=csv.QUOTE_MINIMAL` (or `QUOTE_NONNUMERIC` if needed for embedded tabs/newlines per spec edge cases).

**Rationale**: Stdlib, well-tested; document behavior for embedded tabs.

## 7. Token scope

**Decision**: Document `read:project` and `gh auth refresh -s read:project` like `foc-pr-report/README.md`.

---

No unresolved **NEEDS CLARIFICATION** for planning; synthetic key **spellings** are an implementation + README deliverable under FR-008.
