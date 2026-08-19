# Reference pack generation

## Outcome

The application generates an editable `.pptx`, an equivalent LibreOffice PDF
when requested, and a source-lineage JSON manifest from explicitly selected
stable v2 reference IDs. Generation is synchronous for this local MVP and does
not call a model, agent, RAG pipeline, external presentation service, or the
retrieval rankers.

## User workflow

1. Run a reference search.
2. Inspect returned evidence.
3. Select only the references to retain.
4. Open **Generate Reference Pack** from the ordered selection basket.
5. Choose title, opportunity, date, language, sections, logo policy and formats.
6. Generate PPTX and PDF.
7. Download and edit the PowerPoint.
8. Use the PDF as the fixed sharing version.

The browser basket is stored in `sessionStorage`, deduplicated by stable
`reference_id`, ordered by the user’s selection actions, and cleared only by an
explicit remove/clear action. It sends IDs and presentation options only.

## Trusted backend flow

`reference_pack/validation.py` reloads the selected references from the active
v2 catalog and chunks declared by
`config/baselines/SELECTED_RETRIEVAL_CONFIGURATION.yaml`. The selected config
uses `data/versions/v2/V2_MIGRATION_MANIFEST.json`; this is the repository’s
versioned name for the requested v2 migration manifest.

Before generation the service verifies:

- unique, existing stable IDs in user order;
- retrieval eligibility and permitted `INTERNAL` classification;
- at least one retrieval- and display-approved evidence chunk;
- nonempty document ID, sanitized source filename, SHA-256, positive page,
  citation label/URI and display text;
- a consistent source hash for every document;
- current v2 chunk/catalog hashes against the migration manifest.

Retrieval-only, quarantined, display-prohibited or incomplete-lineage evidence
causes a precise HTTP 422 rejection. Browser-provided project facts are never
accepted.

## Deterministic content

`content_builder.py` splits source fields at sentence, bullet and clause
boundaries; removes duplicates, headers, footers, administrative/legal phrases,
contact markers and signatures; preserves Unicode/acronyms; and enforces the
configured length limits. It never generates replacement facts. Slide
provenance records each bullet’s source fields and evidence chunk IDs.

Static labels are available in French, English and Arabic. User/source content
is preserved rather than machine-translated. Arabic text uses right alignment
and RTL paragraph metadata where PowerPoint interoperability permits it.

## Artifacts and conversion

Each generation is allocated with an exclusive server-created ID under:

`generated/reference_packs/{generation_id}/`

The directory contains `reference_pack.pptx`, optional `reference_pack.pdf`,
`generation_manifest.json`, `generation_log.json`, and the sanitized
`generation_request.json` used for reproducibility. The manifest records corpus,
template, source document/page/chunk and output hashes plus the exact API
generation command.

LibreOffice runs headlessly in a temporary conversion directory. The converter
requires a zero exit code, a nonempty PDF, matching slide/page counts, preserved
accented/Arabic Unicode and a nonblank render. If LibreOffice is absent or
conversion fails, the editable PPTX remains available and the response contains
a warning; no fake PDF is created.

## Reproduce validation demos

```powershell
cd C:\Users\abder\Downloads\Devoteam_AI_Workspace\devoteam-reference-mvp
$env:PYTHONUTF8='1'
.\.venv\Scripts\python.exe -m scripts.generate_reference_pack_demos
.\.venv\Scripts\python.exe -m scripts.validate_reference_pack_visuals
```

> The reference-pack generator is deterministic and source-grounded. It uses
> only user-selected Devoteam references, trusted structured metadata and
> display-approved evidence with document/page lineage. No AI agent or
> generative language model is used.
