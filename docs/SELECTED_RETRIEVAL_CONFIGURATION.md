# ENGINEERING_SELECTED_RETRIEVAL_CONFIGURATION

Date: 2026-08-02  
Status: **SELECTED BY TECHNICAL SAFETY CRITERIA — NOT HUMAN-CALIBRATED**

The executable source of truth is `config/baselines/SELECTED_RETRIEVAL_CONFIGURATION.yaml`. `start.ps1` and direct API startup use it by default. The immutable `config.yaml` remains the corpus-v1 rollback baseline and still matches its recorded SHA-256.

## Selected runtime

| Component | Selected value |
|---|---|
| Corpus | v2; 1,125 approved retrieval chunks; 138 eligible references |
| BM25 | field-aware reference score; k1 1.2; b 0.75 |
| Field weights | title 2.40; mission 2.00; services 2.20; description 1.50; technology 2.80; offering 1.00; sector 0.35; client 0.05; approved evidence 0.80 |
| Exact support | 0.08 per term, capped at 0.48; technology/acronym multiplier 2.50; whole-token matching |
| Dense | exact search over all eligible v2 chunks; pinned multilingual E5; 768 dimensions |
| Hybrid | weighted RRF; lexical 0.75; dense 0.25; RRF k=60; candidate depth 2,000 |
| Aggregation | `C_BEST_PLUS_SUPPORT`; best clean passage plus 0.0008 coherent-support bonus |
| Evidence | up to two clean, display-approved, source-linked passages; cross-language evidence floor 0.70 |
| Relevance | explicit lexical, semantic, retriever-agreement and exact-capability patterns |
| Pagination | every passing reference; stable pages of 10, 20 or 50 |
| Reranker/LLM | disabled / absent |

## Selection basis

All five requested weight pairs were run over the frozen 50 technical queries plus the known broken PCA query. Every pair had zero recorded filter, duplicate, citation, stopword, legal-evidence, display-policy, mojibake, unsupported-return or latency-limit issues. All 15 obvious no-answer scenarios abstained under every pair.

The 0.75/0.25 pair was selected because it retains strong field-aware lexical control while leaving meaningful capacity for cross-language E5. It tied 0.80/0.20 for the lowest total result volume (284 across 51 runs), produced a median of two results per query, and did not regress the known PCA, multilingual, strict-filter or unsupported examples. Weight changes affected result identities even where counts were unchanged, so the choice was based on the complete query set rather than one query.

Observed selected-run latency was 1,128 ms median and 1,791 ms p95 on this Windows CPU host. These are engineering observations, not a service-level objective.

No relevance labels or qrels were created. This selection does not establish higher precision, recall, MRR or nDCG.
