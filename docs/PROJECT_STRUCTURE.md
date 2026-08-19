# Project structure

| Path | Purpose | Classification |
|---|---|---|
| `app/api/` | FastAPI routes, settings, dependencies, and API schemas | Required source |
| `app/frontend/` | Next.js search, selection, and presentation-generation UI | Required source |
| `retrieval/` | BM25, multilingual E5, hybrid ranking, filters, and diagnostics | Required source |
| `reference_narrative/` | Ollama-backed grounded presentation copy and presentation export orchestration | Required source |
| `reference_pack/` | Trusted data validation, evidence handling, template fitting, PPTX/PDF support | Required source |
| `exporting/` | Word reference dossier export | Required source |
| `extraction/` | Evidence extraction helpers used by tests and supported tooling | Required source |
| `data/versions/v2/` | Packaged runtime corpus, metadata, BM25 artifacts, embeddings, mappings, and provenance | Required runtime data |
| `templates/reference_pack/source/` | Immutable approved Devoteam source templates | Required templates |
| `templates/reference_pack/derived/` | Hash-pinned Orange template clone base required by runtime rendering | Required templates |
| `templates/reference_pack/qwen_studio/` | Presentation-format registry and detailed-template field mapping | Required templates |
| `templates/reference_pack/v1/` | Compact-template mapping, logo, and generation settings | Required templates |
| `config/baselines/` | Selected v2 runtime configuration and controlled rollback baselines | Required configuration |
| `evaluation/` | Reproducible technical evaluation inputs and retained final results | Required evaluation material |
| `tests/` | Backend, retrieval, grounding, presentation, PPTX, PDF, and API regressions | Required tests |
| `scripts/` | Setup, preflight, testing, diagnostics, validation, and reproducible evaluation tools | Required tooling |
| `docs/` | Architecture, operation, templates, evaluation, and handoff documentation | Required documentation |

Local-only paths such as `.venv/`, `.runtime/`, `.cache/`, `.tmp/`, `node_modules/`, frontend build output, generated presentations, and audit renders are intentionally excluded by `.gitignore`.

The sibling `Devoteam_AI_CLEAN_PIPELINE` project is an external source lineage system. It is not required by this repository at runtime and is never modified by setup, preflight, startup, or tests.
