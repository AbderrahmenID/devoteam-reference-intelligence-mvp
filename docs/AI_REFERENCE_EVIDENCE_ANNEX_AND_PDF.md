# AI Reference Evidence Annex and PDF Export

## Scope

Phase 5 introduced the approved evidence-annex and PDF pipeline. Phase 6 reuses that same pipeline for both supported presentation formats. Existing editable narrative/reference slides are preserved, one approved source page is appended for every selected reference, and LibreOffice converts that final PPTX into the final PDF. Export never regenerates narrative content and uses a disabled model provider.

“The evidence annex contains actual approved source-document pages. It is
generated deterministically from trusted evidence lineage; the language model
does not select, rewrite, or fabricate evidence.”

## Approval and evidence selection

Export remains fail-closed. It requires `READY_FOR_PRESENTATION`, explicit human approval, no blocking warning, the original selected-reference order, and a fresh server-side resolution of every stable ID.

The backend chooses exactly one evidence page per reference in this order:

1. a display-approved page assigned as support for the reviewed narrative, preferring delivery and outcome fields;
2. otherwise the first deterministic display-approved evidence item already returned by the trusted v2 repository.

No similarity search, browser-supplied path, manual page choice, or model call participates in export.

## Trusted source resolution

`TrustedV2Repository` remains the authority for reference ownership, authorization, display approval, document ID, page number, source display name, source hash, and relative source lineage. The exporter never accepts evidence identity or a source path from the browser.

`EvidenceRenderer` resolves relative lineage only beneath configured trusted roots. The file must exist and match the trusted SHA-256 before rendering. The renderer supports PDF pages directly, supported image files on page 1, and deterministic LibreOffice-to-PDF conversion for supported Office sources.

## Rendering and aspect ratio

PDF pages are rendered at the configured 3x scale, approximately 216 DPI. The existing renderer may remove white outer margins only through its content-safe crop rule: it adds padding and rejects any crop that could remove a substantial part of the page. The resulting page image is placed with contain-style scaling. It is neither stretched nor rasterized together with the narrative slide.

Narrative text stays as editable PowerPoint text. Only the approved evidence page is a raster image.

## Final deck and artifacts

For `N` selected references, the deck contains:

- slide 1: reviewed section narrative;
- slides 2 through `N+1`: reviewed editable reference slides in selection order;
- slides `N+2` through `2N+1`: one evidence page per reference in the same order.

The established artifact location and filenames remain:

```text
generated/reference_packs/<generation_id>/
  narrative_reference_pack.pptx
  narrative_reference_pack.pdf
  reviewed_content.json
  generation_manifest.json
```

The PDF is created only from `narrative_reference_pack.pptx` by headless LibreOffice. It does not have a separate layout implementation.

## Validation and manifest

Generation validates the final PPTX slide count, evidence image ownership, image aspect ratio, editable narrative objects, and reference order. PDF validation checks the page count against the PPTX, rejects blank or non-landscape pages, and verifies required French and Arabic Unicode samples when present.

Manifest schema version 3 records the selected format, narrative, evidence, and total slide counts; narrative, reference, and evidence slide mappings; safe evidence lineage; source display name and page; hash validation; PDF conversion validation; and SHA-256 values for the final PPTX, PDF, and reviewed content. Local filesystem paths and conversion commands are not exposed.

## Failure behavior

Required evidence is never silently removed or replaced by extracted text. Export uses explicit errors:

- `EVIDENCE_SOURCE_NOT_FOUND`
- `EVIDENCE_PAGE_NOT_APPROVED`
- `EVIDENCE_PAGE_RENDER_FAILED`
- `EVIDENCE_HASH_MISMATCH`
- `PDF_CONVERSION_FAILED`

Incomplete output directories are removed after a blocking export failure.

## Current limitations

- The MVP supports only `orange_bank_compact` and `detailed_reference`.
- The standard is one evidence page per selected reference.
- There is no manual evidence-page picker.
- Office evidence depends on the local LibreOffice installation.
- Production persistence, authentication, hosted providers, deployment features, and additional presentation templates remain outside this phase.
