# Devoteam multilingual reference retrieval MVP

An internship-scale application that retrieves up to three cited Devoteam references from a validated internal corpus. It combines Unicode BM25 with the pinned local `intfloat/multilingual-e5-base` index, groups evidence at reference level and abstains when evidence is insufficient. It is a retrieval system, not a chatbot, and it never generates fallback results.

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

## Start and stop the full application

```powershell
.\start.ps1
```

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
- **Ports already used:** free ports 8000/3000 or change both ports in `config.yaml` and the frontend API URL.

## Security and scope

The corpus is classified `INTERNAL`. This prototype has no authentication or document-level authorization and must remain in a controlled local demo environment. See `docs/LIMITATIONS.md` before any broader use.

