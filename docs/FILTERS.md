# Filters and facets

## Contract

Hard filters operate on the 138 retrieval-eligible reference records before BM25 or dense ranking. The source parquet files and retrieval artifacts remain immutable; `retrieval/metadata.py` builds the normalized layer in memory at service startup.

- AND across categories.
- OR across selected values inside one category.
- Unknown category: HTTP 422.
- Unknown source-derived value: HTTP 422.
- Valid filter combination with no eligible record: HTTP 200 with `abstained=true` and `NO_ELIGIBLE_REFERENCE`.
- Security classification remains an independent hard chunk mask.

## Supported categories

| Filter | Provenance | Notes |
|---|---|---|
| `period` | `project_year` | Closed-interval overlap; explicit years or a relative preset. |
| `country` | `country` | Deterministic spelling/case/known-city normalization. |
| `sector` | `sector` | Direct catalog values. |
| `client` | `client` | Direct catalog values. |
| `offering` | `offering` | Direct controlled catalog values. |
| `service_nature` | `service_nature` | Direct source descriptions; high-cardinality by design. |
| `technology` | metadata/evidence terms | Deterministic controlled tag rules; only tags with source matches appear. |
| `status` | parsed `project_year` | `ongoing` requires an explicit marker; finite dated values become `completed`. |
| `evidence_available` | catalog flag plus linked chunks | `available` or `unavailable` when present in the eligible universe. |
| `evidence_type` | `attestation_available`, chunk `document_type` | Direct source classifications. |
| `language` | linked chunk `document_language` | Reference may have multiple source languages. This is optional; cross-language retrieval remains available when unfiltered. |
| `themes` | seven template themes | Deterministic source-term mapping described in `TEMPLATE_FIELD_MAPPING.md`. |
| `business_unit` | `business_unit` | Direct catalog values. |

Backward-compatible `project_year`, `year_after`, `year_before`, `attestation_available`, `document_type`, and `data_quality_status` fields remain accepted. New clients should use `period` and `evidence_type` where applicable.

## Time semantics

A source value containing multiple years becomes `[minimum year, maximum year]`. Matching uses:

`project_start <= requested_end AND project_end >= requested_start`

Both boundaries are inclusive. For an explicit ongoing marker, the runtime end is the local current year. Presets are resolved at request time:

- `last_3_years`: current year minus 2 through current year;
- `last_5_years`: current year minus 4 through current year;
- `last_10_years`: current year minus 9 through current year.

On 31 July 2026, `last_3_years` resolves to 2024–2026. The current eligible catalog ends in 2022, so that preset correctly produces an empty eligible set.

## Facets

`GET /api/facets` returns values and reference counts for every supported category plus period bounds and presets. An optional URL-encoded JSON `filters` parameter applies the same filter schema and returns counts within that eligible context.

Example response fragment:

```json
{
  "eligible_reference_count": 138,
  "facets": {
    "country": [{"value": "Tunisie", "count": 97}],
    "period": {
      "min_year": 2011,
      "max_year": 2022,
      "current_year": 2026,
      "presets": ["last_3_years", "last_5_years", "last_10_years"]
    }
  }
}
```

Counts are reference counts, never chunk counts.

## Normalization and aliases

Matching keys use Unicode compatibility normalization, case folding, French-diacritic folding and punctuation-as-space. Raw display/source text is never overwritten.

Country display aliases are deliberately narrow and auditable:

- `tunisie`, `tunise`, case variants → `Tunisie` (`TN`);
- Côte d’Ivoire apostrophe/case variants and `Abidjan` → `Côte d’Ivoire` (`CI`);
- `senegal`/`Sénégal` → `Sénégal` (`SN`);
- `libya`/`Libye` → `Libye` (`LY`);
- known source labels for Algérie, Bénin, Burkina Faso, Cameroun, France, Mali, Maroc, Mauritanie, Niger, Rwanda and Togo receive their canonical display spelling and ISO alpha-2 code.

No general geocoder is used. An unrecognized country remains source text with a null code.

Technology tags are emitted only for controlled source terms: API management (`api gateway`, `api management`, `kong`), Cloud, COBIT, Core banking, Data platform, Digital identity/IAM, ERP/SAP, IPv6, ITIL/service desk and Network. The seven theme tags use the exact template taxonomy and auditable phrases such as audit/diagnostic, process reengineering, requirements/specifications, architecture/network, security/interoperability, implementation support and change/skills transfer. Empty matches remain empty.

Whitespace-only values, null markers and spreadsheet errors such as `#VALUE!` normalize to missing. No fuzzy client, sector or offering alias is applied.

## Search sequence

1. Validate the query and filter schema.
2. Resolve and validate facet values.
3. Build the eligible reference set.
4. Convert eligible references to a security-constrained chunk mask.
5. Run complete masked BM25 and E5 rankings.
6. Fuse and group by stable reference ID.
7. Apply the evidence gate independently to each reference.
8. Retain every passing reference.
9. Apply deterministic sorting.
10. Paginate at 10, 20 or 50 results.

The safety ceiling is 500, which exceeds both the 161-row catalog and 138-reference eligible universe.
