# Final MVP end-to-end validation

Validation date: 2026-08-15  
Scope: Phase 7 only - final end-to-end MVP validation  
Repository: `devoteam-reference-mvp`  
Protected source pipeline: `Devoteam_AI_CLEAN_PIPELINE` was not modified.

## 1. Final architecture

The validated technical flow is:

```text
Devoteam source documents
  -> trusted corpus v2
  -> Unicode field-aware BM25 + multilingual E5
  -> 75% lexical / 25% dense weighted reciprocal-rank fusion
  -> hard metadata filters
  -> reference aggregation
  -> relevance and evidence gates
  -> ranked, deduplicated stable reference IDs
  -> ordered user selection
  -> local qwen3.5:9b narrative draft
  -> deterministic provenance and claim validation
  -> mandatory human review, edit and approval
  -> orange_bank_compact or detailed_case_study
  -> editable PPTX with approved source-page annex
  -> LibreOffice PDF from that PPTX
  -> PPTX, PDF, reviewed content and generation manifest
```

The runtime remained local and offline. No hosted provider, database, authentication layer, ranking algorithm, reranker, third template, corpus rebuild or new corpus version was introduced.

## 2. Implemented workflow

The normal `start.ps1` workflow started the backend and frontend from a clean application runtime. Startup completed in 69.3 seconds, including loading the local dense model and indexes. Final runtime checks returned:

- backend `GET /health`: `status=ok`, `data_ready=true`, `model_available=true`, `service_loaded=true`, `reranker_enabled=false`;
- frontend `GET http://127.0.0.1:3000`: HTTP 200, title `Devoteam Reference Finder`;
- corpus: v2 selected configuration;
- BM25 and dense indexes: present, aligned and loaded without a rebuild;
- Ollama: 0.32.13 at the loopback endpoint;
- drafting model: `qwen3.5:9b`, digest `6488c96fa5fa...`, 9.7B parameters, Q4_K_M;
- Python 3.10.11, Node.js 24.11.1 and npm 11.10.0;
- Tesseract with `fra+eng+ara` and LibreOffice were available.

Pre-existing modified and untracked worktree content was preserved. Phase 7 added this report and generated runtime validation artifacts only.

The in-app browser service exposed no usable browser instance during validation. Consequently, no claim is made that a person manually clicked the rendered UI in this environment. The frontend itself loaded over HTTP, and its selection, Narrative Studio, validation, approval-reset and two-format behavior were exercised by 30 automated UI/state tests and the live API workflow.

## 3. Retrieval configuration and validation

The active file is `config/baselines/SELECTED_RETRIEVAL_CONFIGURATION.yaml` with:

- corpus version `v2`;
- `intfloat/multilingual-e5-base`, pinned revision `a114a4100c6714cf21651971eefe9191a4415dbb`, 768 dimensions, local files only;
- field-aware Unicode BM25;
- lexical weight 0.75 and dense weight 0.25;
- `C_BEST_PLUS_SUPPORT` reference aggregation;
- hard filters before ranking;
- evidence-quality, relevance and abstention gates;
- reranker disabled.

Live searches covered French, English, Arabic, mixed Arabic/French, an English-to-French cross-language query, `PCA`/`PCI` acronyms and explicit no-answer cases. BM25, dense and hybrid diagnostic candidate lists were non-empty for the PCA/PCI case. The diagnostic showed BM25 scores, dense cosine scores, 75/25 fused scores, aggregation decisions, rejected evidence and final evidence-gated references. Unsupported French, English and Arabic queries returned zero results with explicit abstention reasons.

Repeated identical searches returned identical ordered stable IDs. No duplicate reference ID was observed. Display evidence included a quotation, source document, source page and citation; retrieval-only passages rejected for display did not leak into displayed results.

The explicit regression produced 255 rows: 51 technical queries across each of five engineering weight configurations. The selected 75/25 configuration returned sufficient evidence for 32 rows and abstained safely for 19; median latency was 1,053.71 ms and p95 was 1,357.34 ms. There were zero technical issues. These counts are technical behavior only, not official relevance metrics.

## 4. Facets, filters and provenance

The unfiltered facet endpoint reported 138 eligible references. Facets were available for country, sector, client, offering, service nature, technology, status, evidence availability/type, language, themes, business unit, data-quality status and period (2011-2022 in the current data).

The live PCA validation established OR-within-category and AND-across-category semantics:

- country `Tunisie OR Cameroun` plus offering `PCA/PCI`: 14 retained references from both countries;
- the same filter plus sector `Banque`: 7 references, all Tunisian banking PCA/PCI references.

Exact live checks also passed for client, technology, status, period, sector, country and offering. A 2016-2022 interval correctly retained overlapping projects, including a 2015-2016 project. Corpus/facet counts were kept separate from query-result totals.

Two BCT records remained distinct:

- `38f6543...`: `Opérationnalisation du PCA de la BCT`, BCT, Tunisia, banking, PCA/PCI, 2022, with a client attestation on source page 1;
- `f88d0ed...`: `Mise en place d'un plan de continuité de l'activité`, BCT, Tunisia, banking, PCA/PCI, 2022, with its own attestation and source page 1.

Structured catalog scope and attestation evidence were not silently merged. Detailed scope can support proposed or described activities; an attestation supports only what its displayed page actually proves.

## 5. AI narrative workflow

Two live local drafting calls were completed:

- French, four selected PCA/PCI references: 134.76 seconds;
- English, one selected BCT reference: 24.34 seconds.

Both returned schema-valid structured envelopes with the exact backend-selected reference IDs and deterministic support plans. The model did not control identities or provenance. The French draft produced blocking findings for unsupported named entities and unsupported completion language. The English draft also produced a blocking unsupported claim. These failures were contained: neither draft was export-eligible.

The human-review sequence was then exercised:

1. an unsafe edit introduced `400% ROI`, `NASA` and unsupported completion wording;
2. validation reran and returned blocking warnings;
3. presentation generation rejected the content;
4. unsafe claims were removed and source-attested wording retained only where valid;
5. validation returned `valid=true`, `export_eligible=true` with informational empty-field notices;
6. the narrative was explicitly approved as `READY_FOR_PRESENTATION`.

The frontend test suite confirms that any edit or regeneration after approval clears readiness and requires revalidation/reapproval. Empty unsupported fields remain allowed. The validator mitigates drift but does not make the local model an autonomous authority.

## 6. Selection and human-in-the-loop controls

Selection behavior is session-scoped and ordered. Automated tests verified:

- one-reference selection;
- four-reference ordered selection;
- stable IDs across pagination and session hydration;
- no duplicates;
- explicit reorder, remove and clear operations;
- invalid or duplicate persisted values are discarded;
- the compact optional bottom selection bar;
- state is accepted only for the same selected reference set.

The backend reloads trusted facts for every validation and export. Browser-editable payloads contain prose only; reference IDs, support IDs, source paths and evidence identity are not editable fields. Approval is blocked when any blocking finding remains.

## 7. Supported presentation formats

Exactly two template IDs are supported:

1. `orange_bank_compact`
2. `detailed_case_study`

Both final artifacts were generated from the same approved narrative, the same four selected IDs and the same deterministic evidence pages. Switching format did not call the model. The shared reviewed-content SHA-256 was:

`404843f15c63b7f288de462aff3eb7584cc48e73373fcc5df8ccd090538a9df9`

### Orange Bank compact

Generation ID: `narrative-pptx-20260815T141149587767Z-c2818edd64`

- 3 narrative slides: one section slide and two balanced two-reference summary slides;
- 4 evidence slides;
- 7 total PPTX slides and 7 PDF pages;
- client, country, mission and trusted scope displayed in selection order;
- administrative attestation prose was omitted from compact cards with the explicit `COMPACT_ADMINISTRATIVE_REALISATION_OMITTED` warning;
- no sample content or incorrect logo was found;
- native editable PowerPoint text was present.

PPTX SHA-256: `59fddb76214da3f2529fc2ef5ef074f58b3c7f551a89d98351b0e34877538fcf`  
PDF SHA-256: `3f2db0eee3273c7a2cd52aa8ee41b4678f86c6be18eb1ce164dae3f628d94388`

### Detailed case study

Generation ID: `narrative-pptx-20260815T141153344131Z-3d1270f423`

- one section slide;
- one native editable narrative slide per selected reference;
- 4 evidence slides;
- 9 total PPTX slides and 9 PDF pages;
- title, client, country, sector, period and offering preserved;
- approved `Réalisations` use native PowerPoint bullets;
- unsupported challenge and benefit sections remained empty rather than being invented;
- no sample content, clipping or unreadable text was found.

PPTX SHA-256: `91a0a5eb01f0b687a383736c9c2c693594af1bdc711139531b77d807888f88bd`  
PDF SHA-256: `5c5d51b3951811ae8716d52d022e92eb30c6e9bee21810cc38a5453536c0a3c6`

All 16 final pages were rendered from the LibreOffice PDFs and inspected individually. PPTX package inspection found 67 editable text shapes in Compact and 49 in Detailed. Both presentations reopened successfully with `python-pptx`.

## 8. Evidence grounding and manifests

Each format used the same four evidence selections, in the same reference order:

1. BCT operationalization attestation, page 1;
2. BCT PCA implementation attestation, page 1;
3. TRADEX PCA attestation, page 1;
4. BTK PCA acceptance evidence, page 1.

Every manifest records `pdf_page_render`, `rendered_source_image=true`, `aspect_ratio_preserved=true` and `source_hash_validation=PASS`. No extracted-text fallback was used. Slide content exposes only a safe source display name and page number; no local path, chunk ID or retrieval score appears on an annex slide.

Both manifests contain the correct generation ID, template ID/display name, reviewed-content hash, selected stable IDs, corpus version, narrative/evidence/total slide counts, reference-to-slide and evidence mappings, overflow status, PDF validation, artifact hashes and warnings. No API secret or inappropriate local path was found. Artifact hashes were independently recomputed and matched the manifests.

PPTX and PDF page counts and order agree. No blank page was detected. French accents and other Unicode text were preserved. PDF generation used LibreOffice from the exact final PPTX; there is no separate PDF layout implementation.

## 9. Tests and negative behavior

Final automated totals:

- Python: **190 passed**, 0 failed, 5 third-party deprecation warnings, 41.37 seconds;
- frontend: **30 passed**, 0 failed;
- frontend lint: passed with zero warnings;
- frontend production build: passed;
- explicit retrieval regression: **255 rows**, zero technical issues;
- environment validation: passed;
- live UTF-8/demo smoke check: passed;
- artifact safety audit: passed;
- manifest/file hash audit: passed;
- page-by-page visual inspection: 16/16 pages inspected, no blocking defect.

Live API negative checks returned understandable HTTP 422 errors for unapproved narrative, blocking validation findings, invalid template ID, invalid reference ID and duplicate selections.

The Python suite additionally verifies fail-closed behavior for missing evidence, hash mismatch, unsafe/unapproved evidence page, wrong evidence/reference relationship, PPTX overflow, failed PDF conversion, changed approved reference sets, unknown/wrong support IDs, internal path/chunk/score leakage, missing Ollama model, Ollama timeout and malformed model output. Blocking failures leave no misleading completed artifact directory.

No Phase 7 application bug was found, so no product code was changed and no bug-fix entry is required.

## 10. Runtime performance

Observed on this local Windows validation host:

| Operation | Observed result |
|---|---:|
| Full application startup and health readiness | 69.3 s |
| Selected 75/25 retrieval regression median | 1,053.71 ms |
| Selected 75/25 retrieval regression p95 | 1,357.34 ms |
| French qwen3.5:9b draft, 4 references | 134.76 s |
| English qwen3.5:9b draft, 1 reference | 24.34 s |
| Final Compact PPTX + PDF | about 3.65 s |
| Final Detailed PPTX + PDF | about 3.31 s |

These are single-host technical observations, not production service-level objectives.

## 11. Known limitations

- `qwen3.5:9b` is a local drafting model.
- Human review and explicit approval are mandatory.
- The model may produce incomplete or incorrect draft wording.
- The validator mitigates known drift patterns but cannot prove arbitrary semantic truth.
- Official business-relevance metrics require expert qrels.
- Only `orange_bank_compact` and `detailed_case_study` are supported.
- Evidence must be locally resolvable, hash-valid and approved for display.
- Approval/session state is browser-session scoped; there is no database, authentication or authorization layer.
- The application is an internship MVP for a controlled local environment, not a production deployment.

## 12. Supervisor-ready demo procedure

Opportunity: **PCA/PCI implementation for a banking institution**.

1. Start with `start.ps1` and show `/health` plus the local `qwen3.5:9b` model.
2. Search `PCA PCI banque` and explain lexical BM25, multilingual E5 and the 75/25 fusion.
3. Apply offering `PCA/PCI`, sector `Banque` and a country filter; show OR-within and AND-across behavior.
4. Open the two separate BCT references and compare structured scope with the exact attestation quotation/page.
5. Select four references in the desired order and open Narrative Studio.
6. Generate a French local-model draft for the banking opportunity.
7. Show the blocking drift warnings; edit or remove unsupported wording and revalidate.
8. Approve only after the narrative is export-eligible.
9. Choose `orange_bank_compact`, generate and download the 7-slide PPTX/PDF.
10. Switch to `detailed_case_study` without regenerating narrative; generate and download the 9-slide PPTX/PDF.
11. Compare the identical reviewed-content hash and selected IDs in both manifests.
12. Show the actual source-page images in both evidence annexes.

Do not present technical regression counts as business relevance. Do not hide empty unsupported narrative fields or validation warnings.

## 13. Final acceptance status

### Technical MVP validation

**FINAL_MVP_TECHNICALLY_VALIDATED**

The implemented local workflow is technically coherent, fail-closed and operational end to end under the validated host configuration. No Phase 7 blocking application defect was found.

### Business relevance validation

**BUSINESS_RELEVANCE_EVALUATION_PENDING**

The evaluator returned `HUMAN_JUDGMENTS_REQUIRED` with 0 reviewed query rows, 0 qrel rows and `metrics: null`. No official business-relevance metric is claimed. Historical bootstrap or technical regression values are not expert relevance results.
