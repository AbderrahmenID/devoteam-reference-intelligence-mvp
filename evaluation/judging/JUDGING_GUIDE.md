# Blinded Human Judging Guide

Date: 2026-08-02  
Status: **HUMAN INPUT REQUIRED — PRECISION TUNING BLOCKED**

## Important boundary

The included candidate pool uses only the MVP's pre-existing technical smoke queries. It validates the judging mechanics and gives reviewers a concrete training packet. It is **not** an official development set, and completing it alone does not authorize precision tuning or official quality claims.

The source project's 50-query Phase 5.1 workbook is protected as `FROZEN_TEST_ONLY_NO_TUNING` and has not been copied into this packet.

## Files

- `DEVELOPMENT_QUERY_INTAKE.csv`: 50 blank slots for real or explicitly approved realistic development queries.
- `TECHNICAL_QUERY_REVIEW.csv`: five existing smoke-query records with blank human query/no-answer fields.
- `TECHNICAL_CANDIDATE_POOL_BLINDED.csv`: score- and rank-blinded candidate references with blank judgment fields.
- `TECHNICAL_CANDIDATE_DIAGNOSTICS_INTERNAL.csv`: owner-only mapping to reference IDs, serving ranks, and score components. Do not give this file to judges until all judgments are frozen.

## Roles

Use two independent Devoteam domain experts and an independent adjudicator. Record stable reviewer IDs rather than changing prior rows. The evaluation owner freezes file hashes before judging and keeps the internal diagnostics separate.

## Query intake

For each `DEV-*` row, a domain expert supplies:

- a real information need or explicitly approved realistic scenario;
- language (`fr`, `en`, or `ar`);
- business context and any mandatory visible filters;
- query type (`STANDARD`, `ACRONYM_HEAVY`, `SPARSE`, or `AMBIGUOUS`);
- origin (`REAL_OPPORTUNITY` or `APPROVED_REALISTIC`);
- confirmation that it was not copied or derived from the reference corpus, bootstrap probes, or protected held-out workbook;
- explicit approval for development use and an owner.

Target 50 queries with at least 30 French, 5 English, 5 Arabic, 5 acronym-heavy, 5 sparse, and 5 ambiguous queries. Do not paste confidential opportunity text unless Devoteam has authorized it for this INTERNAL evaluation.

## Candidate relevance labels

Judge the blinded candidate against the query and evidence shown:

- `0`: irrelevant; does not address the information need.
- `1`: partially relevant; useful overlap, but not a strong primary reference.
- `2`: strongly relevant; directly and credibly supports the information need.

Set `wrong_evidence_chunk_yes_no` to `YES` when the reference may be relevant but the displayed passage is not suitable supporting evidence. Choose a failure category only when useful: `WRONG_SECTOR`, `WRONG_COUNTRY`, `WRONG_OFFERING`, `WRONG_CLIENT_TYPE`, `TOO_OLD`, `WEAK_EVIDENCE`, `OCR_OR_TEXT_CORRUPTION`, `FILTER_MISMATCH`, `DUPLICATE_REFERENCE`, `CROSS_LANGUAGE_FALSE_FRIEND`, `QUERY_TOO_BROAD`, or `OTHER`.

Do not infer relevance from result order: candidate rows are deterministically shuffled and do not expose rank or score.

## Independent review and adjudication

1. Freeze the query intake and generated candidate pool.
2. Give identical blinded copies to two experts; they work independently.
3. Preserve both completed files unchanged.
4. Create an additive adjudication file for disagreements. The adjudicator must not be either labeler.
5. Freeze adjudicated development qrels and a separate held-out set before any tuning.
6. Keep the protected Phase 5.1 source workbook out of development experiments.

## Unblocking condition

Precision work may resume only when the 50-row development intake has valid provenance and approval, candidates have two independent complete label sets, disagreements are adjudicated, and a protected held-out boundary is documented. Until then, baseline metrics, threshold experiments, and retrieval configuration changes remain prohibited.
