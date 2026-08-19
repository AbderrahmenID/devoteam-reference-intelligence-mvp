# Post-Hotfix Verification

Date: 2026-08-02  
Branch: `fix/retrieval-evidence-quality`  
Result: **PASS**

## Automated baseline

Command: `./scripts/test.ps1`

- Environment, configuration, immutable data, pinned local model, canonical template, and imports: PASS.
- Python tests: **62 passed**, 0 failed, in 49.44 seconds.
- Warnings: five harmless PyMuPDF/SWIG deprecation warnings.
- Human relevance evaluator guard: `HUMAN_JUDGMENTS_REQUIRED`, 0 query rows, 0 qrel rows, metrics `null`.
- Frontend ESLint with zero-warning policy: PASS.
- Next.js 15.5.7 optimized production build: PASS.
- Known environment limitation: Tesseract is absent; retrieval and digital-PDF extraction work, while scanned-page OCR preview is unavailable.

## Lifecycle verification

The previously running application was stopped, then the project was started through `start.ps1`. The health-controlled startup completed successfully. `scripts/demo_check.ps1` then passed all technical smoke checks:

| Check | Decision | Total references | Returned on page | Detected language |
|---|---|---:|---:|---|
| French UTF-8 | `SUFFICIENT_EVIDENCE` | 23 | 20 | fr |
| English UTF-8 | `SUFFICIENT_EVIDENCE` | 20 | 20 | en |
| Arabic UTF-8 | `SUFFICIENT_EVIDENCE` | 22 | 20 | ar |
| Mixed Arabic/French | `SUFFICIENT_EVIDENCE` | 14 | 14 | mixed |
| Explicit unsupported scope | `UNSUPPORTED_PORTFOLIO_SCOPE` | 0 | 0 | fr |

These inputs are technical smoke queries, not expert relevance labels.

After verification, `stop.ps1` stopped both backend and frontend successfully. The project is intentionally left stopped.

## Original-defect reproduction

Query: `Références PCA pour une banque`

The deterministic diagnostic recorded:

- Normalized query: `references pca pour une banque`.
- BM25 terms: `pca`, `banque`.
- Removed stopwords: `references`, `pour`, `une`.
- Retriever top-10 agreement: 3.
- Eligible corpus: 1,185 chunks linked to 138 references.
- Known corrupt chunk `38500b06...` from `BIAT_MCO.pdf`, page 2: rejected for excessive fragmentation, OCR gibberish, incoherent mixed script, and missing meaningful query evidence.
- The selected BIAT evidence is a clean page-1 project passage beginning `ARTICLE 1 : OBJET` rather than the corrupt page-2 text.
- Other retained PCA references expose source-faithful project/delivery passages with their original document and one-based page citation.

The full diagnostic is retained in `audit/hotfix-reproduction.json` and is also used to include every reproduced bad-search candidate in the human corpus-review packet.

## Required regression properties

- French, English, and Arabic stopwords do not enter BM25 terms or match explanations: PASS.
- Stopwords add no exact-match bonus: PASS.
- Protected acronyms, technology names, alphanumeric terms, and known phrases survive meaningful-term analysis: PASS.
- Corrupted passages are rejected: PASS.
- Clean evidence is selected from another chunk when available: PASS.
- References without readable evidence are removed: PASS.
- Hard filters cannot bypass relevance or evidence gates: PASS.
- Empty and unsupported queries return explicit abstention: PASS.
- Pagination, stable ranks, citations, and reference deduplication remain intact: PASS.
- Frontend rendering and production compilation remain intact: PASS.

## Verification conclusion

The retrieval/evidence hotfix is a valid working baseline for corpus auditing. Precision tuning remains unauthorized until adequate human-reviewed relevance judgments are available.
