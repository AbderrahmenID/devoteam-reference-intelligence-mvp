# AI reference narrative backend

## Phase 2.1 deterministic provenance binding

**The language model generates prose, not provenance. Reference identity,
evidence ownership and support assignment are deterministic backend
responsibilities.**

Phase 2.1 replaces the monolithic model contract with one prose-only generation
call per selected reference and one prose-only section synthesis call. The
backend loads each selected stable ID, creates a field-specific support plan,
passes only eligible material for each field, and constructs the canonical
`ReferenceNarrative` after generation. The model-facing schema contains no
`reference_id`, `support_ids`, source IDs, filenames, page IDs or provenance
fields.

```text
selected stable IDs
    -> trusted source bundles
    -> deterministic FieldSupportPlan per reference
    -> prose-only reference calls
    -> safe selected-reference capsules
    -> prose-only section call
    -> deterministic canonical envelope
    -> unchanged strict claim validation
```

### Field policies and minimum evidence

Policies are executable definitions in `reference_narrative/field_policy.py`.
They define allowed provenance classes, priority, absence behavior and a hard
maximum support count. The selector never attaches every source record.

| Field | Deterministic policy | Maximum support records |
|---|---|---:|
| `headline` | Mission title and client facts; completed or structured fallback | 2 |
| `short_description` | Mission/client facts plus at most one completed or structured record | 3 |
| `challenge` | Explicit challenge/context wording from structured, proposal or contractual context | 1 |
| `devoteam_contribution` | Completed evidence, attestation, contractual scope, then cautious structured scope; proposal scope excluded | 1 |
| `realisations` | Completed-work evidence or client attestation only | 1 |
| `benefits` | Completed/attested evidence containing explicit outcome language only | 1 |
| `why_relevant_to_opportunity` | Mission, offering and sector facts | 2 |

Proposal-only evidence cannot enter `realisations`. Benefits without explicit
outcome evidence and challenges without explicit context receive an empty
support set. Per-request JSON Schema adds `const: ""` or `maxItems: 0` for
fields with empty plans. If a provider nevertheless populates one, strict
validation emits blocking `EMPTY_SUPPORT_PLAN_VIOLATION`; validation is not
weakened or bypassed.

### FieldSupportPlan and backend envelope

`FieldSupportPlan` records the smallest selected support-ID set for each field
of one backend-selected reference. After parsing the prose-only draft, the
service inserts the selected stable ID and attaches the planned supports to
each populated field. Empty model fields receive no support IDs. A model cannot
omit or alter canonical identity, assign another reference's evidence, or
invent a support ID because none of those values occur in its output contract.

Validation also compares every populated field's attached supports with the
deterministic plan. A mismatch is blocking `PROVENANCE_PLAN_MISMATCH`.

### Safe reference capsules

Section synthesis never receives raw evidence bundles. For each selected
reference, the backend creates a capsule containing only deterministic client,
sector, country, period, offering and grounded capability facts. Every exposed
capsule value contributes its fact support ID to the section plan. The model
sees numbered selected capsules without stable IDs or support IDs. Capsules are
built only from the already validated selected bundle list.

### Safety guarantees versus model quality

Evaluation reports two independent metric groups.

Backend guarantees:

- reference identity coverage;
- deterministic support coverage for populated eligible fields;
- unknown support-ID count;
- unselected support count;
- empty-support-field violations;
- blocking provenance warning count.

Model quality:

- human-reviewed narrative usefulness;
- word-count conciseness indicator;
- exact repetition count and review status;
- French, English and Arabic quality review;
- end-to-end latency.

A perfect backend-guarantee score does not mean the prose is useful or
semantically valid. Strict hallucination, completion, outcome, numeric,
technology, named-person, certification, country, date, superlative, path and
internal-metadata checks continue after deterministic binding.

### Phase 2.1 live result

The same eight development cases were rerun on 2026-08-14 with the already
installed `qwen2.5-coder:7b-instruct`; no model was installed or downloaded.
All eight completed with schema-valid prose-only responses and zero structured
retries. Backend results were 100% reference identity, 100% deterministic
support for 23/23 populated eligible fields, zero unknown support IDs, zero
foreign/unselected supports, zero empty-plan violations and zero blocking
provenance warnings. Median end-to-end latency was 15.0 seconds.

Two cases passed the broader validator. Six remained blocked by model-level
wording: unsupported completion claims, named entities, client/sector drift and
similar semantic issues. French output sometimes contained English section
text; the Arabic case was produced in English. Several eligible narrative
fields were left empty, limiting usefulness. These are model-quality findings,
not provenance-binding failures. Phase 2.1 is therefore ready for controlled
model benchmarking, not for review-UI or production progression.

## Phase 2 live integration and validation

Phase 2 keeps the Phase 1 backend boundary unchanged and adds deterministic
quality metrics, warning severities, section-level safety checks, a repeatable
development evaluation harness and real local-model evidence. It does not add
UI, persistence, regeneration, export, template, PPTX or PDF work.

The warning severities are:

- `INFO`: a safe diagnostic such as an unavailable field intentionally left
  empty;
- `WARNING`: non-blocking weak-evidence context, such as a claim supported only
  by catalog, proposal, contract or unverified metadata;
- `BLOCKING`: unsupported, unselected, fabricated or unsafe content.

`export_eligible` is true only when no `BLOCKING` warning exists. It is returned
beside the existing inverse `export_blocked` field so a later review UI can use
an explicit positive gate without weakening validation.

Support coverage is a structural metric, not a semantic-accuracy score:

```text
supported populated fields / all populated narrative fields
```

A populated field counts as supported when it cites at least one known support
ID belonging to a selected reference; per-reference fields must cite their own
reference. Empty fields are excluded. The target is 100%, but a 100% value does
not prove that the wording is semantically correct.

The validator now also blocks:

- support owned by an unselected reference, including in section synthesis;
- unsupported ROI, certification, client-outcome and successful-delivery
  wording;
- unsupported portfolio superlatives and scale claims, including “extensive
  experience”, “market leader” and “hundreds of projects”;
- invented years through the numeric grounding check.

The prompt was changed only after the first real Qwen endpoint call returned a
schema-valid object with an empty `references` array. Prompt version
`reference-narrative-phase2-v3` now repeats selected IDs and their count in a
mandatory structural block, requires exactly one reference object per selected
ID in the same order, and states that structural completeness never permits
invented content. The deterministic validator remains the authority; the prompt
change did not make model text trusted.

### Development evaluation harness

The real-ID fixtures are in
`evaluation/reference_narrative/cases.json`. They cover BCT PCA, rich evidence,
sparse evidence, three-reference synthesis, French-to-English generation,
French, English and Arabic. Run fixture validation without a model:

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_reference_narrative.py --validate-only
```

Run the development suite with temporary process-local configuration:

```powershell
$env:REFERENCE_NARRATIVE_PROVIDER='ollama'
$env:REFERENCE_NARRATIVE_OLLAMA_URL='http://127.0.0.1:11434'
$env:REFERENCE_NARRATIVE_MODEL='qwen2.5-coder:7b-instruct'
.\.venv\Scripts\python.exe scripts\evaluate_reference_narrative.py
```

The harness calls the same `ReferenceNarrativeService` used by the API. It
writes one JSON result and one readable Markdown review per case under
`evaluation/reference_narrative/results/`, plus `development_summary.json`.
Every artifact is marked `DEVELOPMENT / NON-PRODUCTION`. Artifacts contain the
request, narrative, safe support summaries, validation, warning counts,
latency, populated/supported counts and coverage; they never contain trusted
source-bundle text.

On 2026-08-14, installed models were `qwen2.5-coder:7b-instruct` and
`gemma4:latest`; no model was installed or downloaded. Qwen returned structured
schema-valid responses through the real API and service. Gemma returned an
empty structured response and the real endpoint correctly emitted HTTP 502.
The eight-case Qwen suite completed with zero schema-envelope failures, median
latency 32.7 seconds, 0/8 valid cases, 0/8 export-eligible cases and 0% mean
support coverage. Most Qwen outputs omitted selected references and support
IDs; one introduced an unselected reference. The safety layer blocked every
case. These results are development evidence, not production approval, and the
backend is `NOT_READY` for review-UI progression with the currently installed
models.

## Phase 1 scope

Phase 1 adds a backend-only, post-selection narrative service. It does not alter
retrieval, rank or filter references, provide a frontend editor, or generate
PPTX/PDF files.

The retrieval engine determines which Devoteam references are eligible and
relevant. The narrative service is invoked only after the user explicitly
selects stable reference IDs. `TrustedV2Repository` then reloads all facts and
display-approved evidence from the manifest-pinned v2 assets; browser-provided
reference facts are never accepted.

Runtime boundary:

```text
selected stable IDs + opportunity controls
    -> TrustedV2Repository
    -> typed source bundles and short support IDs
    -> configured local narrative provider
    -> strict Pydantic JSON
    -> deterministic blocking validation
    -> development API response
```

## Trusted request

`POST /api/reference-narrative/generate` accepts only:

- `selected_reference_ids`
- `opportunity_title`
- `opportunity_description`
- `requirements`
- `target_language`: `fr`, `en` or `ar`
- `tone`: `commercial`, `executive`, `technical` or `concise`
- `audience`: `executive`, `technical`, `procurement` or `mixed`
- `detail_level`: `short`, `medium` or `detailed`

Pydantic forbids additional request fields. Selected IDs must be unique stable
64-character lowercase IDs. Unknown, ineligible, unauthorized, quarantined or
display-ineligible references fail through the existing v2 validation layer.

## Typed source bundles

Every selected reference produces a `ReferenceSourceBundle` with separate:

- deterministic facts;
- completed-work evidence;
- structured metadata scope;
- proposal or contractual scope;
- approved display evidence;
- fields for which no source support was found.

Sources carry one or more explicit types:

| Type | Meaning |
|---|---|
| `FACT` | Deterministic catalog fact such as client, country, year, sector or offering |
| `COMPLETED_WORK_EVIDENCE` | Approved evidence supporting that work was performed |
| `STRUCTURED_METADATA` | Structured catalog content |
| `PROPOSAL_SCOPE` | Proposed or technical-offer scope, not completion proof |
| `CLIENT_ATTESTATION` | Client attestation evidence |
| `CONTRACTUAL_SCOPE` | Contracted scope, not by itself proof of completion |
| `UNVERIFIED_METADATA` | Content that must not inherit completion status |

Catalog descriptions are deliberately marked structured/unverified scope.
Attestation text is represented separately. A record may carry multiple types,
but a proposal or contract never automatically receives
`COMPLETED_WORK_EVIDENCE`.

## Support IDs and model boundary

The backend allocates request-local identifiers `S1`, `S2`, and so on. Facts,
catalog scope and approved evidence all receive a support ID. The model may cite
only these IDs.

The prompt contains no source-relative paths, local paths, chunk IDs, embedding
IDs, BM25/dense/RRF scores, similarity values or raw retrieval diagnostics.
Source filenames are reduced to safe basenames. The API returns only support
summaries containing support ID, reference ID, provenance types, safe source
label and page; full source-bundle text is not returned to the browser.

## Prompt and structured output

The prompt states that missing sections may remain empty and explicitly
prohibits invented facts, results, benefits, percentages, ROI, technologies,
people, certifications and completion claims. It distinguishes catalog,
proposal, contract, attestation and completed-work evidence.

The output schema is `ReferenceSectionNarrative`. Section and per-reference
fields use:

```json
{
  "text": "Proposal-ready narrative or an empty string",
  "support_ids": ["S1"]
}
```

`challenge` may contain an empty string, while `realisations` and `benefits`
may be empty lists. No template-driven field is forced.

Malformed JSON or schema-invalid content triggers at most one controlled repeat
using the same trusted input. A second failure returns
`REFERENCE_NARRATIVE_INVALID_RESPONSE`; arbitrary prose and Markdown fences are
not silently parsed.

## Provider configuration

Configuration is read only from environment variables:

```env
REFERENCE_NARRATIVE_PROVIDER=disabled
REFERENCE_NARRATIVE_OLLAMA_URL=http://localhost:11434
REFERENCE_NARRATIVE_MODEL=
REFERENCE_NARRATIVE_CONNECT_TIMEOUT_SECONDS=10
```

`disabled` is the safe default and does not affect application startup, search,
or existing exports. Calling the development endpoint in disabled mode returns
HTTP 503 with `REFERENCE_NARRATIVE_DISABLED`.

For Ollama, set the provider to `ollama` and set an explicitly installed local
model name. The application never pulls or installs a model. The client accepts
loopback hosts only and calls `POST /api/chat` with `stream=false`,
`think=false`, temperature zero and the Pydantic JSON schema in `format`.
Only connection establishment is bounded (10 seconds by default). Narrative
response reads have no elapsed-time deadline, and transport calls are not
retried. A schema-invalid model response is repaired once through the existing
structured-output retry path.

## Deterministic validation

Generated content is not trusted automatically. The validator blocks content
when it finds:

- an unselected, missing, duplicate or reordered reference;
- an unknown support ID;
- per-reference content citing another reference's support;
- a non-empty claim with no support;
- a local path, retrieval score, chunk ID or internal stable identifier;
- an unsupported number or percentage;
- a conflicting known client, country, year, sector or offering;
- an unsupported technology or named entity/person;
- completion wording without completed-work evidence;
- proposal or contractual scope described as completed delivery;
- detailed completion claims not lexically supported by the cited attestation;
- a benefit without sufficient direct support.

Validation does not rewrite model text. Blocking warnings are returned alongside
the original structured narrative with `export_blocked=true`. Phase 1 has no
export operation, but this flag establishes the later approval/export gate.

## BCT provenance example

The catalog entry for `Banque Centrale de Tunisie / Opérationnalisation du PCA`
contains detailed activities including procedure workshops, five critical
applications, crisis communication and test planning. The approved client
attestation confirms the overall PCA operationalisation project but does not
repeat every detailed activity.

The source bundle therefore assigns different support IDs to the detailed
catalog scope and the attestation. A claim such as “Devoteam completed workshops
for five critical applications” cannot inherit completion proof merely by
citing both records: the completion details must occur in the completed-work
evidence or validation blocks the claim as
`COMPLETION_DETAIL_NOT_ATTESTED`.

## API response

A successful provider call returns:

- the structured narrative;
- `valid` and `export_blocked` validation status;
- detailed blocking warnings;
- safe source-support summaries;
- generation provenance with provider/model, UTC timestamp, prompt version and
  hash, selected IDs, retry count and warning codes.

No hidden reasoning or model thinking trace is stored or returned.

## Testing and limitations

Automated tests use fake providers and never require Ollama. Coverage includes
disabled mode, malformed output, all support-ID checks, multilingual output,
empty optional sections, multiple references, section synthesis, unsupported
claims, internal metadata scans, provider request options, and the BCT
provenance regression.

The validator is intentionally conservative but cannot provide a general proof
of semantic entailment. It combines typed provenance, exact support ownership,
numeric checks, controlled fact/technology checks and lexical completion
coverage. Ambiguous content remains blocked for user correction in a later
review phase.
