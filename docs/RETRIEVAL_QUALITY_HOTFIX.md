# Retrieval quality and evidence rendering hotfix

## Scope freeze

This branch stops filter/export feature work while retrieval relevance, evidence selection, and readable rendering are repaired. The canonical parquet files, embeddings, BM25 index, source pipeline, and reranker configuration remain unchanged.

## Broken baseline

Captured on 2026-08-02 before ranking changes:

- Branch starting point: `main`; hotfix branch: `fix/retrieval-evidence-quality`.
- Complete test command: `.\scripts\test.ps1`.
- Result: 48 tests passed; frontend lint passed; Next.js production build passed.
- Evaluation status: `HUMAN_JUDGMENTS_REQUIRED` with zero reviewed queries/qrels.
- Reproduction query: `Références PCA pour une banque`.
- Baseline API result: 64 references passed the existing gate.
- Observed explanations included `Exact terms: banque, pour, une`, `Exact terms: references, pour`, and `Exact terms: pour`.
- Observed passages included corrupted OCR, isolated fragments, artificial line breaks, and unrelated contractual text.

The baseline demonstrates that existing tests covered system mechanics but did not protect meaningful-term matching or display-evidence quality.

## Reproducible diagnostic

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe scripts\diagnose_retrieval.py `
  --query "Références PCA pour une banque" `
  --candidate-limit 10 `
  --output .runtime\retrieval-quality-baseline.json
```

The JSON trace records query normalization, BM25 tokens, removed stopwords, BM25/dense/hybrid scores, exact-term behavior, matched terms, reference/chunk IDs, source/retrieval/display fields, evidence diagnostics, selected passages, and per-reference abstention decisions.

The captured pre-change trace is `.runtime/retrieval-quality-baseline.json`. Re-run the same command after the hotfix to produce the current trace; the implementation reports diagnostic version `retrieval_quality_hotfix_v2`.

## Root causes proven

1. `tokenize_multilingual` retained function words, so BM25 query scoring and raw set-intersection explanations treated `pour` and `une` as evidence.
2. `term_coverage` counted every normalized token, allowing stopword overlap to strengthen the per-reference abstention gate.
3. `chunks.parquet:chunk_text` served three incompatible roles: immutable source text, retrieval text, and browser display text.
4. The first fused chunk for a reference was displayed without OCR/readability assessment or a query-evidence gate.
5. Dense similarity could admit a passage even when its linked reference metadata described a different capability.
6. React rendered the API value faithfully; it did not create the corruption. The broken fragments already existed in the canonical chunk field.

## Implemented controls

- Maintained French, English, and Arabic stopword sets with Unicode normalization.
- Complete-token and phrase matching with corpus IDF/document-frequency thresholds.
- Preserved acronyms and named technologies, including PCA, API, SI, IAM, SOC, ERP, CRM, IPv6, API Gateway, ISO 27001, Kong, Azure, RGPD, and Kubernetes.
- Stopword-free BM25 query scoring and stopword-free evidence coverage/bonus.
- Runtime-only `retrieval_text`/`display_text` separation; parquet and indexes remain immutable.
- Deterministic PDF line-wrap cleanup, safe hyphen joining, repeated-line removal, source-faithful project/delivery excerpts, and embedding-prefix removal.
- Configurable `EvidenceQualityEvaluator` with explicit rejection reasons and debug-only diagnostics.
- Per-reference candidate-passage evaluation and deterministic best-evidence selection.
- Capability-concept compatibility between query, reference metadata, and evidence text.
- Structured professional explanations and bidi-safe frontend rendering.
- References with no usable passage are removed instead of being used to fill a page.

## Constraints

- No model retraining or embedding regeneration.
- No complete-corpus rebuild and no source parquet mutation.
- No changes outside this repository.
- Reranker remains disabled.
- Filters remain strict eligibility masks and cannot substitute for relevance.

## Acceptance status

See `docs/RETRIEVAL_QUALITY_HOTFIX_RESULTS.md` for before/after evidence, regression coverage, commands, and remaining limitations.
