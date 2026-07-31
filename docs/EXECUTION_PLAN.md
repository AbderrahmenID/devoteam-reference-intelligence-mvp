# Execution plan

Statuses are updated only when the stated acceptance criteria pass.

## PHASE 0 — Discovery and inventory

- Objective: inspect source/target, toolchains, models, data, indexes, tests and requirements without source mutation.
- Files: `docs/SOURCE_INVENTORY.md`, `docs/MIGRATION_DECISIONS.md`, `docs/EXECUTION_PLAN.md`, `docs/PROGRESS.md`, `docs/source_inventory.json`.
- Acceptance criteria: exact copy/exclusion set; source baseline; compatibility risks recorded.
- Commands: recursive file inventory, version checks, Parquet schema inspection, manifest/config/module/test inspection, aggregate source hash.
- Tests: source readable; catalogs/index rows align; pinned model snapshot present.
- Status: DONE
- Blockers: none; Tesseract absence is an extraction-runtime limitation, not a Phase 0 blocker.
- Evidence: 872-file baseline; 1,185 aligned chunk/vector rows; pinned E5 snapshot found.

## PHASE 1 — Minimal project foundation

- Objective: create the required small Python/Next project and one configuration contract.
- Files: root metadata/config, package initializers and frontend skeleton.
- Acceptance criteria: imports/config load; required structure exists; `.venv` and Git are local to MVP.
- Commands: create venv with Python 3.10, install dependencies, initialize Git/npm.
- Tests: configuration validation and import smoke test.
- Status: DONE
- Blockers: none.
- Evidence: Python 3.10 `.venv`, editable package install, Git `main`, npm lockfile, validated single `config.yaml`.

## PHASE 2 — Data migration and validation

- Objective: copy only approved corpus/index files and produce a verified manifest.
- Files: `data/*`, `data/indexes/*`, `data/DATA_MANIFEST.json`, `data/README.md`.
- Acceptance criteria: stable hashes, plausible counts, required columns, unique chunks, valid reference links, page provenance and Unicode survival.
- Commands: exact `Copy-Item` operations; manifest and integrity tests.
- Tests: `tests/test_data_integrity.py`.
- Status: DONE
- Blockers: none.
- Evidence: 11 exact-copy hash checks; 3/3 data integrity tests pass; 1,185 chunk/vector rows and 161 unique references.

## PHASE 3 — Retrieval migration

- Objective: implement one BM25+dense+hybrid reference retrieval pipeline.
- Files: `retrieval/bm25.py`, `dense.py`, `hybrid.py`, `service.py`, `schemas.py`, `normalization.py`.
- Acceptance criteria: deterministic rankings, exact E5 prefixes, normalized query vectors, hard filters, citations, reference grouping, max 3.
- Commands: focused pytest and manual retrieval probes.
- Tests: BM25, dense and hybrid test modules.
- Status: DONE
- Blockers: none.
- Evidence: source-compatible BM25 artifact load, offline normalized E5 query encoding, deterministic weighted RRF, hard filters, reference grouping and citation tests pass.

## PHASE 4 — Multilingual handling

- Objective: support French, English, Arabic and mixed scripts without destructive Arabic transliteration.
- Files: `retrieval/language.py`, normalization hooks and UI direction behavior.
- Acceptance criteria: script/language/RTL/mixed detection; original evidence unchanged; no language hard filter.
- Commands: multilingual unit and retrieval probes.
- Tests: `tests/test_language.py` plus multilingual hybrid cases.
- Status: DONE
- Blockers: none.
- Evidence: French/English/Arabic/mixed tests pass; live Arabic is detected `ar`/RTL and mixed text is detected `mixed`; cross-language results are not filtered.

## PHASE 5 — Abstention

- Objective: deterministic, explainable, configurable no-evidence decisions.
- Files: `retrieval/abstention.py`, `config.yaml` thresholds.
- Acceptance criteria: accept supported queries; reject invalid/unsupported queries with explicit reason and diagnostics; zero results allowed.
- Commands: focused pytest and negative-query probes.
- Tests: `tests/test_abstention.py`.
- Status: DONE
- Blockers: thresholds remain prototype heuristics pending human labels.
- Evidence: focused acceptance/negative tests pass; live unsupported cooking query returns zero with `UNSUPPORTED_PORTFOLIO_SCOPE`.

## PHASE 6 — API

- Objective: expose health, config summary, search and bounded extraction preview via FastAPI.
- Files: `app/api/*`.
- Acceptance criteria: validation, Unicode, malformed JSON handling, filters, capped top-k, debug opt-in and no tool/instruction execution from query text.
- Commands: API tests and uvicorn health smoke.
- Tests: `tests/test_api.py`.
- Status: DONE
- Blockers: none.
- Evidence: six API tests pass, including health/config, Unicode, malformed JSON, invalid filters, prompt-injection-as-data and bounded PDF preview; live API demo passes.

## PHASE 7 — Frontend

- Objective: one real multilingual search UI backed only by the API.
- Files: `app/frontend/*`.
- Acceptance criteria: health/error/loading/no-result/result states; RTL evidence; citations; max 3; no fake data.
- Commands: npm install, lint, build, browser/API smoke.
- Tests: lint and production build.
- Status: DONE
- Blockers: none.
- Evidence: ESLint passes with zero warnings; Next.js 15.5.7 production build succeeds; live page returns HTTP 200 and uses the real API.

## PHASE 8 — Evaluation tooling

- Objective: provide honest templates and metrics for later human judgments.
- Files: `evaluation/*`.
- Acceptance criteria: required columns/metrics; empty qrels reports need for human labels; no fabricated official metrics.
- Commands: evaluator template run and metric unit tests where appropriate.
- Tests: empty-qrels behavior and known synthetic formula checks.
- Status: DONE
- Blockers: human relevance judgments are intentionally pending.
- Evidence: metric formula tests pass; empty template run returns `HUMAN_JUDGMENTS_REQUIRED` and `metrics: null`.

## PHASE 9 — Scripts and documentation

- Objective: safe Windows lifecycle, repeatable checks and internship-friendly docs.
- Files: `start.ps1`, `stop.ps1`, `scripts/*`, README and architecture/limitations/demo docs.
- Acceptance criteria: scoped PIDs, offline model startup, exact commands and actionable errors.
- Commands: environment validation, test script and demo check.
- Tests: script execution and documentation command verification.
- Status: DONE
- Blockers: none.
- Evidence: environment validation, test, start, demo and safe stop scripts execute successfully; README commands were exercised.

## PHASE 10 — Full validation and cleanup

- Objective: run the complete suite, inspect the target and prove source immutability.
- Files: `docs/PROGRESS.md`, `docs/FINAL_REPORT.md`.
- Acceptance criteria: Python tests, data checks, API smoke, frontend lint/build, demo check; clean Git status rules; baseline source hash unchanged.
- Commands: `scripts/test.ps1`, live demo smoke, aggregate source hash comparison, target inventory.
- Tests: all project checks.
- Status: DONE
- Blockers: none.
- Evidence: 24 tests pass; lint/build pass; live multilingual demo passes; ports close; all required paths exist; final source hash equals baseline exactly.
