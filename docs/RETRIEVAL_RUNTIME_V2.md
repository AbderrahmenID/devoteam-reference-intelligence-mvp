# Retrieval Runtime v2

## Activation and rollback

`start.ps1`, `app.api.settings`, and `python -m retrieval.diagnose` default to:

```text
config/baselines/SELECTED_RETRIEVAL_CONFIGURATION.yaml
```

That configuration points to the manifest-verified v2 chunks, catalog, BM25, lookup and embeddings. It enables field-aware BM25, 0.75/0.25 weighted RRF, reference aggregation, conservative relevance gating and two-passage evidence selection.

Start selected v2:

```powershell
.\start.ps1
```

Run the pre-improvement v2 behavior:

```powershell
$env:DEVOTEAM_CONFIG = 'config/baselines/PRE_RETRIEVAL_IMPROVEMENT.yaml'
.\start.ps1
```

Roll back completely to corpus v1:

```powershell
$env:DEVOTEAM_CONFIG = 'config/baselines/V1_ROLLBACK.yaml'
.\start.ps1
```

After stopping, clear the override with `Remove-Item Env:DEVOTEAM_CONFIG -ErrorAction SilentlyContinue`.

## Runtime sequence

1. Validate query and authorization boundary.
2. Resolve hard filters with AND across categories and OR inside a category.
3. Mask ineligible references/chunks before scoring.
4. Score reference fields with normalized, weighted BM25 and exact whole-token support.
5. Search all eligible chunk vectors with the unchanged pinned E5 model.
6. Fuse lexical and dense ranks with weighted RRF.
7. select clean, display-approved, source-linked evidence.
8. Aggregate at reference level and apply explicit relevance patterns.
9. Retain every passing reference, sort deterministically and paginate.

Country is never a scoring field. Client has a near-zero lexical weight and cannot independently pass the relevance gate. Retrieval-only chunks may rank a reference but cannot become displayed evidence.

## Integrity

- v2 chunks/BM25/lookup/embeddings: 1,125 aligned rows.
- embeddings: 1,125 × 768, finite and normalized.
- repaired chunks: 69; quarantined rows: 53 outside runtime chunks.
- v2 `config.v2.yaml` SHA-256 remains `97136f15…`.
- v1 `config.yaml` SHA-256 remains `c64c9cd3…`.

The authoritative migration evidence is `data/versions/v2/V2_MIGRATION_MANIFEST.json`, its validation block, and `tests/test_v2_integrity.py`.
