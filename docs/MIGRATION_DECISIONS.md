# Migration decisions

| Source asset | Decision | Destination | Reason |
|---|---|---|---|
| `phase4_corpus_v1/chunks.parquet` | COPY | `data/chunks.parquet` | Validated evidence chunks with citations and multilingual text |
| `phase4_corpus_v1/reference_catalog.parquet` | COPY | `data/reference_catalog.parquet` | Reference-level metadata and stable IDs |
| Corpus statistics/filter values/Phase 4 manifest | COPY | `data/source_metadata/` | Provenance, counts and filter inspection |
| Phase 5 BM25 index and vocabulary | COPY | `data/indexes/` | Compatible, tested Unicode lexical index |
| Phase 5 embeddings and chunk lookup | COPY | `data/indexes/` | Preserve pinned E5 vectors and exact row order without regeneration |
| Phase 5 manifest/runtime metadata | COPY | `data/indexes/` | Validate model, prefixes, dimensions and corpus identity |
| `phase5_bm25.py` behavior | REIMPLEMENT | `retrieval/bm25.py`, `retrieval/normalization.py` | Keep a small standalone implementation and original artifact format |
| `phase5_retrieval.py` behavior | REIMPLEMENT | `retrieval/dense.py`, `retrieval/hybrid.py`, `retrieval/service.py` | One minimal retrieval service, offline-only model loading and no FAISS requirement |
| Language/chunking/extraction behavior | REIMPLEMENT | `retrieval/language.py`, `extraction/` | Focused MVP utilities with explicit provenance and safe normalization |
| Phase 5.2 abstention-related signals | REIMPLEMENT | `retrieval/abstention.py` | Deterministic configurable no-evidence gate; opportunity scoring excluded |
| `documents_catalog.parquet` | EXCLUDE | — | Runtime joins can be validated from the selected catalogs and lookup |
| `canonical_pages.parquet` and `chunks.jsonl` | EXCLUDE | — | Duplicate/expanded storage not needed by query runtime |
| `faiss.index` | EXCLUDE | — | 1,185-vector NumPy dot product is simple and fast; avoids binary FAISS dependency |
| Repair pipeline and full Phase 3 orchestration | EXCLUDE | — | Full corpus rebuild is out of scope; bounded extraction preview remains |
| Raw PDFs/images/Office documents | EXCLUDE | — | Not required for retrieval and would expand/sensitize the MVP |
| Notebooks, packages, reports, BRID and Phase 6–8 outputs | EXCLUDE | — | Historical or unrelated deliverables |
| Caches, bytecode, logs and build output | EXCLUDE | — | Generated artifacts do not belong in the clean project |

No accidental asset has been copied. Any later accidental copy will be logged here before removal from the MVP only.

