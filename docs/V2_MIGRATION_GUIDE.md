# v2 Migration and Runtime Switch

## Current activation state

Corpus v2 is the application default through `config/baselines/SELECTED_RETRIEVAL_CONFIGURATION.yaml`. `start.ps1` sets `DEVOTEAM_CONFIG` to that file only when the caller has not supplied an override. Direct FastAPI and diagnostic startup use the same default.

The tracked `config.yaml` remains byte-identical to the recorded corpus-v1 runtime baseline. Versioned corpus-v2 files also remain byte-identical to `data/versions/v2/V2_MIGRATION_MANIFEST.json`.

## Start selected v2

```powershell
.\start.ps1
.\scripts\demo_check.ps1
.\stop.ps1
```

## Controlled alternatives

Pre-improvement v2:

```powershell
$env:DEVOTEAM_CONFIG = 'config/baselines/PRE_RETRIEVAL_IMPROVEMENT.yaml'
.\start.ps1
```

Full corpus-v1 rollback:

```powershell
$env:DEVOTEAM_CONFIG = 'config/baselines/V1_ROLLBACK.yaml'
.\start.ps1
```

Stop before changing configurations and clear the session override afterward:

```powershell
.\stop.ps1
Remove-Item Env:DEVOTEAM_CONFIG -ErrorAction SilentlyContinue
```

No v2 file is copied over v1. The E5 model/revision, 768 dimensions, prefixes and exact-search contract are unchanged. See `RETRIEVAL_RUNTIME_V2.md` and `SELECTED_RETRIEVAL_CONFIGURATION.md` for runtime details.
