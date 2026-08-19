# Repository Cleanup Report

Status: **REPOSITORY_GITHUB_READY**

Date: 2026-08-19
Scope: `devoteam-reference-mvp` only. The sibling `Devoteam_AI_CLEAN_PIPELINE` was not modified.

## Outcome

The repository is reduced from 29,869 files / 1,488.83 MiB to 477 files / 74.78 MiB, excluding `.git`. The cleanup removed approximately 29,392 net files and 1,414.05 MiB (1.38 GiB) of local dependencies, caches, generated presentations, build products, temporary outputs, duplicated assets, obsolete code and superseded documentation.

No commit or push was performed. Five pre-existing frontend/UI modifications were preserved and validated with the cleanup.

## Complete repository inventory

| Path | Files | Size (MiB) | Classification | Purpose |
|---|---:|---:|---|---|
| `app/` | 24 | 0.33 | REQUIRED_SOURCE | FastAPI composition and Next.js frontend |
| `config/` | 3 | 0.01 | REQUIRED_RUNTIME | Selected retrieval configuration and rollback baselines |
| `data/` | 222 | 14.02 | REQUIRED_DATA / REQUIRED_RUNTIME | v1 rollback data, active v2 corpus, mappings and indexes |
| `docs/` | 25 | ~0.12 | REQUIRED_DOCUMENTATION | Current architecture, retrieval, export, template and validation documentation |
| `evaluation/` | 81 | 4.63 | REQUIRED_TEST | Reproducible evaluation inputs, judged pools and retained final results |
| `exporting/` | 2 | 0.01 | REQUIRED_SOURCE | Editable Word export support |
| `extraction/` | 4 | 0.01 | REQUIRED_SOURCE | Source extraction helpers used by tests/tooling |
| `reference_narrative/` | 20 | 0.33 | REQUIRED_SOURCE | Ollama copy generation, grounding, fitting, PPTX/PDF orchestration |
| `reference_pack/` | 8 | 0.08 | REQUIRED_SOURCE | Template-backed reference pack generation and validation |
| `retrieval/` | 16 | 0.12 | REQUIRED_SOURCE | BM25, multilingual E5, hybrid scoring, filters and repository access |
| `scripts/` | 24 | 0.21 | REQUIRED_SOURCE | Setup, preflight, testing and maintained evaluation/import tooling |
| `templates/` | 12 | 54.66 | REQUIRED_TEMPLATE | Approved source, derived, Word and mapping assets |
| `tests/` | 28 | 0.21 | REQUIRED_TEST | Python regression and integration tests |
| Root configuration/scripts | 8 | 0.01 | REQUIRED_SOURCE / DOCUMENTATION | Environment example, dependency manifests, README, start/stop scripts |
| Generated/cache/temp/local-model directories | 0 | 0 | GENERATED / CACHE / TEMPORARY / LOCAL_MACHINE_ONLY | Removed and ignored |
| Secret files | 0 | 0 | SECRET/SENSITIVE | No credentials or `.env` file retained |

The local `.git/` object database is 299.14 MiB and is not part of the working-tree size. All reachable Git blobs were audited; none exceeds 25 MiB.

## Removed

- Local/recreatable directories: `.venv`, `.runtime`, `.cache`, `.tmp`, root/frontend `node_modules`, Next build directories, pytest caches, egg-info, Python bytecode and temporary directories.
- Generated output: all `generated/reference_packs` decks, PDFs, manifests, previews and local export output.
- Bulky obsolete material: `audit/` and superseded temporary evaluation/render output while retaining the final reproducible evaluation assets under `evaluation/`.
- 33 conflicting or superseded development-history documents.
- 10 proven-unreferenced Narrative Studio/legacy reference-pack frontend modules and their obsolete tests. Current search, selection and `PresentationGeneratorModal` code remains.
- Three obsolete development scripts: the former environment validator (replaced by preflight), one-off v1/v2 comparison, and targeted page repair script.
- The empty root `package.json`; the frontend owns the canonical package metadata and lockfile.
- `templates/source/OT_DVT_SDSI__OrangeBANK.pdf`, a byte-identical unreferenced duplicate outside the canonical source directory. The approved source under `templates/reference_pack/source/` is untouched.

Tracked deletion count: 48 files. No source-control rename was required.

## Preserved runtime assets

Preflight verifies these 22 files so startup and tests do not depend on rebuilding the external pipeline:

- v1/rollback: `data/chunks.parquet`, `data/reference_catalog.parquet`, `data/indexes/bm25_index.npz`, `data/indexes/bm25_vocabulary.json`, `data/indexes/embeddings.npy`, `data/indexes/chunk_lookup.parquet`, `data/DATA_MANIFEST.json`, `data/source_metadata/PHASE_4_MANIFEST.json`, `data/indexes/PHASE_5_MANIFEST.json`, `data/indexes/retrieval_runtime.json`, and `data/V1_RUNTIME_ASSET_HASHES.json`.
- active v2: `data/versions/v2/chunks.parquet`, `reference_catalog.parquet`, the BM25 vocabulary/index, dense embeddings, chunk lookup, migration manifest, quarantine, chunk policy, v1-to-v2 mapping, and repair provenance.

The v1 hash baseline was moved from ignored `audit/` output into tracked `data/V1_RUNTIME_ASSET_HASHES.json`, removing the only hidden test dependency discovered by the fresh-machine simulation.

No corpus, BM25 index, dense embedding index or retrieval ranking was rebuilt or changed.

## Preserved templates

All 12 files under `templates/` remain purposeful. Nine are checked directly by preflight; the remainder are the original Word source, registry documentation and logo registry.

Approved source hashes before and after cleanup are identical:

| Source template | Bytes | SHA-256 before and after |
|---|---:|---|
| `templates/reference_pack/source/OT_DVT_SDSI__OrangeBANK.pdf` | 21,257,964 | `BC01334088C95C3796F1B98586E4980C66FD084C45174EEC23FF03195BB39334` |
| `templates/reference_pack/source/references sapmple and template.pptx` | 1,648,745 | `B8DBEA1191E2FA88F672F65BBF37424A7951F70AF5BC0E5BD7A253F21565C831` |

The 15.48 MiB `Template Ref.docx` and `reference_template.docx` files are intentionally byte-identical: one preserves the supplied filename and one is the stable configured runtime path.

## Portability, secrets and junk audit

- Absolute personal filesystem paths remaining: **0**.
- Remaining non-personal drive-literal matches: **5 intentional** — two standard Windows LibreOffice discovery candidates in template runtime configuration and three deliberately fake paths in redaction/sanitization tests. No runtime asset resolves through a user-specific path.
- Credential/private-key/token matches: **0**.
- Secret assignments: **0**.
- `.env` files: **0**; only `.env.example` remains.
- Junk directories (`__pycache__`, caches, venvs, `node_modules`, `.next`, `.runtime`, generated output): **0**.
- PPTX/PDF files outside `templates/`: **0**.
- Reparse points/junctions: **0**.
- Broken Markdown links: **0**.
- Historical source lineage in CSV, JSON and Parquet metadata uses the non-filesystem identifier `external://Devoteam_AI_CLEAN_PIPELINE/...`; it is not an absolute local path or a runtime dependency.

No real secret was removed because none was found. Generic words such as “password” inside corpus/evaluation text are data content, not credential assignments.

## Dependencies and startup

- Python dependencies remain explicitly pinned in `pyproject.toml` and `requirements.txt`; setup uses `pip install -e '.[dev]'`.
- Frontend dependencies remain locked with `package-lock.json` and install with `npm ci`.
- Next.js and its ESLint configuration were updated from vulnerable 15.5.7 to compatible 16.3.1. `npm audit` reports **0 vulnerabilities**.
- `scripts/setup.ps1` creates `.venv`, installs the Python project/dev dependencies and runs `npm ci`; it does not download model weights.
- `scripts/preflight.ps1` checks Python 3.10/3.11, Node 20.9+, packages, frontend installation, all 22 runtime files, nine runtime template assets, both approved hashes, pinned E5, Ollama `qwen3.5:9b`, and LibreOffice.
- `start.ps1` loads a repository-local `.env`, uses repository-relative paths, runs preflight, initializes retrieval, and starts only the recorded backend/frontend processes. `stop.ps1` was verified to leave zero listeners.

## Fresh-machine simulation

A clean copy was created with no `.git`, `.venv`, `node_modules`, `.next`, `.runtime`, caches or generated files.

| Check | Result |
|---|---|
| Create Python 3.10 virtual environment | PASS |
| Install pinned Python project and dev dependencies | PASS |
| `npm ci` from lockfile | PASS |
| Preflight / relative runtime asset resolution | PASS (22 runtime files, 9 runtime template assets) |
| Full Python suite | PASS — 233 tests |
| Frontend behavior suite | PASS — 20 tests |
| Frontend lint | PASS |
| Next.js production build / TypeScript | PASS |
| Retrieval regression | PASS — 255 result rows |
| Backend startup and health | PASS — `status=ok` |
| Frontend startup | PASS — HTTP 200 |
| Application stop | PASS — zero listeners on ports 3000/8000 |

Ollama, the pinned E5 revision and LibreOffice were present, so the optional live smoke test was run. A real indexed Banque centrale de Tunisie PCA reference generated a French Detailed Reference deck with `output_format=both`. The streaming API completed, all PPTX/PDF/manifest downloads returned HTTP 200, and the artifacts reopened as one PPTX slide and one PDF page with a completed manifest.

The smoke test exposed and fixed one non-feature regression: generated realization subitems longer than the existing 180-character slide limit are now word-safely fitted before Pydantic validation. A regression test was added, and the final full suite increased from 232 to 233 passing tests.

The evaluation command also correctly reports `HUMAN_JUDGMENTS_REQUIRED` because reviewed multilingual qrels are not supplied. This does not block application startup, regression checks or the retained MVP workflow.

## Test record

- Python: **233 passed**, 5 third-party SWIG deprecation warnings, 0 failed.
- Frontend: **20 passed**, 0 failed.
- Retrieval regression: **255 rows generated**, command exited 0.
- Detailed generation: **15 tests** in `test_detailed_generic_generation.py`.
- Presentation formats: **10 tests** in `test_presentation_formats.py`, covering the supported Compact and Detailed choices.
- PPTX: **12 tests** in `test_narrative_pptx.py`.
- Evidence/PDF: **12 tests** in `test_evidence_annex_pdf.py`.
- Frontend lint: PASS.
- Frontend production build: PASS.
- `npm audit --audit-level=high`: PASS, 0 vulnerabilities.
- `git diff --check`: PASS.
- Final v2 integrity check after binary lineage sanitization: PASS — 7 tests.

## GitHub size audit

Largest 20 working-tree files:

| # | File | MiB | Classification |
|---:|---|---:|---|
| 1 | `templates/reference_pack/source/OT_DVT_SDSI__OrangeBANK.pdf` | 20.27 | REQUIRED_TEMPLATE |
| 2 | `templates/Template Ref.docx` | 15.48 | REQUIRED_TEMPLATE source |
| 3 | `templates/reference_template.docx` | 15.48 | REQUIRED_TEMPLATE runtime |
| 4 | `data/indexes/embeddings.npy` | 3.47 | REQUIRED_DATA v1 rollback |
| 5 | `data/versions/v2/indexes/embeddings.npy` | 3.30 | REQUIRED_RUNTIME |
| 6 | `data/versions/v2/indexes/chunk_lookup.parquet` | 1.93 | REQUIRED_RUNTIME |
| 7 | `data/versions/v2/chunks.parquet` | 1.85 | REQUIRED_RUNTIME |
| 8 | `templates/reference_pack/derived/orange_pdf_pages_10_29.pptx` | 1.84 | REQUIRED_TEMPLATE runtime |
| 9 | `evaluation/judging/CANDIDATE_JUDGMENTS_BLINDED.csv` | 1.66 | REQUIRED_TEST evaluation |
| 10 | `templates/reference_pack/source/references sapmple and template.pptx` | 1.57 | REQUIRED_TEMPLATE |
| 11 | `data/indexes/chunk_lookup.parquet` | 0.82 | REQUIRED_DATA v1 rollback |
| 12 | `evaluation/results/RETRIEVAL_IMPROVEMENT_REGRESSION.csv` | 0.78 | REQUIRED_TEST retained result |
| 13 | `evaluation/judging/private/CANDIDATE_POOL_UNBLINDED.csv` | 0.75 | REQUIRED_TEST internal evaluation |
| 14 | `data/chunks.parquet` | 0.74 | REQUIRED_DATA v1 rollback |
| 15 | `evaluation/judging/private/CANDIDATE_POOL_SYSTEM_CONTRIBUTIONS.csv` | 0.68 | REQUIRED_TEST internal evaluation |
| 16 | `data/versions/v2/V1_TO_V2_CHUNK_MAP.csv` | 0.31 | REQUIRED_RUNTIME lineage |
| 17 | `app/frontend/package-lock.json` | 0.21 | REQUIRED_SOURCE dependency lock |
| 18 | `data/indexes/bm25_index.npz` | 0.17 | REQUIRED_DATA v1 rollback |
| 19 | `data/versions/v2/indexes/bm25_index.npz` | 0.16 | REQUIRED_RUNTIME |
| 20 | `data/versions/v2/indexes/bm25_vocabulary.json` | 0.13 | REQUIRED_RUNTIME |

Thresholds:

- Greater than 10 MiB: 3 files, all required templates.
- Greater than 25 MiB: 0.
- Greater than 50 MiB: 0.
- Greater than 90 MiB: 0.
- Greater than GitHub's normal 100 MiB per-file limit: 0 in the working tree and 0 in reachable Git history.

No Git LFS action is required. The working tree is 74.78 MiB; local `.git` objects make the current checkout 373.92 MiB on disk, but the largest reachable Git blob is only 20.27 MiB.

## Git change groups

- **DELETED (48 tracked):** 33 obsolete docs; 10 dead legacy frontend files/tests; 3 obsolete scripts; 1 empty root package manifest; 1 byte-identical duplicate template.
- **MOVED (0):** no risky package or asset relocation.
- **UPDATED (32):** hygiene/configuration, portability manifests and Parquet lineage, README, startup/test scripts, secured frontend dependency/configuration, durable integrity baseline references, the validated generation length guard, plus the five pre-existing search UI changes.
- **ADDED (5 including this report):** `data/V1_RUNTIME_ASSET_HASHES.json`, `docs/PROJECT_STRUCTURE.md`, `docs/REPOSITORY_CLEANUP_REPORT.md`, `scripts/preflight.ps1`, and `scripts/setup.ps1`.

## Remaining prerequisites and limitations

- Windows, Python 3.10 or 3.11, Node.js 20.9+, npm, Ollama with `qwen3.5:9b`, the pinned multilingual E5 cache, and LibreOffice are external prerequisites.
- Model files and caches are intentionally not stored in Git.
- Reviewed multilingual qrels remain human-owned evaluation input.
- Evaluation files under `evaluation/judging/private/` contain internal unblinded evaluation data; they are not credentials, but the repository should be hosted with access appropriate for Devoteam internal material.

There is no large-file, secret, portability, dependency, startup, test or generated-artifact blocker to normal GitHub push.
