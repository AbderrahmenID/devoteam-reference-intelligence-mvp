# Remaining Human Work

Date: 2026-08-02

## 1. Validate corpus triage

Open `audit/corpus_quality/HUMAN_CHUNK_REVIEW.csv` and complete the blank human fields for all 180 rows. This packet contains every automatically corrupted or incoherent chunk, every wrong-page candidate, all five reported bad chunks, all 46 chunks involved in the reproduced bad search, items requiring review, and deterministic clean controls.

Confirm readability, mixed-script coherence, and page/reference association. Do not edit the automatic fields. Corrections belong only in the blank `human_*` columns.

## 2. Appoint evaluation roles

Name:

- one evaluation owner;
- two different Devoteam domain-expert labelers;
- an adjudicator who is neither labeler;
- a supervisor who approves the final boundary and decision.

## 3. Author the development queries

Complete all 50 rows in `evaluation/judging/DEVELOPMENT_QUERY_INTAKE.csv` using real or explicitly approved realistic information needs. Minimum coverage: 30 FR, 5 EN, 5 AR; at least 5 acronym-heavy, 5 sparse, and 5 ambiguous queries.

Each row must have an owner, business context, any mandatory filters, provenance, non-derivation confirmation, and explicit approval for development use. Do not copy queries from the corpus, bootstrap probes, or protected source Phase 5.1 workbook.

## 4. Freeze and judge candidates

After query intake approval, rerun candidate generation for the official development set, freeze file hashes, and give score/rank-blinded copies to both labelers. Each labeler independently assigns 0/1/2 relevance and evidence-quality observations. Preserve both original files.

The existing 74-row technical pool is only a workflow/training packet. Its judgments cannot unblock tuning or support official metrics.

## 5. Adjudicate and establish the boundary

Create an additive adjudication file for every disagreement. Freeze the adjudicated development qrels. Keep the source Phase 5.1 workbook as protected held-out test material; it is never allowed for threshold or configuration tuning.

## 6. Resume engineering

Once these inputs exist, rerun the baseline, calculate the specified metrics and multilingual subgroups, classify judged failures, and perform deterministic one-factor experiments. Only then select or reject a configuration and assess targets.
