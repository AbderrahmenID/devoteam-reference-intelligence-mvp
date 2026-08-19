# Devoteam MVP professionalization and correction pass

## Pre-change visual audit

Audit date: 2026-08-15. The running frontend and API were inspected at `127.0.0.1:3000` and `127.0.0.1:8000`. The in-app browser exposed no browser session, so the explicitly permitted local-browser fallback was used. Baseline screenshots are under `audit/professionalization/before/`.

### Observed UX problems before implementation

- The landing page is visually dramatic but behaves like a campaign page rather than an internal proposal-enablement product. The search field is not the dominant element and the four-stage workflow is not visible.
- The interface exposes internal retrieval language (`hybrid retrieval`, `evidence gate`, corpus counts, abstention codes, scores/ranking concepts and stable reference IDs) in primary user-facing areas.
- Result titles copy long source descriptions into headings, creating multi-line walls of text. Cards are too tall, repeat evidence and match explanations, and make commercial scanning difficult.
- Filter navigation consumes a tall left rail and uses technical category names. Result controls and selection actions compete with the core search task.
- The selected-reference bar is visually detached from a clear workflow and calls the next step `Generate AI narrative` rather than presenting selection as a reviewable basket.
- Narrative Studio opens as an extremely tall modal, shows selected references as dense columns, defaults the audience to Mixed rather than Executive, and places a prominent AI label ahead of the commercial review task.
- Opportunity inputs and generation settings have weak hierarchy. Validation and review actions are structurally present but not summarized as a compact decision panel.
- Result and editor copy frequently says what the system is doing internally instead of what a consultant needs to decide next.
- Empty or unsupported fields are inconsistent and can look like broken data rather than an explicit source limitation.
- Download readiness is not expressed as a distinct final workflow state.

## Source-template inventory and visual language

The detailed source is `templates/reference_pack/source/references sapmple and template.pptx` (4 slides, 16:9). Every slide was rendered through LibreOffice and inspected. The compact source is `templates/reference_pack/source/OT_DVT_SDSI__OrangeBANK.pdf` (154 pages, 16:9). Every page was rendered and inspected; the compact reference patterns are pages 10-17 and the supporting-document patterns are pages 18-29. No Orange Bank `.ppt`, `.pptx` or other editable source deck exists anywhere in the workspace.

The shared visual language is:

- Devoteam coral as the action and section accent; deep blue-black for headings; warm white and pale neutral backgrounds; restrained mint only for confirmed/supporting states.
- Montserrat-like geometric headings with plain, highly legible body copy.
- Large editorial section numerals, thin rules, generous whitespace and very light borders rather than dashboard-heavy chrome.
- Flat two-column case-study composition in the detailed family: visual/client context on the left and `Challenges / Réalisations / Bénéfices` on the right.
- Compact reference summaries in the Orange family: strong coral reference labels, short commercial descriptions, logo/client context and disciplined evidence annex pages.
- Rounded/circular image crops and sparse Devoteam marks used as brand furniture, not decorative gradients.

These source-derived tokens govern the application correction. No new brand system is invented.

## Implementation record

The correction remains within the existing MVP. Retrieval ranking, filters, corpus v2, reference IDs, `TrustedV2Repository`, evidence lineage, support assignment, provenance, model selection and evidence selection were not changed, and the corpus was not rebuilt.

### Application and search

- Reworked the shell into four plain-language stages: Find references, Select references, Prepare narrative and Generate presentation.
- Made opportunity search the dominant control and moved filters into a compact, collapsible region.
- Removed scores, ranking terminology, stable IDs, source paths, abstention codes and other engineering metadata from the primary workflow. Source details remain available in a secondary disclosure.
- Added deterministic `display_title` generation and storage without changing authoritative source titles or calling the drafting model. Result cards and the selection basket use the short title; source details retain the full original text.
- Reduced result-card density to client, title, metadata, commercial fit, concise tags and selection actions.
- Applied source-derived visual tokens in `app/frontend/app/globals.css`: Devoteam coral, deep navy, warm neutral surfaces, mint support states, restrained borders, geometric typography, editorial spacing and visible focus states.

### Narrative, validation and export

- Reorganized Narrative Studio as a proposal-writing workspace with professional defaults: French, Commercial, Executive and Medium.
- Made opportunity fields, draft settings, reviewed section narrative and references visually distinct without adding a new schema or field.
- Replaced the database-like metadata layout with a compact client/title/metadata hierarchy and kept verified source facts read-only.
- Added explicit per-bullet editing for Réalisations and Bénéfices while preserving the existing backend list representation.
- Presented empty evidence-backed fields as source limitations and kept them optional; no content is invented to fill a slide region.
- Summarized validator state into Needs correction, Review suggested and Source limitation levels. Field messages remain visible and technical details remain expandable. Validator rules and approval gating are unchanged.
- Clarified the action sequence and states: generate draft, review/validate, approve narrative, choose one of exactly two formats, generate and download.
- Kept format switching deterministic. Both generated manifests use the same approved reviewed-content hash, and the model is not called during export.
- Added professional loading and error copy, download readiness, and secondary technical details.

### Focused regression coverage

Tests now cover deterministic short titles, validation-summary presentation, hidden technical metadata, the four-stage shell, professional Studio defaults, bullet editing and unsupported fields, exactly two formats, no model call on format switch/export, source geometry, sample cleanup, loading copy and presentation download state.

## Validation and artifacts

### Browser workflow and screenshots

The complete live workflow was exercised against the running API and frontend with a local Selenium/Chrome fallback. The in-app browser had no available session. The generated draft initially contained an unsupported completion/relevance claim; approval correctly remained blocked. The unsupported field was cleared in the editor, the backend validator re-ran, approval became available, and both formats were generated from that same approved content.

- Before: `audit/professionalization/before/A-landing.png` through `D-narrative-studio.png`
- A-I after: `audit/professionalization/after/A-search-page.png` through `I-export-success-compact.png`
- Complete after-workflow montage: `audit/professionalization/after-workflow-montage.jpg`

The search, result, selection, pre-generation Studio, generated draft, validation issue, approved state, format selector and both export success states were inspected at a professional laptop viewport. The corrected workflow has no normal-path horizontal scroll or clipped primary actions.

### Source and generated presentation comparison

Requested source-template inventory:

1. Detailed source PPTX: `templates/reference_pack/source/references sapmple and template.pptx`
2. Orange compact source available in the repository: `templates/reference_pack/source/OT_DVT_SDSI__OrangeBANK.pdf`

There is no second source PPTX path to report. A recursive workspace search, including the sibling clean-pipeline folder, found no Orange Bank `.ppt` or `.pptx`. A temporary LibreOffice PDF-import deck under the audit folder is not an original editable template and is not represented as one.

Detailed Case Study uses source-slide cloning from the actual PPTX and removes the original sample slides after cloned slides are populated. It preserves the exact 10 × 5.625 inch source size, Devoteam furniture and source geometry, and it passes sample-text/media cleanup. However, populated text currently uses the configured Arial fallback rather than preserving the source deck's Montserrat/Montserrat Light run formatting exactly.

Compact References uses the existing source-derived renderer configured from the Orange PDF. It preserves the PDF's 13.333 × 7.5 inch page geometry and visually follows the Orange reference and evidence patterns, but it creates editable shapes programmatically. It is not an OOXML clone of an original Orange PPTX/master/layout because that source deck is absent. This is the decisive unmet requirement.

- Detailed source montage: `audit/professionalization/templates/detailed-source-montage.png`
- Orange source montage: `audit/professionalization/templates/orange-source-montage.jpg`
- Detailed source/generated comparison: `audit/professionalization/generated/detailed-source-vs-generated.png`
- Compact source/generated comparison: `audit/professionalization/generated/compact-source-vs-generated.png`
- J, generated PPTX montages: `audit/professionalization/generated/J-detailed-pptx.png` and `J-compact-pptx.png`
- K, generated PDF montages: `audit/professionalization/generated/K-detailed-pdf.png` and `K-compact-pdf.png`

Both generated PPTX files and both PDFs were rendered with LibreOffice/Poppler and visually inspected. The detailed one-reference case slide is intentionally sparse because unsupported challenge, delivery and benefit content remained empty; this is correct fail-closed behavior rather than fabricated presentation copy. The PDFs correspond visually and structurally to their PPTX files.

### Development artifacts

Detailed Case Study:

- `generated/reference_packs/narrative-pptx-20260815T151353395261Z-a10f2a2fb6/narrative_reference_pack.pptx`
- `generated/reference_packs/narrative-pptx-20260815T151353395261Z-a10f2a2fb6/narrative_reference_pack.pdf`

Compact References:

- `generated/reference_packs/narrative-pptx-20260815T151356885075Z-da7a89acca/narrative_reference_pack.pptx`
- `generated/reference_packs/narrative-pptx-20260815T151356885075Z-da7a89acca/narrative_reference_pack.pdf`

The two manifests share reviewed-content SHA-256 `ed05fb32b74379844e2da9154fa4fad1cb1da6fd96e7f4e9c4286efcb144da07`, approval status `READY_FOR_PRESENTATION`, the same selected reference and the same approved evidence source/page.

### Automated checks

- Full Python suite: 194 passed.
- Frontend suite: 37 passed.
- Frontend lint: passed with zero warnings.
- Frontend production build: passed.
- Focused title/narrative/presentation suite: 22 passed (also included in the full total).
- Retrieval regression: 255 rows across five fixed configurations; zero rows with technical issues.
- Both exact development PPTX/PDF pairs: repository structural validator passed. No out-of-bounds objects, fonts below 8 pt, broken native bullets, sample text/media, internal metadata, empty structural placeholders, evidence aspect-ratio changes, blank PDF pages or page-count mismatch were found. Reports: `audit/professionalization/generated/detailed-validation.json` and `compact-validation.json`.
- Artifact safety audit: passed through the structural validator and full sample-leak/evidence tests.
- `git diff --check`: passed; only line-ending conversion notices were emitted.
- The presentation skill's separate padded-canvas helper could not run because its bundled `@oai/artifact-tool` runtime package is absent. This was covered with the repository validator and LibreOffice/Poppler visual QA, not reported as a pass for that unavailable helper.

## Remaining limitations and final disposition

The application/UX correction is demonstrable and the end-to-end workflow is green. It cannot receive the requested ready status because the strict PowerPoint definition of done requires two original PowerPoint source decks and source-slide cloning for both. The repository contains only an Orange PDF, and the current Compact renderer is an emulation rather than an OOXML-preserving clone. Exact Detailed typography preservation is also incomplete for newly populated text because Arial is used as the configured fallback.

Obtaining the original editable Orange Bank PPTX and integrating its actual reference-section slides is external source-material work, not something that can be truthfully reconstructed during this correction pass.

DEVOTEAM_MVP_POLISH_NOT_READY
