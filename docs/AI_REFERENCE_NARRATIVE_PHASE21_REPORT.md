# Phase 2.1 deterministic provenance report

> **DEVELOPMENT / NON-PRODUCTION** — 2026-08-14

## Decision

**READY_FOR_MODEL_BENCHMARK**

This decision means the deterministic architecture is ready for controlled
comparison of approved local models. It does not approve the current Qwen prose
for a review UI, export or production use.

## Architecture delivered

- One prose-only model call per backend-selected reference.
- Executable per-field provenance policies with hard evidence limits.
- Deterministic `FieldSupportPlan` construction.
- Backend insertion of canonical reference IDs and support IDs.
- Per-request schema constraints for fields with no eligible support.
- Safe selected-reference capsules for section synthesis.
- Deterministic section support assignment.
- Strict plan-mismatch and empty-plan validation in addition to all Phase 2
  hallucination checks.
- Separate backend-guarantee and model-quality evaluation metrics.

The model-facing schemas contain no stable reference ID, support ID, source ID,
filename, page ID or provenance field. Attempted model injection of
`reference_id` or `support_ids` is rejected by the structured schema and may use
the existing single repair attempt; it cannot alter the canonical envelope.

## Field-policy summary

The field selector favors the smallest defensible set and applies hard maxima:

- headline: mission/client facts, maximum 2;
- short description: mission/client plus one eligible scope, maximum 3;
- challenge: one explicit context record, otherwise empty;
- contribution: one completed, attested, contractual or cautious structured
  record; proposal scope excluded;
- realisations: one completed/attested record only;
- benefits: one completed/attested record with explicit outcome language only;
- relevance: mission/offering/sector facts, maximum 2.

Section capsules include only non-empty deterministic facts for selected
references. Their support plan contains exactly the fact supports for the
values exposed to section synthesis, not the raw evidence bundle.

## Automated verification

- Focused narrative tests: 58 passed.
- Full Python suite: 147 passed.
- Explicit retrieval regressions: 14 passed.
- Automated tests require no Ollama service.
- Existing ROI, percentage, technology, person, certification, year, country,
  outcome, completion, proposal-scope, superlative, path, score and internal-ID
  regressions remain blocking.
- No retrieval, corpus, index, frontend, reference-pack, PPTX or PDF behavior
  was changed.
- `CLEAN_PIPELINE` was not touched.

## Live Qwen results

The unchanged eight-case development universe was executed with the already
installed `qwen2.5-coder:7b-instruct`. No model was installed or downloaded.

Schema and latency:

- completed cases: 8/8;
- schema failures: 0;
- structured retries: 0;
- median end-to-end latency: 15,048.5 ms;
- multi-reference latency: 36,538.6 ms.

Backend guarantees:

- reference identity coverage: 100% (10/10 reference instances);
- deterministic support coverage: 100% (23/23 populated eligible fields);
- unknown support IDs: 0;
- foreign/unselected support IDs: 0;
- populated fields with empty support plans: 0;
- blocking provenance warnings: 0.

Broader validation and model quality:

- valid/export-eligible cases: 2/8;
- warning totals: 10 INFO, 23 WARNING and 10 BLOCKING;
- blocking model-level findings: 5 unsupported-completion, 3 unsupported
  named-entity, 1 unsupported-client and 1 unsupported-sector warning;
- exact duplicate text count: 0 in the final run;
- total generated word count: 925;
- usefulness and language quality still require human review.

## BCT and multilingual observations

- BCT PCA identity and provenance remained correct; detailed catalog scope did
  not inherit completed-work provenance.
- The French BCT PCA case was valid and export-eligible, but it populated only
  three fields and mixed English into section prose.
- English outputs were structurally grounded but some contained unsupported
  named-entity or completion wording.
- The Arabic case returned English prose and an unsupported completion claim;
  this is an unambiguous current-model language/quality failure.
- The three-reference case preserved all three backend identities and correct
  support ownership, but Qwen left much reference prose empty and introduced
  unsupported client/sector/completion wording.

## Remaining limitations

- The installed Qwen model is not suitable for user-facing progression: only
  2/8 cases pass strict semantic validation, multilingual adherence is weak,
  and many eligible fields remain empty.
- Separate calls improve contract reliability but multi-reference latency is
  still significant.
- The validator is conservative and cannot prove general semantic entailment.
- Model usefulness, fluency and language adherence need blinded human review in
  a later approved benchmark phase.

The architectural provenance failure from Phase 2 is resolved. The next safe
checkpoint is model benchmarking only; no review UI or export progression is
authorized by this report.
