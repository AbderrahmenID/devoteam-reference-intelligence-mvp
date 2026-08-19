# Progress

## 2026-07-31 — PHASE 0 DONE

- Inspected the complete source and empty MVP folder before migration.
- Reviewed required extraction/corpus/retrieval/matching modules, configurations, tests and version ranges.
- Selected the validated Phase 4 corpus and Phase 5 BM25/E5 artifacts; no OCR or embedding rebuild is needed.
- Confirmed local pinned E5 model availability.
- Recorded source baseline: 872 files, 177,905,384 bytes, aggregate content-inventory SHA-256 `a2a6c376345acab3ea087d252b1f276121223b84c2582b1bcf3ad2ee2053ad66`.
- Environment: Python 3.10.11 selected because 3.11 is absent; Node/npm and Git available; Tesseract absent.
- No source file was written, moved, renamed, regenerated or deleted.
- Next: Phase 1 minimal foundation.

## 2026-07-31 — PHASE 1 DONE

- Created the required minimal Python packages, root configuration, pinned dependency contracts, frontend package configuration, local `.venv` and local Git repository.
- Used Python 3.10 because 3.11 is not installed. The venv inherits the already-installed Torch runtime to avoid an unnecessary large download.
- Installed all direct MVP dependencies and verified imports. `USE_TF=0` is required because unrelated globally inherited TensorFlow/protobuf packages conflict; the MVP does not use TensorFlow.
- Installed Next.js dependencies and generated `package-lock.json`.
- Git identity has a user name but no email, so no commit will be created unless identity becomes complete.
- Evidence: editable install and configuration contract checks pass.

## 2026-07-31 — PHASE 2 DONE

- Copied exactly 11 approved canonical/index files; each destination SHA-256 equals its immutable source.
- Created `data/DATA_MANIFEST.json` with source/destination, size, SHA-256, row counts, schemas, reasons and timestamp.
- Confirmed 1,185 unique chunks, 161 unique references, 1,185 lookup rows, `(1185, 768)` normalized finite embeddings and exact lookup ordering.
- Confirmed all linked source rows exist, source pages/citations are present, and Arabic plus accented French survive UTF-8 Parquet loading.
- `tests/test_data_integrity.py`: 3 passed.
- Next: Phase 3 retrieval migration.

## 2026-07-31 — PHASE 3 DONE

- Implemented the source-compatible pickle-free Unicode BM25 loader/scorer, offline E5 query encoder, normalized dense dot-product index, deterministic weighted RRF, hard metadata filters, reference grouping and bounded cited results.
- Reused the 1,185-row source indexes without regenerating embeddings or enabling FAISS/reranking.
- Tests: BM25, dense and hybrid focused suites pass; the real pinned CPU encoder returns a normalized 768-dimensional vector.

## 2026-07-31 — PHASE 4 DONE

- Implemented script, approximate language, mixed-script and RTL detection plus separate Arabic-safe retrieval normalization.
- Original evidence text is never overwritten and language is never a hard retrieval filter.
- Real French, English, Arabic and mixed Arabic/French probes returned cross-language citations; focused language tests pass.

## 2026-07-31 — PHASE 5 DONE

- Implemented deterministic invalid-input and no-evidence gates using BM25, dense, top-score mean, term coverage, retriever agreement, passage count and portfolio scope.
- Thresholds and scope patterns live in `config.yaml`; all reasons are explicit and diagnostics are opt-in.
- Supported probes pass; unrelated cooking/quantum probes abstain with zero results.

## 2026-07-31 — PHASE 6 DONE

- Implemented FastAPI health, configuration summary, search and bounded extraction-preview endpoints.
- Validation covers malformed JSON, query types, unknown filters, top-k capping, Unicode and prompt-injection-style text treated only as retrieval data.
- Extraction preview is capped at 5 MB/3 pages and preserves the uploaded filename; six API tests pass.

## 2026-07-31 — PHASE 7 DONE

- Implemented a responsive Next.js search page with `dir="auto"`, RTL evidence, backend health, filter/facet controls, pagination, export selection and explicit abstention states.
- The UI contains no chat history, client-side search, fake fallback, login or dashboard.
- ESLint passes with zero warnings and the optimized production build succeeds (105 kB first-load JS for `/`).

## 2026-07-31 — PHASE 8 DONE

- Added schema-valid empty query/qrels templates and the requested ranking, no-answer, sample-count and latency metrics.
- Deeper evaluation rankings call the same retrieval service; public output is evidence-gated and paginated without a fixed top-three cap.
- Empty run reports `HUMAN_JUDGMENTS_REQUIRED` with `metrics: null`; no label or official metric was invented.

## 2026-07-31 — PHASE 9 DONE

- Added safe environment, test, start, demo and stop PowerShell scripts plus exact README commands and architecture, limitation and supervisor-demo documentation.
- Fixed Windows PowerShell 5 source-encoding behavior by constructing non-ASCII smoke inputs from JSON Unicode escapes.
- Verified `start.ps1` creates scoped PIDs, both services become reachable, and `stop.ps1` validates and stops only those recorded processes.

## 2026-07-31 — PHASE 10 DONE

- Final Python suite: 24 passed; five harmless PyMuPDF SWIG deprecation warnings.
- Frontend lint: pass with zero warnings. Frontend production build: pass.
- Baseline live demo: French/English/Arabic/mixed queries returned cited references; unsupported query explicitly abstained; invalid filter remained HTTP 422. See `FILTER_AND_EXPORT_RESULTS.md` for the current extension.
- Final source baseline: 872 files, 177,905,384 bytes, aggregate SHA-256 `a2a6c376345acab3ea087d252b1f276121223b84c2582b1bcf3ad2ee2053ad66` — identical to Phase 0.
- Backend/frontend ports are closed after safe stop. Generated `.venv`, `node_modules`, build/test/runtime caches and package metadata are ignored by Git.
- The in-app browser connection was unavailable, so visual screenshot automation could not be performed; HTTP, type, build and live API/UI availability checks passed.
- Git was initialized on `main`; the validated baseline was later committed after the user supplied the repository email identity.

## 2026-07-31 — FILTER AND EXPORT EXTENSION DONE

- Recorded and preserved the green 24-test baseline at commit `c378ad86b0917e01b3e24ac2b56eeecccd8691b0`.
- Audited the 41-page Word reference template, created the byte-identical canonical path and documented field provenance and missing-value rules.
- Added the deterministic normalized reference index, source-driven facets, AND/OR hard filters, interval overlap and relative-year presets.
- Ranked the complete eligible masked universe, applied the existing evidence logic independently per reference, removed the top-three cap and added stable sorting/pagination.
- Added the summary/detailed UI, active chips, persistent stable-ID selection and selected/all-relevant export controls.
- Added hash-verified, template-audited DOCX generation with summary/annex sections and cited source passages.
- Final verification: 48 Python tests, human-judgment guard, frontend lint/types/production build, lifecycle scripts and live health/facet/search checks pass.
- Reranker remains disabled; source parquet, chunks, embeddings, BM25/E5 indexes and source pipeline remain unchanged.
- In-app browser discovery and host DOCX-to-PDF rendering are unavailable; the UI build/live HTTP contract and Word-open/package checks pass, and the limitation is recorded.

## 2026-08-02 — RETRIEVAL EVIDENCE QUALITY HOTFIX DONE

- Captured the green 48-test broken baseline and created branch `fix/retrieval-evidence-quality` before changing ranking behavior.
- Proved corrupt passages originate in immutable `chunks.parquet:chunk_text`; JSON and React were faithful downstream carriers.
- Added the reproducible per-query diagnostic and complete text-field lineage.
- Removed French/English/Arabic stopwords and corpus-common terms from lexical scoring, coverage, bonus, and explanations while preserving acronyms and technology phrases.
- Added runtime display derivation, a configurable evidence quality evaluator, best-passage selection, capability metadata compatibility, and stronger abstention.
- Replaced raw exact-term output with structured professional match reasons and bidi-safe, source-cited display passages.
- Added 14 regression tests; final Python suite is 62 passing. Frontend lint/build and live French/English/Arabic/mixed/zero-result smoke checks pass.
- Canonical corpus/index assets are unchanged and the reranker remains disabled.

## 2026-08-02 — DIRECT RETRIEVAL IMPROVEMENT DONE

- Verified the 1,125-row v2 package, 768-dimensional aligned embeddings, repaired-chunk inclusion, quarantine exclusion and byte-identical v1/v2 runtime assets.
- Activated selected v2 through a reversible configuration switch while retaining exact v1 and pre-improvement-v2 baselines.
- Added field-aware BM25, exact acronym/technology support, 0.75/0.25 weighted RRF, best-plus-support reference aggregation and explicit relevance patterns.
- Added professional evidence cleanup and deterministic user-facing explanations with no score/confidence display.
- Added `python -m retrieval.diagnose --query ... --json` and complete query traces.
- Completed the 255-row technical sweep: zero automated safety issues; every obvious unsupported query abstained under every weight pair.
- No qrels or relevance labels were created and no precision/recall claim is made.
- Final gate: 75 Python tests and seven v2 integrity tests passed; environment validation, frontend lint/build, direct JSON diagnostic and live start/demo/stop passed; ports 3000/8000 closed.

## 2026-08-03 — DETERMINISTIC REFERENCE-PACK GENERATION DONE

- Analyzed template PDF pages 10–29, preserved the authorized source at the required versioned path, recorded SHA-256 `bc01334088c95c3796f1b98586e4980c66fd084c45174eec23ff03195bb39334`, and created editable template `DEVOTEAM_REFERENCE_PACK_V1`.
- Added an ordered session-persistent manual selection basket and French/English/Arabic generation form with progress, exact errors and PPTX/PDF/manifest downloads.
- Added manifest-pinned v2 revalidation for stable IDs, retrieval/display policy, security class, source document/hash/page/citation lineage and duplicate/traversal prevention.
- Added deterministic source-boundary content preparation, editable `python-pptx` layouts, safe evidence cards, PyMuPDF crop support for future approved local sources, and headless LibreOffice 26.2.5.2 PDF conversion.
- Added create/status/PPTX/PDF/manifest APIs, per-generation hashes, bullet provenance, logs and exact generation command.
- Focused gates: 12 backend tests, 7 frontend tests, lint/types/build and four-pack visual matrix pass.
- Real outputs: 1 reference / 5 slides / 2.10 s; 3 / 8 / 2.96 s; 4 Arabic / 10 / 3.81 s; 10 / 21 / 7.28 s. Every PDF page count matches its PPTX.
- Retrieval ranking/model/corpus behavior is unchanged; v1 rollback and immutable source project remain outside this feature’s write scope.
- Complete gate: 87 Python tests, evaluation guard, 7 frontend tests, lint/build, live multilingual retrieval, live reference-pack API/download, controlled stop and closed ports all pass.
