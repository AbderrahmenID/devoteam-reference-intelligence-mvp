# AI Reference Narrative Model Benchmark

> **DEVELOPMENT / NON-PRODUCTION** — Phase 2.2, 2026-08-14

## A. Hardware/environment

- Windows 10 build 26200; Python 3.10.11; Ollama 0.32.9.
- NVIDIA GeForce RTX 5070 Laptop GPU, driver 596.36, 8,151 MiB VRAM.
- Physical RAM: 31.12 GiB. Free RAM before pulls: 17.55 GiB; benchmark snapshot: 14.49 GiB; final idle snapshot: 15.92 GiB.
- C: capacity: 895.38 GiB. Free before pulls: 29.01 GiB; after both approved installs and final cleanup: 21.07 GiB.
- A conservative 15 GiB absolute free-disk floor was set before either pull. `qwen3:8b` was pulled first; the second pull was authorized only after the measured/projected free space remained above that floor.
- Initial VRAM was 7,891 MiB free. Final idle VRAM was also 7,891 MiB free.
- All benchmark models were unloaded before each candidate block. Cold-load latency is included. This runtime isolation used an unload request only; generation remained on `POST /api/chat`.

## B. Models tested

Exactly these models were tested, in the required order:

1. `qwen2.5-coder:7b-instruct`
2. `qwen3:8b`
3. `qwen3.5:9b`

No other model was downloaded, removed, substituted or benchmarked. The pre-existing `gemma4:latest` installation was not used. No global Ollama configuration was changed.

## C. Model artifact sizes

| Model | Ollama digest | Size | Parameters / quantization |
|---|---|---:|---|
| `qwen2.5-coder:7b-instruct` | `dae161e27b0e…` | 4,683,087,561 bytes (4.7 GB) | 7.6B / Q4_K_M |
| `qwen3:8b` | `500a1f067a9f…` | 5,225,388,164 bytes (5.2 GB) | 8.2B / Q4_K_M |
| `qwen3.5:9b` | `6488c96fa5fa…` | 6,594,474,711 bytes (6.6 GB) | 9.7B / Q4_K_M |

## D. Eight-case results

Every model was attempted on the unchanged Phase 2.1 fixture. “Fields” is populated eligible fields over eligible fields; empty fields with an empty `FieldSupportPlan` are excluded.

| Case | `qwen2.5-coder:7b-instruct` | `qwen3:8b` | `qwen3.5:9b` |
|---|---|---|---|
| `bct_pca_french` | OK; language pass; valid; fields 1/5; drift 0; 27.3s | Timeout; 139.2s | OK; language pass; invalid; fields 1/5; drift 1; 33.9s |
| `rich_bct_governance_french` | OK; language pass; invalid; fields 0/6; drift 2; 18.5s | Timeout; 120.1s | OK; language pass; invalid; fields 6/6; drift 1; 36.7s |
| `sparse_bmci_english` | OK; language fail; invalid; fields 1/5; drift 1; 18.5s | Timeout; 128.2s | OK; language fail; invalid; fields 1/5; drift 3; 26.0s |
| `multi_reference_french` | OK; language pass; invalid; fields 4/16; drift 10; 51.4s | Timeout; 128.3s | OK; language pass; invalid; fields 6/16; drift 2; 65.1s |
| `cross_language_bct_english` | OK; language pass; valid; fields 0/5; drift 0; 11.7s | Timeout; 123.9s | OK; language pass; invalid; fields 1/5; drift 2; 15.8s |
| `rich_bct_english` | OK; language pass; invalid; fields 0/6; drift 4; 14.4s | Timeout; 120.1s | OK; language pass; invalid; fields 6/6; drift 3; 36.6s |
| `sparse_bmci_french` | OK; language pass; invalid; fields 0/5; drift 2; 16.1s | Timeout; 140.7s | OK; language pass; valid; fields 3/5; drift 0; 19.7s |
| `bct_pca_arabic` | OK; language fail; invalid; fields 0/5; drift 1; 8.0s | OK; language pass; valid; fields 4/5; drift 0; 17.7s | OK; language pass; valid; fields 0/5; drift 0; 19.9s |

## E. Schema reliability

| Model | Completed/schema success | Provider timeout | Structured repairs |
|---|---:|---:|---:|
| `qwen2.5-coder:7b-instruct` | 8/8 (100%) | 0 | 0 |
| `qwen3:8b` | 1/8 (12.5%) | 7 | 0 |
| `qwen3.5:9b` | 8/8 (100%) | 0 | 0 |

All requests used `stream=false`, `think=false`, temperature 0, the accepted 120-second per-call timeout, the existing single structured-output repair policy, and prompt version `reference-narrative-phase2.1-prose-v1`. There were no model-specific compatibility adjustments. The seven `qwen3:8b` failures were provider timeouts, not malformed-JSON repair failures.

## F. Factual-fidelity failures

| Model | Blocking drift | Principal codes |
|---|---:|---|
| `qwen2.5-coder:7b-instruct` | 20 | 6 unsupported completion; 4 success claims; 4 named entities; 3 unsupported clients; 3 unattested completion details |
| `qwen3:8b` | 0 | Only one case completed; the zero is not comparable with full-suite models |
| `qwen3.5:9b` | 12 | 5 unsupported completion; 3 named entities; 1 unattested completion detail; 1 sector; 1 number; 1 offering |

These are model-quality failures. They did not alter or weaken backend provenance. Proposal/completion confusion occurred six times for the baseline and five times for `qwen3.5:9b`.

## G. Language compliance

The deterministic check requires Arabic script to comprise at least 60% of Arabic-plus-Latin letters for Arabic. French and English use a function-word marker share of at least 60%, at least three markers, and less than 20% Arabic script. Technical terms and proper nouns remain permitted.

| Model | Compliant cases / all attempts | Rate |
|---|---:|---:|
| `qwen2.5-coder:7b-instruct` | 6/8 | 75.0% |
| `qwen3:8b` | 1/8 | 12.5% |
| `qwen3.5:9b` | 7/8 | 87.5% |

Timed-out cases cannot satisfy the language gate. Both full-suite models failed `sparse_bmci_english`; the output was substantially mixed with French. The baseline also failed Arabic. Language failures are recorded separately from provenance.

## H. Narrative completeness

| Model | Eligible | Populated | Empty | Unusable populated | Usable populated | Population rate |
|---|---:|---:|---:|---:|---:|---:|
| `qwen2.5-coder:7b-instruct` | 53 | 6 | 47 | 5 | 1 | 11.3% |
| `qwen3:8b` | 5 | 4 | 1 | 0 | 4 | 80.0% on its sole completed case |
| `qwen3.5:9b` | 53 | 24 | 29 | 5 | 19 | 45.3% |

`qwen3.5:9b` is materially more complete than the baseline, but completeness did not compensate for factual drift. `qwen3:8b` is not comparable because seven cases produced no narrative. Unsupported fields with an empty plan were never counted as eligible and were not penalized.

## I. Latency

| Model | Median | P95 | Prompt tokens | Generated tokens |
|---|---:|---:|---:|---:|
| `qwen2.5-coder:7b-instruct` | 17.28s | 42.96s | 14,502 | 1,626 |
| `qwen3:8b` | 126.07s | 140.15s | 7,844 available | 440 available |
| `qwen3.5:9b` | 29.94s | 55.15s | 13,914 | 2,216 |

Cold-load latency is included for the first case of each model. Latency is secondary to factual and language quality.

## J. Export eligibility

- `qwen2.5-coder:7b-instruct`: 2/8 valid and export-eligible.
- `qwen3:8b`: 1/8 valid and export-eligible; seven cases failed before validation.
- `qwen3.5:9b`: 2/8 valid and export-eligible.

No model approaches an acceptable full-suite export rate.

## K. BCT behavior

- French PCA: the baseline was valid but populated only 1/5 eligible fields; `qwen3:8b` timed out; `qwen3.5:9b` populated 1/5 and was blocked for unsupported completion language.
- Rich French governance: `qwen3.5:9b` populated 6/6 fields but was blocked for completion language; the baseline populated 0/6 and had two drift findings; `qwen3:8b` timed out.
- Cross-language English PCA: the baseline was valid but populated 0/5 fields. `qwen3.5:9b` populated 1/5 and introduced two completion findings. `qwen3:8b` timed out.
- Arabic PCA: the baseline used the wrong language and drifted. Both candidates passed the script check and strict validator, but `qwen3.5:9b` left all five eligible reference fields empty. The sole completed `qwen3:8b` response populated 4/5 yet exposed schema-like tokens such as “items/type/string” in prose; blind human review would therefore still reject its commercial quality.
- Across all BCT cases, identity and deterministic support ownership remained correct.

## L. French observations

The two full-suite models passed the deterministic language check on all four French cases. `qwen3.5:9b` was more complete, especially on rich evidence, but its French prose still produced completion, sector and named-entity drift. The baseline was sparse and produced substantially more drift in the three-reference synthesis. `qwen3:8b` timed out on all French cases.

## M. English observations

Both full-suite models passed two of three English cases and failed the sparse BMCI case through French/English mixing. `qwen3.5:9b` populated more rich-evidence fields but still introduced completion and named-entity claims. `qwen3:8b` timed out on all English cases.

## N. Arabic observations

The baseline failed the Arabic language check. `qwen3:8b` and `qwen3.5:9b` passed the script check on the Arabic case, but neither supplied acceptable proposal-ready reference prose: one leaked schema vocabulary and the other abstained on all eligible per-reference fields. Arabic script compliance alone is therefore insufficient.

## O. Blind-review artifact locations

- Eight packets: `evaluation/reference_narrative/model_benchmark/blind_reviews/CASE_<id>_BLIND_REVIEW.md`
- Confidential mapping: `evaluation/reference_narrative/model_benchmark/BLIND_CANDIDATE_MAPPING.json`
- Candidate A = `qwen3.5:9b`; Candidate B = baseline; Candidate C = `qwen3:8b`.

Every packet contains Candidate A/B/C, all requested narrative fields, five blank 1–5 rubric items and a blank reviewer-comments area. Automated checks found no model-name leak in blind packets. No human scores were filled, and no aggregate model score was created.

## P. Automated test results

- Focused narrative suite: 63 passed.
- Full Python suite: 157 passed.
- Explicit retrieval regression file: 5 passed.
- New benchmark-only unit tests: 10 passed without live Ollama.
- Evaluation artifact safety audit: 27 JSON files and 8 blind packets checked; zero confidential source-bundle keys, zero blind model-name leaks, and zero rubric-structure failures.
- `git diff --check`: passed.

## Q. Files changed

- Added deterministic language, completeness and factual-drift metrics in `reference_narrative/quality.py`.
- Added Ollama token/duration telemetry in `reference_narrative/ollama_client.py` and per-case capture in `scripts/evaluate_reference_narrative.py`.
- Added `scripts/benchmark_reference_narrative_models.py` and offline tests in `tests/test_reference_narrative_benchmark.py`.
- Added benchmark environment, summaries, 24 raw safe case results, eight blind-review packets and the confidential candidate mapping under `evaluation/reference_narrative/model_benchmark/`.
- Added this report. No Phase 2.1 provenance policy, prompt, schema, validator, retrieval behavior, frontend, PPTX or PDF implementation was changed. The protected `Devoteam_AI_CLEAN_PIPELINE` directory was not modified.

## R. Recommendation

**NO_LOCAL_MODEL_READY**

No candidate passes all selection gates. The baseline fails language, repeated-drift and proposal/completion gates. `qwen3:8b` fails schema reliability through seven timeouts and its sole completed narrative is not commercially usable. `qwen3.5:9b` is the best relative model for completeness and multilingual adherence, but it still fails language, repeated factual-drift and proposal/completion gates and yields only 2/8 export-eligible cases. Human blind-review artifacts are available for diagnosis, not for progression to Phase 3.
