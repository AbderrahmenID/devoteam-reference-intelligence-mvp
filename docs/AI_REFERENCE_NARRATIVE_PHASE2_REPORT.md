# Phase 2 AI reference narrative validation report

> **DEVELOPMENT / NON-PRODUCTION** — 2026-08-14

## A. Changed files

- `reference_narrative/schemas.py`: explicit `INFO`, `WARNING` and `BLOCKING`
  severity plus `export_eligible`.
- `reference_narrative/claim_validator.py`: unselected-support checks,
  unsupported ROI/certification/outcome/success/superlative checks, year
  classification, weak-evidence warnings and unavailable-field information.
- `reference_narrative/quality.py`: deterministic populated-field support
  coverage.
- `reference_narrative/prompt_builder.py`: prompt version
  `reference-narrative-phase2-v3` and mandatory selected-reference structure.
- `scripts/evaluate_reference_narrative.py`: repeatable service-level evaluator.
- `evaluation/reference_narrative/cases.json`: eight real stable-ID cases.
- `evaluation/reference_narrative/results/`: one JSON and Markdown review per
  case plus the suite summary.
- `tests/test_reference_narrative_phase2.py`: Phase 2 metrics, severity, export,
  harness and hallucination/safety regressions.
- `docs/AI_REFERENCE_NARRATIVE_BACKEND.md`: Phase 2 behavior, command and live
  evidence documentation.
- `docs/AI_REFERENCE_NARRATIVE_PHASE2_REPORT.md`: this checkpoint report.

No retrieval, corpus, index, frontend, reference-pack, PPTX or PDF code was
changed for Phase 2. `CLEAN_PIPELINE` was not touched.

## B. Model selected and why

Installed models were inspected with `ollama list`. No model was installed or
downloaded. `qwen3:14b` was not installed. The available candidates were:

- `qwen2.5-coder:7b-instruct` (4.7 GB);
- `gemma4:latest` (9.6 GB).

Qwen was selected for the development suite because it was the only installed
candidate that returned schema-conforming JSON through Ollama structured
generation. It also fit fully on the available GPU during the run. It is not
considered suitable for progression based on the narrative results below.

## C. Live integration outcome

An isolated Uvicorn backend was started on `127.0.0.1:8010` with temporary
process-local environment variables and called through
`POST /api/reference-narrative/generate`.

Qwen returned HTTP 200, provider/model provenance, safe support summaries and
schema-valid `ReferenceSectionNarrative` JSON. The first hardened-prompt smoke
completed in 30.5 seconds with zero schema retries. It omitted the selected
reference, so validation returned `valid=false` and `export_eligible=false`.
No support text was exposed by the API.

Gemma was also checked because Qwen's narrative failed validation. Gemma
returned an empty structured content value; the API correctly returned HTTP 502
with `REFERENCE_NARRATIVE_INVALID_RESPONSE`. All isolated Uvicorn processes
were stopped after testing.

## D. Real evaluation cases executed

Eight cases used stable IDs loaded by `TrustedV2Repository`:

1. BCT PCA provenance regression in French;
2. rich BCT governance evidence in French;
3. sparse BMCI catalog-only evidence in English;
4. three-reference French section synthesis;
5. French BCT evidence to English narrative;
6. rich BCT evidence to English narrative;
7. sparse BMCI evidence in French;
8. BCT PCA evidence to Arabic narrative.

This covers the required BCT, rich, sparse, multi-reference, cross-language,
French, English and Arabic conditions.

## E. Schema-failure count

The Qwen eight-case evaluation had **0 schema-envelope failures** and **0
structured-output retries**. Separately, the Gemma API candidate check had one
empty structured provider response and returned HTTP 502.

## F. Median latency

Qwen median end-to-end service latency was **32,668.6 ms** across eight cases.
Observed case latency ranged from 17,960.2 ms to 64,387.8 ms.

## G. Support coverage results

The model populated 30 narrative fields across the suite and attached a valid
selected-reference support ID to 0 of them:

```text
0 supported populated fields / 30 populated fields = 0%
```

Every case had 0% coverage; the target is 100%. This metric measures support-ID
attachment only and does not claim semantic correctness.

## H. Warning counts by severity

Across the live suite:

- `INFO`: 1 (`UNAVAILABLE_FIELD_LEFT_EMPTY`);
- `WARNING`: 0;
- `BLOCKING`: 40.

Blocking codes were 29 `MISSING_SUPPORT`, 9 `MISSING_SELECTED_REFERENCE`, 1
`UNKNOWN_SUPPORT_ID` and 1 `UNSELECTED_REFERENCE`. Deterministic tests separately
confirm non-blocking `WEAK_SOURCE_SUPPORT` warnings.

## I. Hallucination-detection findings

Deterministic fake-provider stress tests confirm blocking detection for
unsupported ROI, percentages, technologies, client outcomes, named team
members, certifications, years, countries and successful-delivery wording.
Existing and new regressions also cover nonexistent support IDs, wrong-reference
support, unselected-reference support and proposal/technical-offer scope
represented as completed delivery. All blocking cases set
`export_eligible=false`.

## J. Section-level safety findings

Tests confirm that section claims can cite only selected-reference support,
generic supported portfolio wording is allowed, unsupported numeric claims are
blocked, and unsupported “extensive experience”, “market leader” and “hundreds
of projects” wording is blocked. Multi-reference ownership and empty-field
behavior are covered deterministically.

## K. Prompt changes

The first real Qwen response proved that the Phase 1 prompt did not force the
selected reference objects even though the response schema allowed an array.
Prompt version `reference-narrative-phase2-v3` therefore:

- carries the mandatory selected IDs and count outside the request block;
- requires exactly one reference object per selected ID in the same order;
- explicitly prohibits empty reference arrays when IDs are selected;
- reinforces that structural completeness cannot justify invented content;
- explicitly prohibits unsupported success claims, portfolio superlatives and
  technical-offer completion claims.

Qwen continued to omit or corrupt selected IDs, showing that prompt changes
alone do not make this installed model suitable. The deterministic safety gate
correctly remained authoritative.

## L. Remaining failure modes

- The only installed model that returns structured JSON does not reliably copy
  selected IDs or attach support IDs.
- The alternate installed model returns an empty structured response.
- Qwen produced 0% support coverage and no valid/export-eligible case.
- Median latency is high for an interactive review workflow.
- Typed provenance and lexical checks are conservative and do not prove general
  semantic entailment.
- The later review UI does not exist in Phase 2 and must not be started until a
  model passes the same suite.

## M. Recommendation

**NOT_READY**

Do not proceed to review-UI work with the currently installed models. Re-run
the unchanged development suite after an appropriate structured multilingual
instruction model is made available through an explicitly approved model
installation or runtime change. Progression should require all selected
references to be preserved, 100% support coverage, no blocking warnings, and
acceptable interactive latency on the real endpoint.

Verification at this checkpoint:

- focused narrative tests: 45 passed;
- explicit retrieval regressions: 14 passed;
- full Python suite: 134 passed;
- `git diff --check`: passed (pre-existing line-ending notices only).
