# Targeted Repair v2 Results

Date: 2026-08-02  
Status: **V2 AND BLINDED CSV POOL PASS; OFFICIAL XLSX BLOCKED BY TOOLING**

## Corpus repair and migration

- Tesseract 5.4.0.20240606 is available with official `fra`, `eng`, and `ara` language data.
- All 19 targeted source pages completed the controlled extraction workflow with source hash, document ID, page number, attempt text, diagnostics, and selection provenance preserved.
- Corpus v1 remains byte-identical to its recorded runtime hashes.
- Corpus v2 contains 1,125 retrieval chunks: 1,056 unchanged v1 chunks and 69 new repaired chunks.
- One proposed repaired chunk failed the evidence-quality gate and remains quarantined.
- The quarantine contains 53 rows in total.
- The v2 catalogue retains 161 stable reference IDs, of which 138 have retrieval-eligible evidence.
- Every v1 chunk has exactly one migration mapping row.
- BM25, dense embeddings, and the exact lookup contain 1,125 aligned rows.
- The dense matrix shape is `[1125, 768]`, and all vectors are L2-normalized.
- Model revision, passage/query prefixes, BM25 settings, hybrid weights, and abstention thresholds remain unchanged.

## Query and judging-pool preparation

- The 50-query development intake passes structural, duplication, language, type, formula, direct-copy, and filter validation.
- Owner-approved canonical filter overrides are recorded separately; the original workbook is unchanged.
- The frozen set contains 35 answerable and 15 no-answer scenarios across 17 French, 14 English, 14 Arabic, and 5 mixed-script queries.
- The blinded public pool contains 1,192 candidates with at most 25 per query.
- Private v1/v2, BM25, dense, hybrid, rank, score, and evidence-chunk provenance is stored separately.
- No relevance, confidence, reviewer-note, or adjudication field is prefilled.
- `DEV-041` has zero eligible candidates under its approved strict filter. Similarity was not allowed to bypass the filter.
- Candidate-pool validation passes with zero hard-filter violations, complete public/private reconciliation, and no retrieval-only evidence displayed.

## Verification

- Full Python suite: **70 passed**, 0 failed; five existing SWIG deprecation warnings.
- Evaluator guard: `HUMAN_JUDGMENTS_REQUIRED`; official metrics remain `null`.
- Frontend ESLint: PASS.
- Next.js production build: PASS.
- v2 multilingual lifecycle: French, English, Arabic, and mixed-script smoke queries returned cited evidence; unsupported-domain input abstained with zero results.
- `stop.ps1` stopped the recorded backend/frontend processes, and ports 3000 and 8000 were confirmed closed.

## Remaining blocker

The official eight-sheet judging workbook has not been created because the mandated `@oai/artifact-tool` spreadsheet runtime is unavailable. The validated blinded CSV and private manifests are ready for workbook assembly once that runtime, or an explicitly connected supported Excel authoring session, is available.

No precision, recall, MRR, nDCG, language-quality improvement, or production-quality claim is made.
