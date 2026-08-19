# AI Reference PPTX Template Integration

## Phase 4 scope

Phase 4 maps a Phase 3 narrative with status `READY_FOR_PRESENTATION` into an editable PowerPoint. It implements only `TEMPLATE_D_REFERENCE_CASE`, based on the supplied read-only source `templates/reference_pack/source/references sapmple and template.pptx`.

“Presentation generation is deterministic. The language model is not called during export; only human-reviewed and approved narrative content is mapped into editable PowerPoint elements together with trusted reference metadata.”

PDF generation, evidence pages, source-page images, and additional template families remain outside this phase.

## Approval and validation gate

The browser sends the session approval flag, approval status, approved reference order, generation context, reviewed prose, and the fixed template choice. Export proceeds only when:

- the user explicitly approved the narrative;
- status is `READY_FOR_PRESENTATION`;
- the approved reference IDs exactly match the generation request in the same order;
- the trusted repository resolves every selected ID again;
- deterministic narrative validation returns zero `BLOCKING` findings.

The export service owns a `DisabledNarrativeProvider`. It reuses only the validation path of `ReferenceNarrativeService`; generation and regeneration methods are never called. Rejections use explicit reasons including `NARRATIVE_NOT_APPROVED`, `NARRATIVE_REFERENCE_SET_CHANGED`, `NARRATIVE_HAS_BLOCKING_WARNINGS`, and `PPTX_CONTENT_OVERFLOW`.

## Template D mapping

The source presentation is never modified. The registry and controlled mapping are stored in:

- `templates/reference_pack/qwen_studio/template_registry.yaml`
- `templates/reference_pack/qwen_studio/template_d_mapping.yaml`

The mapping clones source slide 2, whose editable objects provide the mission-title, Challenges, Réalisations, Bénéfices, sector, period, Devoteam mark, and page-number zones. Its generic Google shape names are resolved through audited source shape IDs. Generated objects receive stable names such as `D.MISSION_TITLE`, `D.CLIENT`, `D.CHALLENGE`, `D.REALISATIONS`, `D.BENEFITS`, and `D.PERIOD`.

The output sequence is deterministic:

1. one reference-section narrative slide;
2. one case slide per approved reference, in exact selection-basket order.

For `N` references, the output therefore has `N + 1` slides.

## Content ownership

Approved narrative text supplies:

- section introduction;
- overall storyline;
- why the references were selected;
- headline, with trusted mission title as the empty-headline fallback;
- challenge;
- realisations;
- benefits.

Trusted backend data supplies:

- stable reference identity;
- canonical client;
- country;
- sector;
- period/year;
- offering;
- corpus version.

`Devoteam contribution` and `why relevant to the opportunity` are not placed automatically because the first template mapping has no dedicated, unambiguous content zone. No new claim is generated to fill them.

## Editability and bullets

Narrative and metadata are written as native PowerPoint text objects. Realisations and benefits use separate native bullet paragraphs in their reviewed order. Case slides are cloned from the source slide rather than rasterized, and all generated text remains editable in PowerPoint.

## Client images and template samples

The approved local client-logo registry is currently empty. Therefore the exporter uses canonical client-name text and removes the source slide's sample photograph, country flag, client logo, and sector icon. The authentic Devoteam footer mark is preserved. Sample clients, annotations, contact values, accelerators, strategic domains, entities, and dispositifs are never copied into output.

## Missing fields

Missing challenge or benefits content causes the corresponding inherited shape to be deleted. The exporter does not add fallback claims, availability messages, or synthetic bullets. The same rule applies to empty section-narrative fields.

## Overflow policy

The template body size is 10 pt. The deterministic fitter may reduce reviewed body text one point at a time to the documented safe minimum of 8 pt, while preserving all paragraphs and bullet order. Headline and section-title zones have their own higher safe minima. Paragraph spacing may be tightened within the mapped zone.

Text is never truncated, bullets are never removed, and text is never shrunk below the safe minimum. If a mapped field still cannot fit, export stops with `PPTX_CONTENT_OVERFLOW`, including the reference ID when applicable, field name, estimated required lines, available lines, and minimum font size.

## Font fallback

The source uses Montserrat and Montserrat Light, which are not installed on the development machine. Generated and replaced text therefore uses the installed Arial family. The substitution is deterministic and recorded in the manifest; no font files are installed or packaged.

## Artifacts and manifest

Phase 4 reuses the existing `generated/reference_packs/<generation_id>/` convention and writes:

- `narrative_reference_pack.pptx`;
- `reviewed_content.json`;
- `generation_manifest.json`.

The manifest records generation time, template identity and source SHA-256, selected stable IDs, approved status, canonical reviewed-content SHA-256, corpus version, slide count, reference-to-slide mapping, font substitution, overflow result, non-blocking warning codes, and output hashes. It does not store API keys, hidden evidence bundles, or confidential local paths.

## Current limitations

- Approval is session-scoped and is not persisted in a database.
- Only the Challenges / Réalisations / Bénéfices family is available.
- No trusted client logo is rendered until an approved local logo is registered.
- Extremely dense reviewed content is rejected instead of being split across additional case slides.
- Arabic text and right-to-left paragraph metadata are preserved structurally; final typography still depends on the presentation application.
- LibreOffice/PDF rendering is used only for development visual inspection. PDF is not a Phase 4 product output.

