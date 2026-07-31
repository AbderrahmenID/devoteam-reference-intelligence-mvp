# Final report

## Outcome

The multilingual Devoteam reference retrieval MVP is demo-ready for a controlled local internship demonstration. It is not production-ready. It starts with one command, retrieves real corpus evidence in French/English/Arabic/mixed inputs, returns at most three reference-level citations and can explicitly return zero results.

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

## Excluded

Raw PDFs, canonical page duplication, chunks JSONL, FAISS binary, repair/rebuild orchestration, notebooks, ZIPs, historical reports, BRID and Phase 6–8 deliverables, rerankers, LLMs, fine-tuning, cloud deployment, authentication and database work.

## Final architecture

- One Python backend and one `RetrievalService` shared by API/evaluation.
- One Next.js frontend that calls only the real backend.
- One `config.yaml` for paths, model, retrieval, filters, thresholds, languages, API and ports.
- One `start.ps1` / `stop.ps1` lifecycle with scoped PID files.
- One minimal corpus/index copy with a SHA-256 data manifest.

## Data counts and integrity

- 1,185 unique chunks and vector lookup rows.
- 161 unique catalog references.
- 134 source documents in the source Phase 4 manifest; 132 retrieval-eligible.
- 389 canonical eligible pages in the source Phase 4 manifest.
- 12,322 BM25 terms.
- 1,185 × 768 finite, L2-normalized passage embeddings.
- All selected source/destination hashes match; all chunk reference-row links exist; Arabic and accented French survive load.

## Validation results

- Environment validation: pass on Python 3.10.11, Node 24.11.1 and npm 11.10.0.
- Python: 24 tests passed; only five PyMuPDF SWIG deprecation warnings.
- Frontend ESLint: pass, zero warnings.
- Next.js production build: pass.
- Live FastAPI health and frontend HTTP 200: pass.
- Live demo: French, English, Arabic and mixed Arabic/French accepted; maximum three results; source passages/pages/URIs present.
- Abstention live path: zero results with `UNSUPPORTED_PORTFOLIO_SCOPE`.
- Invalid-filter live path: real HTTP 422, no fake frontend/backend result.
- Safe stop: backend/frontend recorded PIDs stopped; ports 8000/3000 closed.
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

- Tesseract plus `fra`, `eng` and `ara` packs are not installed. Scanned-page OCR preview is unavailable; retrieval and digital PDFs work.
- Human multilingual/cross-language qrels and expert threshold calibration remain pending.
- No authentication/document authorization means controlled local use only.
- No official held-out quality evaluation or production-readiness claim.
- Reranker remains disabled and corpus coverage is finite.
- The in-app browser automation surface was unavailable; visual screenshot automation was not possible, although lint/types/build, frontend HTTP and live end-to-end API behavior pass.
- Git `user.email` is unset, so the verified files remain uncommitted as required.

## Remaining human work

1. Add expert-reviewed multilingual queries and qrels without labeling smoke tests as official.
2. Review Arabic/French cross-language relevance and calibrate abstention thresholds.
3. Install/test Tesseract language packs if scanned extraction preview is part of the demo.
4. Define authorization and deployment controls before any use outside a controlled local environment.
5. Visually review the UI in a normal browser at desktop/mobile widths.

## Git handoff

After setting a real email identity, review and commit:

```powershell
git config --global user.email "your.real.email@example.com"
git add .
git commit -m "Build multilingual Devoteam reference retrieval MVP"
```

The application is demo-ready under the stated limitations.

