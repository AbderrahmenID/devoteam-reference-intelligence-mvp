# Pre-v2 Baseline

Date: 2026-08-02  
Branch: `fix/retrieval-evidence-quality`  
Status: **PASS — v1 unchanged**

## Automated verification

Command: `./scripts/test.ps1`

- Environment, configuration, data, pinned model, template, and imports: PASS.
- Python: 3.10.11.
- Node.js: 24.11.1; npm: 11.10.0.
- Python tests: **62 passed**, 0 failed, in 68.28 seconds.
- Warnings: five PyMuPDF/SWIG deprecation warnings.
- Evaluator guard: `HUMAN_JUDGMENTS_REQUIRED`, 0 qrels, official metrics `null`.
- Frontend ESLint with zero warnings: PASS.
- Next.js 15.5.7 production build: PASS; compilation completed in 1.984 seconds.
- Tesseract warning: executable absent.

The tests cover meaningful multilingual terms and stopword exclusion, corrupted-evidence rejection, clean evidence selection, reference removal when usable evidence is absent, strict hard filters, stable pagination/citations, Arabic/mixed-script preservation, and immutable manifest/index alignment.

## Lifecycle verification

`start.ps1` completed successfully. `scripts/demo_check.ps1` produced:

| Input | Decision | Total | Page results | Language |
|---|---|---:|---:|---|
| French | `SUFFICIENT_EVIDENCE` | 23 | 20 | fr |
| English | `SUFFICIENT_EVIDENCE` | 20 | 20 | en |
| Arabic | `SUFFICIENT_EVIDENCE` | 22 | 20 | ar |
| Mixed Arabic/French | `SUFFICIENT_EVIDENCE` | 14 | 14 | mixed |
| Unsupported domain | `UNSUPPORTED_PORTFOLIO_SCOPE` | 0 | 0 | fr |

`stop.ps1` stopped backend PID 38684 and frontend PID 21788. Subsequent checks found no listener on ports 3000 or 8000.

## v1 runtime identity

Exact hashes, byte sizes, and `DATA_MANIFEST.json` reconciliation are recorded in `audit/v1_runtime_asset_hashes.json`. The frozen set includes:

- `data/chunks.parquet`;
- `data/reference_catalog.parquet`;
- BM25 index and vocabulary;
- dense embedding matrix and chunk lookup;
- Phase 4, Phase 5, and copy manifests;
- retrieval runtime metadata;
- `config.yaml`.

The canonical v1 chunk and reference hashes remain:

- chunks: `aa6f19e1eddb17505a35b8ff9443ac76385c2d7ed2d7ba414b205cf15e1c9b0e`;
- reference catalog: `13f9605cdd0fd47817e8b4c111a931d61a18413dc67202044e776d4ab4977b30`.

The read-only source snapshot identifier is `20260714T154731Z_129ff982c8`. Repair-source existence and SHA-256 identity are validated separately in the targeted repair manifest; no source-project write operation is performed.
