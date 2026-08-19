# Reference pack API

## Create a pack

`POST /api/reference-packs`

```json
{
  "title": "Références pertinentes pour la mission",
  "client_name": "Client",
  "subtitle": "Sélection de références Devoteam",
  "preparation_date": "2026-08-03",
  "language": "fr",
  "reference_ids": ["<stable 64-character v2 reference ID>"],
  "include_summary": true,
  "include_reference_details": true,
  "include_evidence_annex": true,
  "include_logos": true,
  "output_formats": ["pptx", "pdf"]
}
```

The endpoint returns HTTP 201 and a completed or completed-with-warnings status,
selected count, slide count, artifact URLs and warnings. The server sanitizes
all presentation metadata and rejects markup/control characters, invalid IDs,
duplicates, unsupported languages/formats and empty section selections.

## Status and downloads

- `GET /api/reference-packs/{generation_id}`
- `GET /api/reference-packs/{generation_id}/download/pptx`
- `GET /api/reference-packs/{generation_id}/download/pdf`
- `GET /api/reference-packs/{generation_id}/download/manifest`

Generation IDs must match the server format and are resolved beneath the fixed
generation root. The download kind maps to a fixed filename; callers cannot
submit paths. Invalid IDs return 422, missing generations/artifacts return 404,
reference validation returns 422, and unexpected rendering failures return 500
with `REFERENCE_PACK_GENERATION_FAILED`.

Only the IDs and presentation options in the request are trusted from the
browser. Titles, clients, descriptions, services, technologies, evidence,
pages, hashes and logos are loaded from trusted v2 assets on the server.
