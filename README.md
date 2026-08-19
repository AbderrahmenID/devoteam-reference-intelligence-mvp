# Devoteam Reference Intelligence

Multilingual hybrid reference retrieval and AI-assisted presentation generation for Devoteam commercial opportunities.

## Overview

Devoteam teams need to find credible past experience quickly, connect every claim to approved project evidence, and turn the selected references into client-ready material. This private internal MVP packages that workflow in one application: multilingual retrieval over a trusted corpus, controlled reference selection, grounded local-AI copy generation, and editable presentation export.

The processed runtime corpus and indexes are included. A supervisor can clone and run the application without rebuilding the confidential source-document pipeline.

## Features

- Search in French, English, and Arabic.
- Unicode BM25 lexical retrieval plus `intfloat/multilingual-e5-base` semantic retrieval.
- Deterministic weighted hybrid ranking, hard metadata filters, reference aggregation, and abstention controls.
- Evidence-backed results with source lineage and page-level support.
- Selected-reference review workflow.
- Local AI generation through Ollama and `qwen3.5:9b`.
- Detailed Challenges / Réalisations / Bénéfices copy and Compact Orange copy.
- Grounding, language, evidence-coverage, and template-fit validation.
- Approved Devoteam source templates, editable PPTX output, and LibreOffice PDF conversion.
- Python API, retrieval, data-integrity, presentation, PPTX/PDF, and frontend tests.

## Architecture

```text
Packaged trusted corpus
          ↓
Unicode BM25 + multilingual E5
          ↓
Weighted hybrid retrieval + filters
          ↓
Evidence-backed reference selection
          ↓
Local Ollama / qwen3.5:9b
          ↓
Template-specific grounded copy
          ↓
Approved Devoteam PPTX templates
          ↓
Editable PPTX / PDF
```

The pipeline produces normalized E5 embeddings and a FAISS index. At the packaged MVP scale of 1,185 chunks, the application deliberately performs the same normalized inner-product search directly over the committed NumPy matrix. This exact search avoids a platform-specific FAISS runtime dependency while preserving deterministic dense retrieval and source-index alignment.

## Technology Stack

- Python 3.10 or 3.11, FastAPI, Pydantic, pandas, PyArrow, NumPy
- Unicode BM25, `multilingual-e5-base`, FAISS-compatible normalized embeddings, weighted rank fusion
- Next.js 16, React 19, TypeScript
- Ollama with `qwen3.5:9b`
- `python-pptx`, PyMuPDF, pypdf, LibreOffice
- pytest, Node test runner, ESLint

## Repository Structure

```text
app/api/                 FastAPI application, routes, and settings
app/frontend/            Next.js user interface and frontend tests
config/                  Selected retrieval and rollback configurations
data/                    Required v1 lineage and reviewed v2 runtime artifacts
retrieval/               BM25, E5, dense scoring, hybrid ranking, filters
reference_narrative/     Grounded AI copy generation and quality controls
reference_pack/          Template mapping, PPTX generation, and PDF export
templates/               Approved source templates and rendering configuration
evaluation/              Regression queries, judgments, metrics, and reports
tests/                   Backend, retrieval, integrity, and presentation tests
scripts/                 Setup, preflight, validation, and test entry points
docs/                    Focused architecture and operating documentation
```

See [Project structure](docs/PROJECT_STRUCTURE.md) and [Architecture](docs/ARCHITECTURE.md) for more detail.

## Requirements

- Windows 10 or 11 with PowerShell 5.1 or newer
- Python 3.10 or 3.11
- Node.js 20.9 or newer and npm
- Ollama 0.32.14 (validated) with `qwen3.5:9b`
- LibreOffice with `soffice` on `PATH` or in its standard Windows installation directory
- The pinned `intfloat/multilingual-e5-base` revision `a114a4100c6714cf21651971eefe9191a4415dbb` in the current user's Hugging Face cache

Model weights and model caches are external dependencies and are never stored in Git.

## Installation

```powershell
git clone https://github.com/AbderrahmenID/devoteam-reference-intelligence-mvp.git
cd devoteam-reference-intelligence-mvp
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[dev]"
Set-Location app\frontend
npm ci
Set-Location ..\..
```

The equivalent automated setup is:

```powershell
.\scripts\setup.ps1
```

## Ollama and E5 Models

Install the local generation model:

```powershell
ollama pull qwen3.5:9b
```

Download the pinned E5 model outside the repository:

```powershell
.\.venv\Scripts\hf.exe download intfloat/multilingual-e5-base --revision a114a4100c6714cf21651971eefe9191a4415dbb
```

Normal startup is offline-only and does not download either model automatically.

## Configuration

```powershell
Copy-Item .env.example .env
```

The checked-in example selects the packaged v2 corpus, local FastAPI endpoint, local Ollama endpoint, and approved model. `.env` is ignored and must not be committed.

Validate the complete local runtime before starting:

```powershell
.\scripts\preflight.ps1
```

## Running

```powershell
.\start.ps1
```

- Application: <http://127.0.0.1:3000>
- API health: <http://127.0.0.1:8000/health>
- API documentation: <http://127.0.0.1:8000/docs>

Stop only the processes recorded by this project:

```powershell
.\stop.ps1
```

## Usage

1. Describe the opportunity or expertise required.
2. Refine results with the sidebar filters.
3. Select the strongest evidence-backed references.
4. Review the selection and generate a presentation.
5. Choose Compact Orange or Detailed Challenges / Réalisations / Bénéfices.
6. Choose PPTX, PDF, or both.
7. Download and review the editable deliverable.

## Tests

Run the complete validation suite:

```powershell
.\scripts\test.ps1
```

Focused commands:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe scripts\run_retrieval_improvement_regression.py
Set-Location app\frontend
npm test
npm run lint
npm run build
```

## Data Pipeline

Data preparation pipeline: [devoteam-reference-data-pipeline](https://github.com/AbderrahmenID/devoteam-reference-data-pipeline)

The separate private pipeline inventories authorized source documents, performs extraction/OCR and quality repair, constructs evidence lineage, creates the trusted corpus, and builds retrieval artifacts. The MVP consumes reviewed processed artifacts and never needs confidential raw client documents at startup.

## Additional Documentation

- [Retrieval runtime](docs/RETRIEVAL_RUNTIME_V2.md)
- [AI presentation backend](docs/AI_REFERENCE_NARRATIVE_BACKEND.md)
- [Presentation formats](docs/AI_REFERENCE_PRESENTATION_FORMATS.md)
- [Template field mapping](docs/TEMPLATE_FIELD_MAPPING.md)
- [Export requirements](docs/EXPORT.md)
- [Known limitations](docs/LIMITATIONS.md)

## Limitations

- This is a private internal MVP without user authentication or document-level authorization.
- The validated launcher and LibreOffice export workflow are Windows-oriented.
- E5 and Ollama model weights must be installed separately on each machine.
- Generated copy remains subject to consultant review and evidence-grounding controls.

No open-source license is granted. Devoteam-related code, data, templates, and generated material remain subject to company approval and access controls.
