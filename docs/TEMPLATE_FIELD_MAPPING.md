# Word template audit and field mapping

## Template identity and preservation

The supplied source is `templates/Template Ref.docx` (16,228,690 bytes; SHA-256 `A58E409010992F9A8B7A958EBBC7BF7D3FE06DC1043287FD2DB72BEDCA5334DA`). It is retained byte-for-byte and is never an export destination. The API creates every deliverable from a task-local working copy and verifies the source hash after generation.

The configured canonical path is `templates/reference_template.docx`. It is a byte-identical canonical copy of the supplied file so application code has a stable, space-free template path while preserving the original attachment filename.

## Structural audit

The source template contains:

- one summary section headed `Nos principales références`;
- one 19-row summary table with six logical columns: number, project title, client, country, period, and key themes;
- seven theme subcolumns under the logical key-themes column;
- 17 detailed reference sections headed `Référence N°…`;
- one six-row, two-column details table per reference;
- 17 Word sections, 18 tables, 953 paragraphs, and 32 embedded media assets;
- native `Title`, `Heading 1`, `Heading 2`, and `Heading 5` paragraph styles plus template-specific table styles;
- detailed labels for mission, country, contracting authority, start date, completion date, project description, and services delivered.

The summary theme taxonomy visible in the source template is:

1. Audit technique et organisationnel
2. Réingénierie des processus
3. Rédaction des cahiers des charges
4. Réseaux et architecture
5. Sécurité des SI et interopérabilité
6. Accompagnement à la mise en place
7. Conduite du changement

Exports reproduce the template's red heading accent, summary-first structure, compact table hierarchy, detailed annex rhythm, footer page numbering, and one-reference-per-section organization. A task-local template copy is reopened to validate the audited topology; dynamic output is written to a clean package so sample records and unused embedded media cannot leak into an export.

## Source-grounded field mapping

| Field | Source and normalization | Missing behavior | Display label | Filterable | Provenance |
|---|---|---|---|---|---|
| Stable ID | `reference_id`, unchanged | Never missing for an eligible record | Stable reference ID | No | Direct |
| Reference number | `reference_number`; trim whitespace and discard spreadsheet error markers such as `#VALUE!` | Blank or `Not available in source` | `#` / `Référence N°` | No | Direct |
| Project title / mission | `service_nature`; whitespace-only normalization, 220-character summary excerpt; `offering` only when service nature is absent | Blank when neither source field exists | Project / mission; Nom de la mission | Yes as service nature | Direct source text; display excerpt derived |
| Client / contracting authority | `client`; whitespace normalization | Blank or configured missing label | Client; Nom de l’Autorité Contractante | Yes | Direct |
| Country | `country`; canonical case/spelling and known `Abidjan`→Côte d’Ivoire mapping | Blank or configured missing label | Country / Pays | Yes | Derived label from direct value |
| Country code | ISO alpha-2 lookup from canonical country | Null when unrecognized | Country code | Returned, not shown as a separate UI filter | Derived |
| Period | all explicit years in `project_year`; `[min,max]`, current year only for explicit ongoing markers | Blank | Period / Période | Yes | Derived from direct years |
| Start year | minimum explicit year | Null/blank | Date de démarrage | Via period | Derived |
| End year | maximum explicit year; null completion for ongoing | Null/blank | Date d’achèvement | Via period | Derived |
| Project ongoing | explicit `ongoing`, `présent`, `present` or `en cours` marker only | False when no marker | Status | Yes | Derived |
| Sector | `sector`; whitespace normalization | Blank | Sector | Yes | Direct |
| Offering | `offering`; whitespace normalization | Empty list/blank | Offering | Yes | Direct |
| Service nature | `service_nature`; whitespace normalization | Blank | Service nature | Yes | Direct |
| Business unit | `business_unit`; whitespace normalization | Blank | Business unit | Yes | Direct |
| Evidence availability | `evidence_available` plus at least one linked eligible chunk | False | Evidence availability | Yes | Derived from direct flags/links |
| Evidence type | union of `attestation_available` and linked chunk `document_type`; discard `Sans JUSTIF` | Empty list | Evidence type | Yes | Direct controlled values |
| Document language | distinct linked chunk `document_language` codes | Empty list | Document language | Yes | Direct |
| Technologies | controlled phrase matches over source metadata/evidence | Empty list; no inferred product | Technologies | Yes | Deterministically derived |
| Key themes | seven audited template-theme phrase rules over source metadata/evidence | Empty list; no checkmark | Thématiques clés | Yes | Deterministically derived |
| Description | full `service_nature` | Blank or configured missing label | Description du projet | No separate filter | Direct |
| Services delivered | retained supporting evidence passages | Empty list | Services effectivement rendus | No | Direct excerpt |
| Citation | chunk filename, 1-based page, label and URI | URI blank when absent; filename/page remain | Source | No | Direct provenance |

## Unsupported fields

The corpus does not provide reliable contact details, staff names, contract amounts, exact calendar dates, or a separate authoritative project-title column. These fields are not synthesized. Missing values render as blank or `Not available in source`, according to the export option.

## Rendering note

The source was audited directly through its OOXML package. Microsoft Word automation available on the host did not complete a headless PDF conversion during the initial audit and was stopped without modifying the template. Final export verification therefore includes structural OOXML checks and uses the first available supported DOCX-to-PDF renderer; any environment limitation is reported explicitly in the validation results.
