# Text field lineage

## Runtime lineage

| Stage | Field/artifact | Runtime behavior |
|---|---|---|
| Source document | PDF/JPG named by `source_file_name` | Immutable upstream evidence; not bundled in this MVP. |
| Extracted page text | Upstream canonical page record | The bundled manifest does not include page records. The local preview extractor calls this `original_text`. |
| Chunk source field | `data/chunks.parquet:chunk_text` | Source-faithful canonical chunk, including extraction defects already present upstream. |
| BM25 retrieval text | Prebuilt BM25 postings aligned to chunk rows | The manifest identifies `chunk_text` as the indexed corpus and tokenizer `unicode_fold_v1`; runtime query tokenization uses `normalize_search_text` plus `tokenize_multilingual`. |
| Dense retrieval text | `data/indexes/embeddings.npy` row aligned by `chunk_lookup.parquet` | Prebuilt E5 passage vector. `chunk_lookup.chunk_text` is byte-for-byte equal to `chunks.chunk_text`; only `retrieval_text_sha256` is retained for the original embedding input. |
| Runtime API source | `RetrievalService._build_result` | Copies `chunks.chunk_text` directly into `EvidencePassage.text` and compatibility field `supporting_passage`. |
| JSON response | `supporting_passages[].text` | FastAPI/Pydantic serialize the same Unicode string without cleanup or concatenation. |
| Frontend | `ResultCard` `passage.text` | React renders the API string directly inside a blockquote. No tokenization or normalization is performed in the browser. |

## Proven defect location

The broken fragments are already present in `chunks.parquet:chunk_text`. The same strings appear unchanged in `chunk_lookup.parquet`, the API response, and the result card. Query normalization, JSON serialization, React rendering, and RTL selection do not introduce the corrupt characters or line structure.

The runtime defect is therefore twofold:

1. one source field is incorrectly serving retrieval and display responsibilities; and
2. the highest-ranked raw chunk is displayed without a readability gate or evidence-aware selection.

The hotfix will derive `retrieval_text` and `display_text` in memory. It will not overwrite either parquet asset.
