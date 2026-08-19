# AI Reference Narrative Studio

> **INTERNSHIP MVP / HUMAN REVIEW REQUIRED** — Phase 3

## Purpose

The Narrative Studio is the human review step between reference selection and later presentation generation:

Selected references → generate a local AI draft → review warnings → edit or regenerate → revalidate → approve → mark ready for presentation.

“The local language model acts as a proposal-writing assistant. It generates editable draft narrative from selected, source-grounded references, while deterministic validation and human approval control what can proceed to presentation generation.”

`qwen3.5:9b` is the selected local development drafting model. This is an internship-MVP choice, not a finding that the model is safe for autonomous publication. The Phase 2.2 benchmark limitations still apply.

## Configuration

The existing environment-backed provider abstraction remains in use:

```text
REFERENCE_NARRATIVE_PROVIDER=ollama
REFERENCE_NARRATIVE_OLLAMA_URL=http://localhost:11434
REFERENCE_NARRATIVE_MODEL=qwen3.5:9b
REFERENCE_NARRATIVE_CONNECT_TIMEOUT_SECONDS=10
```

`start.ps1` supplies these development defaults only when the corresponding environment variable is unset, so explicit local configuration still takes precedence. No model download is performed by the application. Missing Ollama, missing-model and connection-timeout errors are returned by the existing API error mapping and shown in the Studio. Once connected, narrative response reads have no elapsed-time deadline.

## Studio workflow

The Studio opens from the existing selected-reference basket and provides:

- opportunity title, description and requirements;
- French, English or Arabic output;
- executive, commercial, technical or concise tone;
- executive, technical, procurement or mixed audience;
- short, medium or detailed output;
- editable section introduction, overall storyline and reference rationale;
- an editable card for each selected reference;
- read-only client, country, sector, period and offering facts;
- field-adjacent and aggregate INFO, WARNING and BLOCKING findings;
- section-first progress followed by one sequential progress item per reference;
- completed-unit previews and isolated failed units that retain scoped regeneration;
- complete narrative, section-introduction and one-reference regeneration;
- session-scoped draft and approval state.

Manual edits are revalidated after a short debounce. Editing or regenerating after approval immediately clears approval.

## Backend authority

The browser sends only prose in validation and regeneration requests. It cannot submit reference IDs or support IDs inside an editable reference block. For every review request, the backend reloads selected references from `TrustedV2Repository` and reconstructs:

- canonical reference order and identity;
- `FieldSupportPlan` and section support plan;
- deterministic support assignment;
- safe read-only metadata;
- claim validation and export eligibility.

The browser never changes source facts or provenance. Retrieval, corpus, filters, indexes, field policies, source-type policies, capsules and claim-validation rules remain unchanged.

## API

- `POST /api/reference-narrative/generate` creates a complete local-model draft.
- `POST /api/reference-narrative/validate` accepts prose-only edits, rebuilds the canonical envelope and returns current validation.
- `POST /api/reference-narrative/regenerate` regenerates either the section introduction or one selected reference, then revalidates the result.

The validation endpoint does not require Ollama and remains usable when the drafting provider is unavailable.

## Approval and status

- `DRAFT`: AI-generated content with no edit and no blocking finding, awaiting explicit review.
- `NEEDS REVIEW`: a blocking finding exists, or content changed after generation/approval.
- `READY FOR PRESENTATION`: no blocking finding exists and the user explicitly approved the current content.

INFO and WARNING findings may remain after approval but stay visible. BLOCKING findings disable approval. Approval is stored only in the current browser session; there is no database or authentication.

`READY FOR PRESENTATION` is a workflow status only. Phase 3 does not connect approved narrative to PPTX or PDF generation. That integration requires a separate Phase 4 decision.
