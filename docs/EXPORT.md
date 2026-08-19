# Template-based DOCX export

## Endpoint

`POST /api/export/docx`

The request must include the search query and may include the same hard-filter context and sort used by `/api/search`. Choose exactly one selection mode:

- `selected_reference_ids`: stable IDs selected across result pages; or
- `export_all_filtered: true`: every evidence-gated reference in the current ranked/filtered result set.

The server re-runs the complete search and rejects a selected ID that is not a member of the current retained set. Raw catalog IDs cannot bypass filters or the evidence gate.

```json
{
  "query": "API gateway Kong",
  "filters": {"country": ["Côte d’Ivoire"]},
  "selected_reference_ids": ["stable-reference-id"],
  "export_all_filtered": false,
  "sort": "relevance",
  "options": {
    "include_summary_table": true,
    "include_detailed_annex": true,
    "include_evidence_passages": true,
    "include_scores": false,
    "missing_value_policy": "blank"
  }
}
```

## Template handling

- Supplied source: `templates/Template Ref.docx`.
- Canonical runtime path: `templates/reference_template.docx`.
- Both files are byte-identical with SHA-256 `A58E409010992F9A8B7A958EBBC7BF7D3FE06DC1043287FD2DB72BEDCA5334DA`.
- The configured hash is verified before every export.
- A task-local working copy is created and reopened to validate the audited 18-table template topology.
- The output is a clean Word package that applies the audited summary-first, red-accent, compact-table and annex layout system. It does not carry the template's sample records, unused media or embedded-font payload.
- Neither template file is an output destination.
- The source hash is verified again after generation.

## Output structure

The summary table contains reference number when source-supported, mission/project wording, client, country, period and key themes. The annex contains stable ID, mission, contracting authority, year-precision dates, status, sector, offering, technology tags, themes, evidence types, languages, source description and cited passages.

Missing source fields are blank by default. `missing_value_policy: not_available` displays `Not available in source`. No LLM is called and no sentence is generated to fill a missing field.

Retrieval scores are excluded by default. If explicitly enabled, they are labeled diagnostics and never described as confidence or probability.

## Filename and delivery

The filename format is:

`devoteam-references-YYYYMMDD-HHMMSS-microseconds-<count>-<context-hash>.docx`

The API exposes reference count and document SHA-256 headers, streams the file, and deletes the temporary server artifact after the response completes.

The configured export ceiling is 161 references. Evidence links are enabled, evidence images are disabled, and raw scanned pages are never embedded by default.

## Validation

Every export must:

- be a valid OPC/ZIP package;
- contain the Word document and styles parts;
- reopen with `python-docx`;
- contain every selected reference by stable ID or exact project title;
- contain at least one table;
- leave the source-template hash unchanged.

The automated test suite covers selected subsets, summary-only output, missing values, empty selections, bad template hashes, invalid API selections and endpoint MIME/package validity.

PDF export is intentionally outside the blocking acceptance path. See `FILTER_AND_EXPORT_RESULTS.md` for render-environment status.
