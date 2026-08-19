# Filter and export baseline

Recorded before implementation on 31 July 2026 (Africa/Tunis).

## Source-control state

- Baseline commit: `c378ad86b0917e01b3e24ac2b56eeecccd8691b0`
- Commit subject: `Build multilingual Devoteam reference retrieval MVP`
- Working tree: clean before the validation run
- Runtime: stopped before validation

## Complete baseline validation

Command:

```powershell
.\scripts\test.ps1
```

Result: **PASS**.

- Backend: 24 pytest tests passed.
- Evaluation: `HUMAN_JUDGMENTS_REQUIRED`; metrics remained null because no human qrels were supplied.
- Frontend lint: passed with zero warnings.
- Frontend production build: passed with Next.js 15.5.7.
- Reranker: disabled.

The five PyMuPDF SWIG deprecation warnings emitted by the baseline are non-failing dependency warnings.

## Immutable runtime assets

- Reference catalog: 161 rows, including 138 retrieval-eligible references.
- Evidence chunks: 1,185 rows.
- Dense vectors: 1,185 x 768, finite and normalized.
- Local E5 model snapshot: `a114a4100c6714cf21651971eefe9191a4415dbb`.
- Original Word template: `templates/Template Ref.docx`.
- Original template SHA-256: `A58E409010992F9A8B7A958EBBC7BF7D3FE06DC1043287FD2DB72BEDCA5334DA`.

No corpus migration, extraction, embedding generation, index regeneration, model download, reranking, or source-data mutation is part of this extension.

## Baseline behavior to preserve

- Multilingual French, English, Arabic, and mixed-script query handling.
- Hybrid BM25 plus multilingual E5 retrieval.
- Reference-level grouping and source citations.
- Deterministic abstention for empty, unsupported, and insufficient-evidence queries.
- Security classification masking.
- Exact data-manifest hash verification.

The former three-result cap is the only intentional retrieval-output limit being removed. The evidence gate remains mandatory and will be applied independently to every candidate reference before pagination.
