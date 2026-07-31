# MVP data

This directory contains only the validated Phase 4 corpus assets and Phase 5 retrieval artifacts needed at runtime. Source PDFs, canonical pages, duplicate JSONL data, notebooks and historical outputs are intentionally excluded.

`DATA_MANIFEST.json` records source/destination paths, sizes, hashes, counts, schemas and inclusion reasons. The runtime validates the manifest and never writes to the source project. The evidence is classified `INTERNAL`; this prototype has no document-level authorization and must not be exposed as a public service.

