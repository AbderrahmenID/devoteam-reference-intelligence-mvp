# Filter and export implementation results

Recorded on 31 July 2026 (Africa/Tunis).

## Delivered

- Deterministic normalized metadata index over immutable parquet.
- Source-derived `GET /api/facets` counts and optional filter context.
- Validated hard multi-select filters with AND/OR semantics.
- Closed-interval time filtering and local-year presets.
- Complete eligible chunk ranking with BM25 and pinned local multilingual E5.
- Reference grouping followed by independent per-candidate evidence gates.
- Removal of the fixed three-result cap.
- Relevance/newest/oldest/title/client/country sorting.
- 10/20/50 pagination with a 500-reference internal ceiling.
- Extended source-grounded result schema and explicit no-eligible/no-relevant states.
- Responsive filter UI, chips, counts, sorting, summary/detail views and pagination.
- Stable-ID selection across pages, select-page, select-all-relevant and clear actions.
- Template-audited selected/all-relevant DOCX export with configurable sections.
- Server-side membership validation and immutable-template hash checks.

## Verification evidence

- Pre-change baseline: 24 tests passed, evaluation guard held, frontend lint/build passed.
- Current backend suite: 48 tests after adding filter, interval, ongoing/completed, facet, pagination, leakage, sorting, Unicode export and selected/all-relevant coverage.
- Frontend: ESLint passed; Next.js 15.5.7 production compilation and TypeScript validation passed.
- Live scripts: environment validation, startup and multilingual demo checks passed.
- Live API: filtered `API gateway Kong` search returned five source-supported Côte d’Ivoire references in the tested context.
- DOCX smoke artifact: two selected API-related references; package reopened; three tables; both selected records present; template hash unchanged.
- Generated DOCX opens successfully through Microsoft Word automation.

## Render verification status

The supplied template was audited directly through OOXML: 17 Word sections, 18 tables, 953 paragraphs, 32 media assets, one summary table and 17 detailed reference tables.

LibreOffice/`soffice` and other DOCX-to-PDF renderers are not installed on this host. Microsoft Word successfully opens both a minimal control DOCX and the generated export, but its headless PDF conversion hangs even for the minimal one-page control. Multiple invisible conversion processes were stopped after bounded waits; no source or template was changed.

Therefore this host supports:

- exact template structural audit;
- package/content/relationship validation;
- Python reopening;
- native Microsoft Word open validation;

but not automated page-image inspection. Visual PDF rendering remains an environment limitation, not a DOCX generation error. DOCX is the primary deliverable and PDF was explicitly optional.

## Guardrails preserved

- No source-project or corpus mutation.
- No corpus migration, extraction rerun, embedding/index regeneration or model download.
- No reranker.
- No invented expert labels, qrels, contact details, dates, staffing or project outcomes.
- No nearest-neighbor fallback when evidence is weak.
- No client-side fake data or client-side search.
- Human relevance metrics remain `HUMAN_JUDGMENTS_REQUIRED` until reviewed qrels exist.
