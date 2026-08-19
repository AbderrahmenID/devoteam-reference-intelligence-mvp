# Final report

## Outcome

The multilingual Devoteam reference retrieval MVP is demo-ready for a controlled local internship demonstration. It is not production-ready. It starts with one command, retrieves real corpus evidence in French/English/Arabic/mixed inputs, applies source-derived hard filters, independently gates the complete eligible reference universe, paginates all qualifying references and exports selected/all-relevant results to a template-audited DOCX. It can explicitly return zero results.

## Reused

- Validated Phase 4 `chunks.parquet` and `reference_catalog.parquet`.
- Phase 4 corpus statistics, filter values and manifest.
- Phase 5 pickle-free BM25 index/vocabulary.
- Phase 5 `(1185, 768)` normalized multilingual E5 embeddings and exact chunk lookup.
- Pinned local `intfloat/multilingual-e5-base` revision and the original `query: ` / `passage: ` contract.
- Behavioral patterns from source Unicode, filter, citation, extraction and deterministic-retrieval tests.

## Reimplemented

- Minimal standalone normalization, script/language/RTL handling and Unicode BM25 loader.
- Offline-only E5 query encoding, dense scoring, weighted RRF, hard filters and reference-level grouping.
- Deterministic abstention with explicit reasons and diagnostics.
- Offline digital-PDF extraction, `fra+eng+ara` OCR fallback, quality/provenance and page chunking.
- FastAPI API, single-page Next.js frontend, honest human-qrels evaluator and Windows lifecycle scripts.
- Deterministic normalized metadata/facet layer, paginated multi-reference search and template-based DOCX export.

## Excluded

Raw PDFs, canonical page duplication, chunks JSONL, FAISS binary, repair/rebuild orchestration, notebooks, ZIPs, historical reports, BRID and Phase 6–8 deliverables, rerankers, LLMs, fine-tuning, cloud deployment, authentication and database work.

## Final architecture

- One Python backend and one `RetrievalService` shared by API/evaluation.
- One Next.js frontend that calls only the real backend.
- One `config.yaml` for paths, model, retrieval, filters, thresholds, languages, API and ports.
- One `start.ps1` / `stop.ps1` lifecycle with scoped PID files.
- One minimal corpus/index copy with a SHA-256 data manifest.
- One immutable canonical Word-template copy with a configured SHA-256 contract.

## Data counts and integrity

- 1,185 unique chunks and vector lookup rows.
- 161 unique catalog reference IDs; 138 retrieval-eligible references with linked evidence.
- 134 source documents in the source Phase 4 manifest; 132 retrieval-eligible.
- 389 canonical eligible pages in the source Phase 4 manifest.
- 12,322 BM25 terms.
- 1,185 × 768 finite, L2-normalized passage embeddings.
- All selected source/destination hashes match; all chunk reference-row links exist; Arabic and accented French survive load.

## Validation results

- Environment validation: pass on Python 3.10.11, Node 24.11.1 and npm 11.10.0.
- Python: 48 tests passed after filter/export coverage; only five PyMuPDF SWIG deprecation warnings.
- Frontend ESLint: pass, zero warnings.
- Next.js production build: pass.
- Live FastAPI health and frontend HTTP 200: pass.
- Live demo: French, English, Arabic and mixed Arabic/French accepted; complete qualifying result totals and pagination; source passages/pages/URIs present.
- Facets: 138 eligible references and 11 canonical country values; filtered counts exclude orphaned/ineligible references.
- DOCX: selected subset, all-relevant validation path, summary/annex topology, Unicode content, citations, package reopening and template immutability pass.
- Abstention live path: zero results with `UNSUPPORTED_PORTFOLIO_SCOPE`.
- Invalid-filter live path: real HTTP 422, no fake frontend/backend result.
- Lifecycle: `start.ps1`, `demo_check.ps1` and `stop.ps1` pass; the final handoff leaves the verified app running on ports 3000/8000.
- Source immutability: final aggregate source SHA-256 exactly matches Phase 0.

No official retrieval-quality metric is reported. Empty qrels correctly produce `HUMAN_JUDGMENTS_REQUIRED` and `metrics: null`.

## Exact startup commands

```powershell
cd C:\Users\abder\Downloads\Devoteam_AI_Workspace\devoteam-reference-mvp
.\start.ps1
```

Open <http://127.0.0.1:3000>. To verify and stop:

```powershell
.\scripts\demo_check.ps1
.\stop.ps1
```

## Known limitations and blockers

- Tesseract plus `fra`, `eng` and `ara` data are available through the validated local dependency paths; scan quality remains source-dependent.
- Human multilingual/cross-language qrels and expert threshold calibration remain pending.
- No authentication/document authorization means controlled local use only.
- No official held-out quality evaluation or production-readiness claim.
- Reranker remains disabled and corpus coverage is finite.
- The in-app browser automation surface was unavailable; visual screenshot automation was not possible, although lint/types/build, frontend HTTP and live end-to-end API behavior pass.
- LibreOffice 26.2.5.2 is installed and validated for reference-pack PPTX-to-PDF conversion; the independent legacy DOCX renderer limitation remains separate.

## Remaining human work

1. Add expert-reviewed multilingual queries and qrels without labeling smoke tests as official.
2. Review Arabic/French cross-language relevance and calibrate abstention thresholds.
3. Install/test Tesseract language packs if scanned extraction preview is part of the demo.
4. Define authorization and deployment controls before any use outside a controlled local environment.
5. Visually review the UI in a normal browser at desktop/mobile widths.
6. Render representative small and maximum-size DOCX exports on a host with LibreOffice or another reliable renderer and inspect every page.

## Git handoff

The validated baseline is committed as `c378ad86b0917e01b3e24ac2b56eeecccd8691b0`. The filter/export extension remains visible as a reviewed working-tree change for an explicit follow-up commit.

## 2026-08-02 retrieval-evidence hotfix

The evidence path now distinguishes immutable source text, retrieval text, and derived display text. Multilingual stopwords and corpus-common terms cannot contribute to BM25 query scoring, exact-match bonus, query coverage, or match explanations. Every returned reference must have a quality-passing, query-supported passage selected from its candidate chunks, and recognized capabilities must agree with source metadata.

The reproduced `Références PCA pour une banque` failure no longer emits `Exact terms: pour` or `Exact terms: une`. The noisy higher-ranked BIAT OCR/table chunk is rejected and replaced by its readable project-object clause. Generic attestation/form text without meaningful query evidence is rejected. Professional explanation categories replace raw token lists.

Hotfix verification: 62 Python tests pass, frontend lint and optimized build pass, lifecycle and multilingual demo checks pass, the reranker is false, and immutable data hashes still match `DATA_MANIFEST.json`. Human qrels remain required before reporting official retrieval metrics. Full details are in `RETRIEVAL_QUALITY_HOTFIX_RESULTS.md` and `TEXT_FIELD_LINEAGE.md`.

The application is demo-ready under the stated limitations.

## 2026-08-02 direct retrieval runtime v2

The default application runtime now uses the immutable repaired v2 corpus through `config/baselines/SELECTED_RETRIEVAL_CONFIGURATION.yaml`; v1 remains byte-identical and directly runnable through `V1_ROLLBACK.yaml`. The selected engine uses weighted field-aware BM25, unchanged exact multilingual E5, 0.75/0.25 weighted RRF, best-plus-support reference aggregation, explicit relevance patterns and professional display-evidence cleanup.

The required regression artifact contains 255 complete rows (five weight pairs × 51 queries). All configurations had zero recorded filter leaks, duplicate IDs, missing citations, stopword explanations, legal/display-prohibited evidence, mojibake flags, unsupported-query returns or latency-limit violations. The selected configuration abstained on all 15 obvious no-answer scenarios. Four answerable-intent scenarios also abstained conservatively rather than bypassing filters or lowering the evidence gate.

The direct diagnostic, activation/rollback procedure, selected settings, results and limitations are documented in `RETRIEVAL_DIAGNOSTIC_GUIDE.md`, `RETRIEVAL_RUNTIME_V2.md`, `SELECTED_RETRIEVAL_CONFIGURATION.md`, `DIRECT_RETRIEVAL_IMPROVEMENT_RESULTS.md` and `REMAINING_LIMITATIONS.md`.

Final verification passed with 75 Python tests, seven dedicated v2 integrity tests, selected-environment validation, frontend ESLint and production build, standalone JSON diagnostic, live backend/frontend startup, multilingual demo checks and controlled shutdown. The live known PCA query returned 16 cited, evidence-gated references under field-aware v2. Ports 3000 and 8000 were closed after shutdown.

Human relevance labels remain unavailable. No official retrieval-quality metric or production-readiness claim is made.

## 2026-08-03 deterministic reference-pack generation

The application now turns only an ordered, manually selected set of stable v2
reference IDs into an editable Devoteam PPTX, matching LibreOffice PDF and
source-lineage JSON manifest. The browser sends no project facts. The backend
reloads structured metadata and display-approved evidence, rejects quarantined,
retrieval-only, unauthorized or incomplete-lineage inputs, and records output,
corpus, template, document, page and chunk hashes.

Implemented layouts are an editable cover, page-10-inspired divider, up-to-three
reference summary cards, one detailed slide per selected reference and one/two
evidence cards per annex slide. No full PDF background, invented logo, raw OCR,
internal score, local path, signature, contact or legal boilerplate is emitted.

Validated demonstrations:

- French one-reference pack: 5 PPTX slides / 5 PDF pages / 2.10 seconds.
- English three-reference pack: 8 / 8 / 2.96 seconds.
- Arabic four-reference pack: 10 / 10 / 3.81 seconds.
- French ten-reference pack: 21 / 21 / 7.28 seconds.

The automatic and manual visual audit passes bounds, overlap, title, footer,
numbering, card density, minimum evidence font, citation/linkage, logo aspect,
French accent and Arabic Unicode checks. See the `REFERENCE_PACK_*` documents
and `audit/reference_pack/VISUAL_VALIDATION.json`.

The reference-pack generator is deterministic and source-grounded. It uses
only user-selected Devoteam references, trusted structured metadata and
display-approved evidence with document/page lineage. No AI agent or
generative language model is used.

Exact start and stop commands:

```powershell
cd C:\Users\abder\Downloads\Devoteam_AI_Workspace\devoteam-reference-mvp
.\start.ps1
.\scripts\demo_check.ps1
.\stop.ps1
```

Validated demonstration roots:

- `generated/reference_packs/reference-pack-20260803T182559681026Z-94d67bc98e` — French, 1 reference, 5 slides.
- `generated/reference_packs/reference-pack-20260803T182601803848Z-3dcf7c9e9a` — English, 3 references, 8 slides.
- `generated/reference_packs/reference-pack-20260803T182604771525Z-c209e29b66` — Arabic, 4 references, 10 slides.
- `generated/reference_packs/reference-pack-20260803T182608631217Z-2b689f143e` — French, 10 references, 21 slides.
