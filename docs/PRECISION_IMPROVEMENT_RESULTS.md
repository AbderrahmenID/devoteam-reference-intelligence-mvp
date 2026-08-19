# Precision Improvement Results

Date: 2026-08-02  
Status: **STOPPED — HUMAN JUDGMENTS REQUIRED**

## Outcome

The verified retrieval/evidence hotfix remains the selected working baseline. No precision parameter was tuned because the required human-judged development set does not exist. This is a governance-correct stop, not a quality failure.

## Baseline

- 62 Python tests passed; frontend lint and production build passed.
- Full stop/start/demo/stop lifecycle passed.
- French, English, Arabic, mixed-language, and unsupported-scope technical smoke checks passed.
- Existing evaluator status: `HUMAN_JUDGMENTS_REQUIRED` with 0 queries, 0 qrels, and metrics `null`.
- Original PCA defect reproduction confirms stopword exclusion, corrupt evidence rejection, and clean passage selection.

These results establish software and regression correctness only. They are not precision, recall, ranking, or relevance claims.

## Corpus-quality decision

Decision: **TARGETED_REPAIR_V2** after human validation.

All 1,185 chunks were audited. Automatic triage found 117 corrupted chunks, 6 incoherent mixed-content chunks, 4 needing review, 633 readable with layout noise, and 425 clean. The combined severe rate is 10.38%; 89.45% pass the serving evidence-quality gate. No canonical-document linkage mismatch was found. The v1 corpus remains immutable and serving-time quality rejection remains active.

## False-positive categories

No query/reference false-positive categories were assigned because there are no human relevance judgments. Automatically labeling retrieved references as false positives would invent the missing ground truth. Intrinsic corpus categories are available separately in the exhaustive chunk audit and must not be confused with relevance errors.

## Experiments

No tuning experiments were run. The experiment registry is intentionally empty. Changing RRF weights, thresholds, candidate depth, reference aggregation, metadata gates, or evidence-selection weights without judged development qrels would be uncalibrated and violate the task's stop condition.

## Selected configuration

The verified hotfix configuration is retained unchanged as a provisional operational baseline. It was not selected through a relevance experiment. See `SELECTED_RETRIEVAL_CONFIGURATION.md` for exact values and status.

## Metric and latency changes

- Official relevance metrics before tuning: unavailable.
- Official relevance metrics after tuning: unavailable; no tuning occurred.
- Metric delta: not calculable.
- Query-latency delta: not calculable because no controlled before/after experiment ran.
- Technical suite wall time: 108.4 seconds for validation, 62 tests, evaluator guard, lint, and frontend build; this is not serving latency.

## Before/after hotfix example

For `Références PCA pour une banque`, the pre-hotfix failure exposed meaningless stopword matches and a corrupt BIAT page-2 passage. The verified baseline now sends only `pca` and `banque` to BM25, removes `references/pour/une`, rejects the corrupt page-2 chunk for deterministic quality failures, and selects a source-faithful BIAT page-1 passage beginning `ARTICLE 1 : OBJET`.

This example validates the reported defect fix; it does not prove portfolio-wide relevance precision.

## Failed experiments

None. Experiments were not authorized in the absence of human development judgments.

## Targets

Precision, recall, MRR, nDCG, no-answer false-positive rate, answerable zero-result rate, evidence acceptability, and multilingual subgroup targets were **not assessed**. No target-achievement claim is made.

## Remaining limitations

- No human-authored, human-judged development set.
- No adjudicated qrels or development/held-out split.
- Protected source workbook is draft and `FROZEN_TEST_ONLY_NO_TUNING`.
- Corpus repair candidates still require human readability/page-association validation.
- Tesseract is absent, so scanned-page OCR preview is unavailable in this environment.
- Five-per-category manual relevance inspection cannot be completed honestly until approved inputs and reviewers exist.

## Required next step

Complete `evaluation/judging/DEVELOPMENT_QUERY_INTAKE.csv`, appoint two independent labelers plus an adjudicator, generate/freeze the real development candidate pool, and complete adjudication. Precision work may resume only after those artifacts exist.
