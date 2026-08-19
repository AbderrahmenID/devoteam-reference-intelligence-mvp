# Retrieval quality hotfix results

## Result

The reproduced stopword explanation and noisy-evidence path is fixed without changing the canonical corpus, BM25 artifact, embeddings, pinned model, or reranker state.

## Before and after

Reproduction query: `Références PCA pour une banque`.

| Behavior | Before | After |
|---|---|---|
| BM25 query tokens | `references, pca, pour, une, banque` | `pca, banque` |
| Removed stopwords | none | `references, pour, une` |
| Explanation | `Exact terms: banque, pour, une` | `Exact acronym: PCA`, `Matching offering: PCA/PCI`, `Matching sector: Banque`, structured semantic/capability reasons |
| BIAT evidence | noisy page-2/3 OCR/table fragments | chunk `cf0c854…`, page 1: `ARTICLE 1 : OBJET … mission d'accompagnement Plan de Continuité d'Activité (PCA) au profit de la BIAT.` |
| Generic BNA line | `Cette attestation est délivrée … pour servir…` | rejected for `NO_MEANINGFUL_QUERY_EVIDENCE`; a project-delivery passage is selected instead |
| Noisy high-score chunks | selected by fused order | rejected by explicit quality diagnostics; cleaner lower-score passage wins |
| Stopword-only query with filters | could receive lexical support | zero results; filters do not bypass relevance/evidence gates |

The saved traces are:

- `.runtime/retrieval-quality-baseline.json`
- `.runtime/retrieval-quality-hotfix.json`

## Affected implementation files

- `retrieval/terms.py`: multilingual term classification, IDF/DF checks, whole-token/phrase matching, protected technologies, concept compatibility.
- `retrieval/evidence.py`: display derivation, evidence quality scoring/reasons, focused excerpts, best-passage selection.
- `retrieval/bm25.py`, `retrieval/hybrid.py`: stopword-free meaningful BM25 query scoring and query diagnostics.
- `retrieval/abstention.py`, `retrieval/service.py`: clean-evidence, metadata, multilingual semantic, and relevance gates.
- `retrieval/schemas.py`: structured match-reason contract.
- `app/frontend/components/ResultCard.tsx`, `app/frontend/app/globals.css`: display-only passages, `dir="auto"`, plaintext bidi, pre-wrapped text, safe wrapping, and readable width.
- `scripts/diagnose_retrieval.py`, `scripts/demo_check.ps1`: reproducible trace and live acceptance assertions.
- `config.yaml`: auditable term/evidence thresholds.

## Automated validation

- Python regression suite: 62 passed; five pre-existing PyMuPDF SWIG deprecation warnings.
- Frontend ESLint: passed with zero warnings.
- Next.js production build: passed.
- Live smoke checks: French, English, Arabic, and mixed-script queries returned source-cited results.
- Live unsupported-scope query: explicit zero-result abstention.
- Reproduction API check: no `Exact terms:` reasons, no missing evidence/reasons, no retrieval prefixes, no reproduced corrupt BIAT passage.
- Debug evidence diagnostics remain absent from API responses while `api.debug: false`.
- Reranker remains disabled.
- Manifest integrity tests prove canonical parquet/index hashes are unchanged.

## Remaining limitations

- Human-reviewed multilingual relevance judgments are still absent; no official recall/precision claim is made.
- Deterministic cleanup cannot repair every possible OCR defect. It rejects or excerpts around unsafe text rather than inventing missing characters.
- The in-app browser surface was unavailable for automated screenshot/click validation. Frontend lint, type/build, source-level bidi assertions, live HTTP, and API-to-component contracts passed.
- Tesseract language packs remain absent for new scanned-PDF preview extraction; existing retrieval assets are unaffected.
