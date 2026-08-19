# AI Presentation Generator

## Primary MVP workflow

The user searches, selects references, and opens a compact **Generate presentation** dialog. The dialog exposes only:

- presentation style: `orange_bank_compact` or `detailed_reference`;
- output: `pptx`, `pdf`, or `both`.

There is no Narrative Studio, tone, audience, detail-level, approval, or validation-dashboard step in the primary workflow. The backend still owns automatic grounding validation and uses Qwen `qwen3.5:9b` to write one selected reference at a time. A rejected unit receives one constrained retry; a second failure produces a safe trusted-title fallback with unsupported fields empty.

## Orange Bank Compact References

Template ID: `orange_bank_compact`

The source of truth is Orange Bank PDF pages 10–29. The generator clones the corresponding derived source slides: page 10 for the divider, pages 11–17 for compact summary layouts, and pages 18–29 for evidence treatment. It preserves selection order and places at most three references on each summary slide.

Qwen returns only `display_title` and three to six `activities` when eligible support exists. Trusted client, country, sector, and offering metadata are inserted deterministically. One approved evidence page is appended for each reference where display evidence is available; a reference without evidence remains in the summary and does not fail the export.

## Detailed Reference

Template ID: `detailed_reference`

The generator clones the real source reference slide from `templates/reference_pack/source/references sapmple and template.pptx`. Qwen returns only `mission_title`, `challenges`, `realisations`, and `benefits`. Unsupported challenge and benefit sections remain empty.

The output contains exactly one slide per selected reference. Four selected references therefore produce exactly four slides—no divider, storyline, introduction, rationale, or evidence-annex slides.

## Files, validation, and progress

PowerPoint content remains editable. PDF is produced from the generated PPTX through headless LibreOffice, so the two formats share the same slide content and page count. The browser receives business-level progress only: preparing references, writing each reference, building the presentation, and preparing PDF when requested.

No third template, custom upload, comparison matrix, layout editor, evidence picker, or AI template selection is supported.
