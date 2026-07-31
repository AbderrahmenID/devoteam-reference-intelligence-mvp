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

- Implemented one responsive Next.js search page with `dir="auto"`, RTL evidence, backend health, loading/error/abstention states and up to three source-backed cards.
- The UI contains no chat history, client-side search, fake fallback, login or dashboard.
- ESLint passes with zero warnings and the optimized production build succeeds (105 kB first-load JS for `/`).

## 2026-07-31 — PHASE 8 DONE

- Added schema-valid empty query/qrels templates and the requested ranking, no-answer, sample-count and latency metrics.
- Deeper evaluation rankings call the same retrieval service; public output remains capped at three.
- Empty run reports `HUMAN_JUDGMENTS_REQUIRED` with `metrics: null`; no label or official metric was invented.

## 2026-07-31 — PHASE 9 DONE

- Added safe environment, test, start, demo and stop PowerShell scripts plus exact README commands and architecture, limitation and supervisor-demo documentation.
- Fixed Windows PowerShell 5 source-encoding behavior by constructing non-ASCII smoke inputs from JSON Unicode escapes.
- Verified `start.ps1` creates scoped PIDs, both services become reachable, and `stop.ps1` validates and stops only those recorded processes.

## 2026-07-31 — PHASE 10 DONE

- Final Python suite: 24 passed; five harmless PyMuPDF SWIG deprecation warnings.
- Frontend lint: pass with zero warnings. Frontend production build: pass.
- Live demo: French/English/Arabic/mixed accepted with three cited references; unsupported query explicitly abstained; invalid filter remained HTTP 422.
- Final source baseline: 872 files, 177,905,384 bytes, aggregate SHA-256 `a2a6c376345acab3ea087d252b1f276121223b84c2582b1bcf3ad2ee2053ad66` — identical to Phase 0.
- Backend/frontend ports are closed after safe stop. Generated `.venv`, `node_modules`, build/test/runtime caches and package metadata are ignored by Git.
- The in-app browser connection was unavailable, so visual screenshot automation could not be performed; HTTP, type, build and live API/UI availability checks passed.
- Git was initialized on `main`. No commit was created because `user.email` is unset.
