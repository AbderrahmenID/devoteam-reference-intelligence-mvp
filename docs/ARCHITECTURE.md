# Architecture

## Runtime flow

`Next.js UI → FastAPI /api/search → RetrievalService → hard filters → BM25 + multilingual E5 → weighted RRF → reference grouping → abstention → 0–3 cited results`

## Source data

The MVP reuses the validated Phase 4 canonical corpus: 1,185 page-constrained chunks linked to 161 reference-catalog rows. Evidence text, document filename, page number, language and Drive citation are preserved. Raw source documents and redundant page/JSONL exports are not copied.

## Offline extraction

`extraction/pdf_extraction.py` first attempts digital PDF text. Sparse pages use a Tesseract fallback configured as `fra+eng+ara`; OCR is never run during a query. Each preview page records filename, 1-based page, method, quality, original text, retrieval-normalized text, language/scripts and RTL. Chunking remains page-constrained. Preview uploads are capped at 5 MB and three pages.

## Chunk storage

`data/chunks.parquet` is the evidence corpus. `data/indexes/chunk_lookup.parquet` preserves the exact vector-row ordering. Startup validates alignment; data tests validate hashes, IDs, schemas, references, pages and Unicode.

## BM25

The pickle-free source BM25 index is loaded from NumPy arrays plus a JSON vocabulary. Its Unicode tokenizer folds French diacritics and normalizes Arabic only in a separate retrieval representation. Exact technologies, acronyms, clients and identifiers therefore remain strong signals.

## Multilingual dense retrieval

The query encoder loads the pinned local `intfloat/multilingual-e5-base` snapshot offline. It preserves the exact `query: ` prefix; the copied passage matrix was created with `passage: `. Query and passage vectors are L2-normalized and scored by cosine-equivalent dot product. No cloud API is called and no model is downloaded at startup.

## Hybrid retrieval and hard filters

BM25 and dense rankings are fused with weighted reciprocal rank fusion. Filters are applied before either score is ranked. Supported exact and year filters live in `config.yaml`; unknown filters fail closed. Document/query language is metadata, never a hard filter, which allows Arabic-to-French and English-to-French matches.

## Reference grouping and citations

Chunk candidates are expanded through their canonical reference rows and grouped by stable `reference_id`. Each reference keeps a bounded set of supporting passages, while its best passage supplies the displayed original evidence, document, page, language and citation URI. The API and UI cap final output at three distinct reference IDs.

## Abstention

The deterministic gate uses lexical score, dense cosine, top dense mean, query-term coverage, retriever agreement, independently supporting passages, filter eligibility and explicit out-of-scope patterns. Thresholds live only in `config.yaml`. Reasons are explicit, diagnostics are opt-in and raw retrieval scores are labeled as components—not probability or confidence.

## API and frontend

FastAPI owns validation and exposes health, config summary, search and bounded extraction preview. The Next.js page calls only this API, uses `dir="auto"` or explicit RTL for evidence, and implements real loading, network-error, no-result and cited-result states. It has no generation, login, dashboard, client-side search or synthetic fallback.

## Evaluation

The evaluator calls the same retrieval service, using an internal deeper ranking only for Recall@10/20 and nDCG/MRR. It calculates metrics only after human qrels are supplied. Operational UI/API output remains capped at three.

