# Targeted Repair and Candidate-Pool Plan

Date: 2026-08-02  
Branch: `fix/retrieval-evidence-quality`

## Imported inputs

| Workbook | SHA-256 | Import rule |
|---|---|---|
| `audit/corpus_quality/HUMAN_CHUNK_REVIEW_FINAL.xlsx` | `27c495ea6b653fa65f9329a268c7d2fb551cf793aa5c74860099674a7aa4b298` | Read-only; decisions are imported into additive JSON/CSV/Markdown artifacts. |
| `evaluation/judging/DEVELOPMENT_QUERY_INTAKE_FINAL.xlsx` | `d651d006b52cb850bbc0ff7bb7a8f201d7cd65d94ca9ea5ea9a7b38f05ab6db3` | Read-only; queries are provisional development inputs, not qrels or a gold set. |

Neither imported workbook will be overwritten. No blank relevance field will be inferred from metadata, retrieval scores, or the user's corpus-quality classifications.

## Safety boundary

- The v1 corpus, reference catalog, BM25 artifacts, embeddings, lookup, manifests, and runtime configuration remain immutable and available for rollback.
- `Devoteam_AI_CLEAN_PIPELINE` is read-only. Source pages may be read only when a validated repair record requires them.
- Repair outputs, if authorized after dependency validation, belong only under `data/versions/v2/`.
- Retrieval weights, thresholds, aggregation, model identity, and reranker state remain unchanged.
- No external OCR, embedding, or language-model service is allowed.

## Execution plan

1. Hash and structurally inspect both workbooks. Reject duplicate IDs, missing required columns, formulas, spreadsheet-injection values, unknown controlled values, invalid filter JSON, unsupported filters, and unreconciled chunk/reference IDs.
2. Re-run the unchanged v1 test, lint, production-build, start/demo/stop baseline. Record exact runtime-asset hashes and verify ports 3000/8000 close.
3. Import the 180-row chunk-review decisions without changing source values. Apply retrieval, display, exclusion, repair, linkage-quarantine, and provisional-confirmation policies exactly as specified.
4. Produce a repair manifest deduplicated by source document and page. Include every `REPAIR_OR_REEXTRACT` page once, preserve all affected v1 chunk IDs, references, source hashes/paths, automatic and reviewed classifications, and follow-up status.
5. Validate PyMuPDF, Tesseract executable and `fra+eng+ara` language packs, image-preprocessing dependencies, pinned local E5 model/revision, and free disk space.
6. If any required OCR dependency is missing, create `docs/OCR_DEPENDENCY_BLOCKER.md` with exact Windows installation/verification commands and stop before creating repaired text, v2 chunks, or v2 indexes.
7. Only if dependencies pass, re-extract approved pages, compare controlled digital/OCR strategies, assemble an immutable-lineage corpus v2, regenerate complete aligned BM25/E5 artifacts, and run v2 integrity/regression tests.
8. Validate and freeze the 50 development queries. Generate a v1/v2 union pool only after v2 is validated. Keep system origins/ranks/scores in a private mapping and leave all human relevance fields blank.
9. Stop after a validated blinded judging package. Precision metrics and tuning remain blocked until two independent reviewers and an adjudicator produce frozen qrels.

## Imported review policy

- `KEEP_RETRIEVAL_AND_DISPLAY`: retrieval and primary display permitted subject to normal gates.
- `KEEP_RETRIEVAL_ONLY`: retrieval permitted; primary display/export prohibited.
- `EXCLUDE_GENERIC_OR_NON_EVIDENTIARY_TEXT`: exclude from retrieval and evidence selection.
- `REPAIR_OR_REEXTRACT`: exclude unchanged v1 text from approved v2 retrieval and add its page to the repair manifest.
- `REVIEW_REFERENCE_LINKAGE`: quarantine; no automatic relinking.
- `HUMAN_CONFIRMATION_REQUIRED`: retain in an explicit provisional queue; never primary display; retrieval follows only the workbook's explicit approval field.

## Acceptance evidence

Every generated artifact must be reproducible from the two workbook hashes, v1 asset hashes, source snapshot ID `20260714T154731Z_129ff982c8`, and recorded commands. No v2 artifact will be created when source lineage, workbook reconciliation, OCR dependencies, or index alignment cannot be proven.
