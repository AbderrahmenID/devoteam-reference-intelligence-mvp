# Devoteam multilingual reference retrieval MVP

An internship-scale application for multilingual, filtered Devoteam reference retrieval, template-based Word export and deterministic reference-pack generation. The active runtime uses the repaired v2 corpus, field-aware Unicode BM25, exact search with pinned local `intfloat/multilingual-e5-base`, weighted rank fusion, clean reference aggregation and conservative relevance/evidence gates. Hard metadata filters run before ranking, every passing reference is paginated, and insufficient evidence returns zero results. It is a retrieval system, not a chatbot, and it never generates fallback results or export claims.

The interface provides source-derived facets, multi-select filters, interval-aware periods, relevance and metadata sorting, 10/20/50-result pages, summary and detailed views, an ordered session-persistent stable-ID basket, selected DOCX export and editable PPTX/PDF reference-pack generation with source-lineage manifests.

## Open the project

```powershell
cd C:\Users\abder\Downloads\Devoteam_AI_Workspace\devoteam-reference-mvp
```

## Recreate the environment manually

Python 3.11 is not installed on this machine, so the verified environment uses Python 3.10 and inherits the already-installed Torch runtime to avoid a large duplicate download.

```powershell
py -3.10 -m venv --system-site-packages .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip "setuptools<82" wheel
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -e . --no-deps
cd app\frontend
npm install
cd ..\..
```

## Validate and test

```powershell
.\scripts\validate_environment.ps1
.\scripts\test.ps1
```

The test script runs Python tests (including data integrity and API smoke tests), validates the empty human-evaluation templates, runs frontend lint and produces a frontend build.

Filter and export documentation:

- `docs/FILTERS.md`
- `docs/TEMPLATE_FIELD_MAPPING.md`
- `docs/EXPORT.md`
- `docs/FILTER_AND_EXPORT_RESULTS.md`

Retrieval-quality hotfix documentation:

- `docs/RETRIEVAL_QUALITY_HOTFIX.md`
- `docs/TEXT_FIELD_LINEAGE.md`
- `docs/RETRIEVAL_QUALITY_HOTFIX_RESULTS.md`

Current v2 runtime documentation:

- `docs/DIRECT_RETRIEVAL_IMPROVEMENT_RESULTS.md`
- `docs/RETRIEVAL_RUNTIME_V2.md`
- `docs/RETRIEVAL_DIAGNOSTIC_GUIDE.md`
- `docs/SELECTED_RETRIEVAL_CONFIGURATION.md`
- `docs/REMAINING_LIMITATIONS.md`

Reference-pack documentation:

- `docs/REFERENCE_PACK_GENERATION.md`
- `docs/REFERENCE_PACK_API.md`
- `docs/REFERENCE_PACK_TEMPLATE.md`
- `docs/REFERENCE_PACK_TEST_RESULTS.md`
- `docs/REFERENCE_PACK_VISUAL_VALIDATION.md`

## Start and stop the full application

```powershell
.\start.ps1
```

This starts `config/baselines/SELECTED_RETRIEVAL_CONFIGURATION.yaml` (corpus v2, field-aware retrieval). Set `DEVOTEAM_CONFIG=config/baselines/V1_ROLLBACK.yaml` before startup for a complete v1 rollback; see `docs/V2_MIGRATION_GUIDE.md`.

- Frontend: <http://127.0.0.1:3000>
- Backend: <http://127.0.0.1:8000>
- API docs: <http://127.0.0.1:8000/docs>

Stop only the two recorded MVP processes:

```powershell
.\stop.ps1
```

## Start only the backend

```powershell
$env:USE_TF='0'
$env:TRANSFORMERS_NO_TF='1'
$env:HF_HUB_OFFLINE='1'
$env:TRANSFORMERS_OFFLINE='1'
.\.venv\Scripts\python.exe -m uvicorn app.api.main:app --host 127.0.0.1 --port 8000
```

## Start only the frontend

In a second terminal, after the backend is running:

```powershell
cd app\frontend
$env:NEXT_PUBLIC_API_URL='http://127.0.0.1:8000'
npm run dev -- --hostname 127.0.0.1 --port 3000
```

## Run the live demo checks

With the application started:

```powershell
.\scripts\demo_check.ps1
```

These are technical UTF-8 and contract smoke checks, not official relevance judgments.

## Explain one complete retrieval run

```powershell
$env:PYTHONIOENCODING='utf-8'
.\.venv\Scripts\python.exe -m retrieval.diagnose --query 'API Gateway Kong' --json
```

The diagnostic includes fields, chunk candidates, aggregation, evidence decisions, rejections and final abstention. Internal scores are diagnostic-only and are not displayed in the UI.

## API examples

Search with hard filters and pagination:

```powershell
$body = @{
  query = 'PCA banque'
  filters = @{
    country = @('Tunisie', 'Maroc')
    offering = @('PCA/PCI')
    period = @{ start_year = 2020; end_year = 2022 }
  }
  page = 1
  page_size = 20
  sort = 'relevance'
} | ConvertTo-Json -Depth 6
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/search -ContentType application/json -Body $body
```

Facet values and counts:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/facets
```

Use `POST /api/export/docx` with the current query/filter context and either `selected_reference_ids` or `export_all_filtered: true`. The server re-runs retrieval and rejects IDs outside the retained result set.

Use `POST /api/reference-packs` with explicitly selected stable IDs and presentation options. The server reloads all facts and display evidence from manifest-pinned v2 data; `GET /api/reference-packs/{generation_id}` and its `/download/pptx`, `/download/pdf` and `/download/manifest` routes return the result.

## Evaluate human-reviewed qrels

Complete the CSV templates under `evaluation/`, then run:

```powershell
.\.venv\Scripts\python.exe -m evaluation.evaluate
```

Empty qrels return `HUMAN_JUDGMENTS_REQUIRED` with `metrics: null`; the evaluator never invents labels or quality claims.

## Troubleshooting

- **Pinned E5 model missing:** startup is intentionally offline and will not download it. Restore revision `a114a4100c6714cf21651971eefe9191a4415dbb` under `~/.cache/huggingface/hub/models--intfloat--multilingual-e5-base/snapshots/`, or update `model.local_path` only after building a compatible 768-dimensional index.
- **TensorFlow/protobuf warning:** the MVP does not use TensorFlow. Keep `USE_TF=0` and `TRANSFORMERS_NO_TF=1`; the scripts set both.
- **Tesseract missing:** ordinary search and digital-text PDF preview still work. For scanned PDFs, install Tesseract and the `fra`, `eng`, and `ara` language packs, verify `tesseract --list-langs`, then restart.
- **Node.js/npm missing:** install a current Node.js release, confirm `node --version` and `npm --version`, then run `npm install` in `app/frontend`.
- **Backend unavailable in the UI:** inspect `.runtime/backend.err.log` when started through `start.ps1`; the UI deliberately shows the real network/API error and never substitutes fake results.
- **Ports already used:** free ports 8000/3000 or change both ports in the selected runtime configuration and the frontend API URL.
- **DOCX export rejected:** selections are validated against the current query, filters, sort and evidence gate. Re-run the search and export its stable IDs; do not submit catalog IDs directly.
- **PDF reference pack unavailable:** the editable PPTX is retained and the API returns a warning. Install LibreOffice at `C:\Program Files\LibreOffice\program\soffice.exe`, then retry.
- **Word rendering:** runtime export generation does not require Microsoft Word. The test suite validates package integrity and reopens generated files with `python-docx`; see `docs/FILTER_AND_EXPORT_RESULTS.md` for host-specific visual-render validation status.

## Security and scope

The corpus is classified `INTERNAL`. This prototype has no authentication or document-level authorization and must remain in a controlled local demo environment. See `docs/LIMITATIONS.md` before any broader use.
