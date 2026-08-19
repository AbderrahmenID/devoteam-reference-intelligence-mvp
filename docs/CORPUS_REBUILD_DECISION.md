# Corpus Rebuild Decision

Date: 2026-08-02

## Decision: TARGETED_REPAIR_V2

Preserve the immutable v1 corpus and prepare a separately versioned, lineage-complete v2 repair for only the affected documents/pages after human validation. A full corpus rebuild is not justified by the current evidence.

## Evidence

The exhaustive audit covered all 1,185 unique chunks across 132 source documents:

| Classification | Chunks | Percent |
|---|---:|---:|
| CLEAN | 425 | 35.86% |
| READABLE_WITH_LAYOUT_NOISE | 633 | 53.42% |
| CORRUPTED | 117 | 9.87% |
| WRONG_PAGE_ASSOCIATION | 0 | 0.00% |
| INCOHERENT_MIXED_CONTENT | 6 | 0.51% |
| NEEDS_HUMAN_REVIEW | 4 | 0.34% |

The combined severe automatic rate is 123/1,185, or 10.38%, inside the engineering guide's normal targeted-repair range. Intrinsic evidence quality passes for 1,060/1,185 chunks (89.45%). The issues are not a universal failure of chunk structure: 56 documents contain at least one severe chunk, while the largest concentration is 29 severe chunks in `contrat GIZ-AMOA 83400520 (1).pdf`. No canonical-document linkage mismatch was found. The two weaker page-association candidates are capability conflicts and require human confirmation.

Language impact is material but not systemic: severe findings include 1 of 12 Arabic chunks, 7 of 173 English chunks, 90 of 894 French chunks, and 25 of 106 mixed-script chunks. The mixed-script concentration and key evidence documents justify repair, but the high overall pass rate and intact provenance do not justify rebuilding every chunk and embedding.

## Required v2 repair procedure

1. Complete human review of every corrupted, incoherent, wrong-page candidate, prior reported-bad chunk, and deterministic clean control in `audit/corpus_quality/HUMAN_CHUNK_REVIEW.csv`.
2. Freeze the reviewed list of affected documents/pages. Do not edit v1 artifacts.
3. Re-extract only confirmed affected pages from the verified source snapshot using French, English, and Arabic OCR where needed.
4. Write corrected chunks as a new version while preserving stable reference IDs and original v1 lineage.
5. Rebuild BM25 for the complete corrected v2 chunk collection.
6. Regenerate embeddings for changed chunks only if row identity and numerical equivalence can be proven safe; otherwise regenerate the complete dense matrix for v2.
7. Rebuild the chunk lookup, validate hashes/shapes/order/provenance, and document v1-to-v2 mappings and removals.
8. Evaluate v2 only after reviewed development judgments exist; keep a protected held-out set untouched during tuning.

## Immediate runtime action

Continue serving immutable v1 with the hotfix's evidence-quality rejection and best-passage selection. Do not rebuild or overwrite corpus/index artifacts in this phase. Human corpus validation is required before the targeted repair list is final.
