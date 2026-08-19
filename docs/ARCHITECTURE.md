# Architecture

## Runtime flow

`Next.js UI → FastAPI → normalized metadata eligibility → masked BM25 + multilingual E5 → weighted RRF → reference grouping → per-candidate evidence gate → sort → pagination → cited results → optional template DOCX export`

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

## Normalized metadata and hard filters

`retrieval/metadata.py` builds a deterministic in-memory projection over the immutable reference catalog and chunk provenance. It canonicalizes only spelling/case/geography aliases, parses explicit project years into closed intervals, derives `ongoing` only from explicit markers, and attaches source languages, evidence types, controlled technologies and the seven template themes through auditable term rules. The parquet files are never edited.

AND applies across filter categories and OR within a category. Periods use interval overlap; an ongoing record uses the local current year as its runtime end. Unknown categories and unknown facet values fail with HTTP 422. A valid zero-sized eligible set returns `NO_ELIGIBLE_REFERENCE`.

BM25 and dense rankings are fused with weighted reciprocal rank fusion after the hard reference mask is converted to a chunk mask. Candidate depth exceeds the full chunk corpus so the complete eligible universe can be grouped.

## Reference grouping and citations

Chunk candidates are expanded through their canonical reference rows and grouped by stable `reference_id`. Each reference keeps a bounded set of supporting passages, while its best passage supplies the displayed original evidence, document, page, language and citation URI. Every grouped candidate passes through the evidence gate independently. All passing references are retained, sorted deterministically and only then paginated at 10, 20 or 50 items.

## Abstention

The deterministic gate uses lexical score, dense cosine, top dense mean, query-term coverage, retriever agreement, independently supporting passages, filter eligibility and explicit out-of-scope patterns. Thresholds live only in `config.yaml`. Reasons are explicit, diagnostics are opt-in and raw retrieval scores are labeled as components—not probability or confidence.

## API and frontend

FastAPI owns validation and exposes health, config summary, facets, paginated search, DOCX export and bounded extraction preview. The Next.js page calls only this API, uses `dir="auto"` or explicit RTL for evidence, and implements real loading, network-error, no-eligible, no-relevant and cited-result states. Selection is keyed by stable reference ID and persists across pages.

## Template-based export

`exporting/docx_export.py` verifies the immutable source-template hash, creates a task-local template working copy, validates the audited 18-table source structure and builds a clean Word package using the template's summary-first/table/annex visual system. Exports can include the summary table, detailed annex, source evidence passages and optional retrieval diagnostics. The package is reopened and checked for every selected reference before the API streams it, then the temporary output is deleted.

## Evaluation

The evaluator calls the same retrieval service, using an internal deeper ranking only for Recall@10/20 and nDCG/MRR. It calculates metrics only after human qrels are supplied. Operational results are evidence-gated and paginated; there is no fixed top-three cap.
