# Technical v1/v2 Comparison

Status: **PASS — descriptive comparison only**

This comparison uses fixed technical smoke inputs and no relevance judgments. It does not measure or claim precision, recall, MRR, nDCG, or language-quality improvement.

## Corpus and runtime identity

- v1 retrieval chunks: **1185**; v2 retrieval chunks: **1125**.
- v1 retrieval-eligible references: **138**; v2: **138**.
- E5 model revision, dimensions, prefixes, normalization, BM25 settings, hybrid weights, evidence thresholds, and abstention thresholds are unchanged.
- Both systems returned complete evidence citations for every emitted result and abstained on the unsupported-domain input.

## Fixed-query outputs

| Case | v1 decision | v2 decision | v1 total | v2 total | Top-10 set overlap | Same top reference |
|---|---|---|---:|---:|---:|---|
| TECH-FR-PCA | SUFFICIENT_EVIDENCE | SUFFICIENT_EVIDENCE | 23 | 23 | 7 | YES |
| TECH-EN-PCA | SUFFICIENT_EVIDENCE | SUFFICIENT_EVIDENCE | 20 | 21 | 7 | NO |
| TECH-AR-PCA | SUFFICIENT_EVIDENCE | SUFFICIENT_EVIDENCE | 22 | 21 | 8 | NO |
| TECH-MIXED-PCA | SUFFICIENT_EVIDENCE | SUFFICIENT_EVIDENCE | 14 | 16 | 8 | NO |
| TECH-FR-API | SUFFICIENT_EVIDENCE | SUFFICIENT_EVIDENCE | 12 | 10 | 9 | YES |
| TECH-EN-CLOUD | SUFFICIENT_EVIDENCE | SUFFICIENT_EVIDENCE | 3 | 4 | 3 | NO |
| TECH-FILTER | SUFFICIENT_EVIDENCE | SUFFICIENT_EVIDENCE | 4 | 4 | 4 | YES |
| TECH-NEGATIVE | UNSUPPORTED_PORTFOLIO_SCOPE | UNSUPPORTED_PORTFOLIO_SCOPE | 0 | 0 | 0 | YES |

Differences above are retrieval-output deltas, not correctness judgments. Relevance conclusions remain prohibited until independent qrels are completed and frozen.
