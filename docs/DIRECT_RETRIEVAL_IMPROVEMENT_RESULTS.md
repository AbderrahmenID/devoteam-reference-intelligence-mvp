# Direct Retrieval Improvement Results

Date: 2026-08-02  
Status: **IMPLEMENTED AND TECHNICALLY VERIFIED**

“The retrieval engine was improved through corpus repair, field-aware lexical retrieval, multilingual dense retrieval, hybrid fusion, reference-level aggregation and conservative relevance/evidence gates. Human-labeled qrels were not available, so no official precision or recall claim is made.”

## Previous behavior

The pre-improvement runtime used one chunk-text BM25 field, 0.50/0.50 weighted RRF, maximum clean-chunk reference scoring and one displayed passage. Generic semantic neighbors could survive for obviously unsupported commercial domains, and some otherwise relevant snippets retained attestation/legal/contact tails. The known `Références PCA pour une banque` failure had previously exposed noisy OCR and meaningless stopword explanations before the earlier evidence hotfix.

## Implemented changes

- Activated manifest-verified corpus v2 through a reversible configuration switch without changing corpus v1 or v2 assets.
- Added a direct complete-run diagnostic (`python -m retrieval.diagnose --query ... --json`).
- Added separate BM25 fields for title, mission, services, description, technologies, offerings, sector, client and approved evidence. Duplicate source aliases are counted once.
- Preserved natural source text for unchanged exact multilingual E5 search.
- Compared all requested RRF weights and selected lexical 0.75 / dense 0.25.
- Compared maximum, top-two mean, best-plus-support and field-agreement aggregation. Selected best-plus-support because it rewards corroboration without excluding a genuinely strong single passage.
- Added four explicit passing patterns and deterministic rejection categories at reference level.
- Strengthened professional display derivation to remove signatures, contacts, headers/tails and legal boilerplate while retaining citations and Unicode.
- Replaced user-facing token/score explanations with traceable capability, technology, sector, evidence and filter statements.
- Retained every passing reference with exact totals and 10/20/50 pagination.

## Selected field and fusion settings

| Field | Weight |
|---|---:|
| Project title | 2.40 |
| Mission name | 2.00 |
| Services delivered | 2.20 |
| Project description | 1.50 |
| Technologies | 2.80 |
| Offerings | 1.00 |
| Sector | 0.35 |
| Client | 0.05 |
| Approved evidence | 0.80 |

Exact meaningful terms add 0.08 up to 0.48; technology/acronym matches receive a 2.50 multiplier. Stopwords receive no score, bonus or explanation. Country does not score. Hybrid fusion is weighted RRF (k=60), not raw BM25/cosine addition. Candidate depth is 2,000, which covers all 1,125 v2 chunks after the hard mask.

## Gates and aggregation

`C_BEST_PLUS_SUPPORT` stores the best clean evidence chunk, an optional second coherent chunk and a deterministic explanation. The relevance gate permits strong lexical evidence, strong semantic evidence with corroboration, lexical/dense agreement with direct evidence, or an exact capability/technology confirmed by project work. It rejects metadata-only, weak lexical+dense, single accidental semantic, corrupted, display-prohibited, boilerplate, contact/signature and invalid-lineage candidates.

## Before/after technical examples

| Query | Earlier observed behavior | Selected runtime |
|---|---|---|
| `Références PCA pour une banque` | noisy/boilerplate passages and stopword explanations in the original defect | 16 gated references; clean page citations; no stopword/legal-evidence issue |
| DEV-013 agriculture | 15 accidental results in the first improvement sweep | `UNSUPPORTED_PORTFOLIO_SCOPE`, zero results |
| DEV-023 English business continuity | zero results before cross-language evidence calibration | 5 clean cross-language results |
| DEV-041 Tunisia + Cloud + last five years | tempting semantic candidates outside mandatory filters | `NO_ELIGIBLE_REFERENCE`, zero results |

These are behavior examples, not relevance judgments.

## Regression outcomes

`evaluation/results/RETRIEVAL_IMPROVEMENT_REGRESSION.csv` contains 255 rows: 51 queries under each of five requested weight pairs. It records IDs, counts, evidence chunks, professional reasons, rejection counts/categories, abstention and latency.

- 5 configurations × 51 queries: complete.
- 15/15 obvious no-answer scenarios abstained in every configuration.
- Zero recorded hard-filter, duplicate, citation, stopword-explanation, legal-evidence, display-policy, mojibake, unsupported-return or >5-second latency issues.
- Selected pair: 284 cumulative results, median two per query.
- Selected latency: 1,128 ms median; 1,791 ms p95 on the local CPU host.
- Selected decisions: 32 sufficient-evidence, 14 unsupported-scope, 4 no-relevant-reference and 1 no-eligible-reference.

Four answerable-intent rows conservatively abstain; this is documented rather than lowering the gate to fill a page.

## Manual-free acceptance

Thirty categorized output inspections passed: five French (DEV-001–005), five English (DEV-018–022), five Arabic (DEV-032–036), all five mixed-script queries (DEV-046–050), five unsupported French scenarios (DEV-013–017), the three frozen hard-filter scenarios and two additional strict-filter searches. No meaningless reason, corrupted/fragmented or legal evidence, hard-filter leak, duplicate ID, missing citation, unrelated page-fill result or display-prohibited chunk was observed. Safe zero-result decisions were accepted rather than treated as failures.

## Verification

The final gate passed: 75 Python tests, seven dedicated v2 integrity tests, environment validation, frontend ESLint, optimized Next.js build, standalone JSON diagnostic, `start.ps1`, multilingual `demo_check.ps1`, live known-query verification and `stop.ps1`. Ports 3000 and 8000 were confirmed closed. The suite covers v1/v2 hashes, field BM25, stopwords/acronyms/whole tokens, hard filters/date overlap, aggregation, evidence restrictions, no-answer behavior, pagination, Unicode and citations.

## Remaining limitations

See `REMAINING_LIMITATIONS.md`. Most importantly, the technical query set has no relevance labels, so the selected configuration is an honest engineering default rather than an empirically calibrated optimum.
