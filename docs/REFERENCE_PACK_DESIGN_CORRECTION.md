# Reference Pack design correction

Date: 2026-08-03  
Scope: evidence annex, reference-summary slides, and optional selection workflow only. Retrieval, v2 corpus assets, ranking, and abstention were not changed.

## Outcome

The reference pack is now source-page-first. Every selected reference receives one evidence slide containing its hash-verified approved document page. A text card is used only when the source cannot be rendered, and its reason is mandatory in the generation manifest.

The search page no longer contains the permanent, scrollable Reference Pack basket. Selection is exposed through a small checkbox on each result, a compact bottom bar after the first selection, and a side drawer for review/removal/reordering. The generation form is mounted only after **Generate pack** is clicked.

## Before and after — search UI

### Old UI screenshot

A genuine browser screenshot could not be captured in this execution session because the supported in-app browser runtime reported no available browser. The pre-correction implementation was inspected directly before editing and contained both:

- a permanent `selection-bar` above the results;
- a large `SelectionBasket` panel with a scrollable list and full-width generation button in the central results column.

No synthetic screenshot has been substituted for that missing capture.

### Corrected UI screenshot

The same browser-runtime limitation prevented a genuine corrected browser screenshot. The corrected visual state is backed by the production build and the frontend assertions in `app/frontend/tests/referencePackUi.test.mjs`:

- no `SelectionBasket` is mounted in the results flow;
- the bottom `CompactSelectionBar` returns `null` for zero selections;
- **View selection** opens `SelectionDrawer`;
- the drawer contains only mission title, client, country, remove and reorder controls;
- `ReferencePackModal` is conditional on the explicit generation action.

## Before and after — evidence annex

### Old evidence slide

![Old text-card evidence slide](../audit/reference_pack/design_correction_demo/old_evidence_slide.png)

The old slide placed extracted text inside large rounded cards. It did not show the approved document page and left most of the slide without meaningful visual evidence.

### Corrected evidence slide

![Corrected source-page evidence slide](../audit/reference_pack/design_correction_demo/corrected_evidence_slide.png)

The corrected slide contains the real approved attestation page, rendered at high resolution and placed without stretching. The mission, client/country subtitle, filename, page number, Devoteam footer and slide number remain separate and readable. The coral frame now follows the actual source page rather than creating a large empty card.

## Corrections applied

| Area | Previous behavior | Corrected behavior |
|---|---|---|
| Source resolution | No configured local source root | Local runtime source cache; path containment and SHA-256 verification |
| PDF evidence | Text excerpt card | Exact approved page rendered with PyMuPDF at 3× scale |
| Office evidence | No rendered page | DOC/DOCX/PPT/PPTX converted through LibreOffice, then rendered |
| Image evidence | Not rendered | Approved image displayed directly on page 1 |
| Cropping | Not applicable | Conservative white-margin crop with pixel coordinates in the manifest |
| Aspect ratio | Not validated | Source and placed ratios recorded and automatically checked |
| Fallback | Default presentation mode | Fallback-only, professional full layout, explicit label and mandatory reason |
| Summary layout | Oversized rounded cards; unbalanced last slide | Flat three-part rows, balanced pagination, maximum three references per slide |
| Mission title | Up to 78 characters | Deterministic concise title capped at 52 characters |
| Selection | Permanent central basket | Per-result checkbox plus compact optional bottom bar |
| Review selection | Full central list | Side drawer with short metadata, removal and reordering |
| Generation form | Multiple visible entry points | Opened only from **Generate pack** after selection |

## Demonstration and validation

The fixed demonstration uses the four references from the UI example and is available at:

- `generated/reference_packs/design_correction_demo/reference_pack.pptx`
- `generated/reference_packs/design_correction_demo/reference_pack.pdf`
- `generated/reference_packs/design_correction_demo/generation_manifest.json`

All rendered slides and the visual validation record are in `audit/reference_pack/design_correction_demo/`.

Validated result:

- 4 selected references;
- 12 PPTX slides and 12 PDF pages;
- 4 evidence slides;
- 4 rendered approved source pages;
- 0 text fallbacks;
- maximum 2 references on either balanced summary slide (within the maximum of 3);
- source filename/page citations present;
- image aspect ratios preserved;
- PPTX/PDF page parity passed.

## Source handling

The clean pipeline remains read-only and was not modified. Approved source documents were copied into `.runtime/reference_pack_sources/raw/evidence` with `scripts/import_reference_pack_sources.ps1`. The renderer refuses paths outside the MVP, rejects hash mismatches, and never writes local filesystem paths into slides or manifests.
