# Precision Improvement Plan

Date: 2026-08-02  
Branch: `fix/retrieval-evidence-quality`

## Purpose and guardrails

This plan continues from the completed retrieval and evidence-quality hotfix. The immutable corpus artifacts, embedding matrix, BM25 artifacts, source PDFs, canonical template, and read-only source project are not tuning surfaces. Retrieval changes are authorized only after an adequate human-judged development set and a protected held-out boundary exist. Technical smoke checks are regression evidence, not relevance labels.

## Current serving path

1. The API validates the query and resolves metadata filters before retrieval. `ReferenceMetadataIndex.resolve_filters` returns eligible reference IDs; linked chunks are converted to a hard Boolean mask and intersected with the configured security-classification mask.
2. The query is normalized only for retrieval analysis. Multilingual stopwords and corpus-wide common terms are removed from BM25, while protected acronyms, technology terms, and known phrases are retained. The original query is passed unchanged to the pinned offline E5 encoder with the required `query: ` prefix.
3. BM25 and dense cosine scores are calculated over eligible chunks. Each retriever is deterministically ranked, with chunk ID as the tie-breaker.
4. Hybrid fusion is weighted reciprocal-rank fusion, not a raw-score sum:

   `fused(d) = 0.5 / (60 + rank_bm25(d)) + 0.5 / (60 + rank_dense(d))`

   The configured candidate depth is 2,000, which covers the current 1,185-chunk corpus after filtering. Global retriever agreement is the intersection of each retriever's top 10.
5. Fused chunks are mapped through `reference_rows_json` and grouped into eligible references. Each reference retains at most 12 candidate chunks for evidence evaluation. Reference ordering uses best fused score, then best dense score, then stable reference ID.
6. Candidate evidence is cleaned only for display; raw `chunk_text` remains the source and retrieval field. The evidence evaluator measures printable/alphabetic content, meaningful-word volume, token and line fragmentation, repetition, suspicious symbols, sentence completeness, detected script/language, query-term coverage, capability support, and project-delivery signals.
7. Evidence that has any rejection reason is excluded. Passing evidence is ranked by:

   `0.42*quality + 0.20*query_coverage + 0.15*dense_component + 0.08*metadata_support + 0.05*exact_term_bonus + 0.10*project_delivery_signal`

   One supporting passage is displayed per reference. Source document, one-based page, citation label, URI, and evidence language are carried from that selected chunk.
8. Reference-level abstention checks meaningful-query content, clean evidence, metadata/capability compatibility, lexical and semantic strength, cross-language support, retriever agreement, and independent passage count. Unsupported-scope phrases and empty/malformed queries have explicit deterministic reasons.
9. Structured match explanations include only meaningful whole-token/phrase matches, metadata field matches, capability matches, and semantic similarity. Removed stopwords cannot create an exact-match bonus or explanation.

## Hotfix summary

The hotfix corrected three connected defects:

- High-frequency multilingual function words were treated as relevance evidence and surfaced as exact matches.
- Retrieval text, immutable source text, and user-facing evidence text were conflated.
- The first fused chunk was displayed even when a cleaner, more coherent chunk existed for the same reference.

The implemented controls add corpus-aware meaningful-term analysis, an auditable evidence-quality evaluator, best-passage selection, metadata/concept compatibility, structured match reasons, source-faithful display derivation, and deterministic regression diagnostics. The current configuration has reranking disabled and uses the pinned 768-dimensional local E5 embeddings.

## Evaluation evidence currently available

- Data-integrity, retrieval-unit, API, filtering, export, multilingual, and evidence-quality tests.
- Reproducible French, English, Arabic, mixed-language, unsupported-scope, and known-corrupt-passage technical checks.
- Empty schema-valid evaluation templates in `evaluation/queries_multilingual.csv` and `evaluation/qrels_multilingual.csv`.

The existing evidence can establish software correctness and hotfix regression safety. It cannot establish precision, recall, ranking quality, false-positive rate, or threshold superiority because no reviewed relevance judgments are present.

## Known limitations

- Evidence-quality thresholds are engineering defaults, not human-calibrated operating points.
- The corpus has not yet been exhaustively classified for corruption, layout noise, mixed-script coherence, or page-association risk.
- OCR confidence is not currently a field in the serving chunk artifact, so it cannot be reconstructed or invented during audit.
- No official development/held-out query split has been identified yet.
- Cross-language relevance and Arabic evidence presentation have technical tests but no reviewed relevance labels.
- Current candidate and abstention thresholds must not be tuned against smoke queries or manually inferred relevance.

## Execution sequence

1. Re-run all automated tests, frontend lint/build, full start/demo/stop lifecycle, and the original defective queries. Stop immediately if the verified hotfix baseline fails.
2. Audit all 1,185 chunks using deterministic, explainable indicators. Produce chunk-level, document-level, corpus-level, and blinded human-review artifacts.
3. Select exactly one corpus action: preserve v1, targeted repair v2, or full rebuild v2. The decision must be driven by the exhaustive audit, not a sample.
4. Inventory every evaluation asset in this MVP and the read-only source project. Record provenance, counts, languages, reviewers, label status, synthetic/human status, leakage risk, and allowable use without inspecting any protected held-out query text.
5. If and only if an adequate human-judged development set exists, freeze a held-out set, record the baseline, classify failures, run one-factor experiments, and compare precision/recall/abstention/evidence metrics with deterministic tie-breaks.
6. If no adequate set exists, create a blinded judging workflow and candidate pool with blank judgment fields, then stop and request human review. No parameter change or official metric will be claimed.

## Permitted future changes after authorization

After adequate judgments exist, changes may be proposed to meaningful-term thresholds, lexical/dense RRF weights, candidate depth, reference aggregation, evidence selection, metadata compatibility, abstention thresholds, and deterministic tie-breaks. Each experiment must change one factor, record the exact configuration, and be rejected if it materially harms false-positive control, multilingual performance, evidence quality, or latency.

## Explicitly out of scope

- Modifying or regenerating `data/chunks.parquet`, `data/reference_catalog.parquet`, existing indexes, embeddings, source PDFs, or canonical templates before the corpus decision.
- Editing `Devoteam_AI_CLEAN_PIPELINE`.
- Introducing a reranker, online model download, synthetic relevance labels, or query generation as a substitute for human judgments.
- Looking at protected held-out query text during tuning.
