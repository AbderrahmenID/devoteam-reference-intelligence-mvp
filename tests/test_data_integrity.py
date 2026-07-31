from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def test_manifest_files_exist_and_hashes_match() -> None:
    manifest = json.loads((ROOT / "data/DATA_MANIFEST.json").read_text(encoding="utf-8"))
    for item in manifest["files"]:
        path = ROOT / item["destination_path"]
        assert path.is_file(), item["destination_path"]
        assert path.stat().st_size == item["file_size"]
        assert _sha256(path) == item["sha256"]


def test_catalog_and_index_integrity() -> None:
    chunks = pd.read_parquet(ROOT / "data/chunks.parquet")
    references = pd.read_parquet(ROOT / "data/reference_catalog.parquet")
    lookup = pd.read_parquet(ROOT / "data/indexes/chunk_lookup.parquet")
    embeddings = np.load(ROOT / "data/indexes/embeddings.npy", mmap_mode="r")

    required_chunk_columns = {
        "chunk_id", "document_id", "chunk_text", "page_number_1_based", "citation_label",
        "citation_uri", "reference_rows_json", "client_values_json", "sector_values_json",
        "offering_values_json", "security_classification",
    }
    required_reference_columns = {
        "reference_id", "row_number", "client", "sector", "offering",
        "document_retrieval_eligible",
    }
    assert required_chunk_columns <= set(chunks.columns)
    assert required_reference_columns <= set(references.columns)
    assert len(chunks) == len(lookup) == embeddings.shape[0] == 1185
    assert embeddings.shape[1] == 768
    assert chunks.chunk_id.is_unique and lookup.chunk_id.is_unique
    assert references.reference_id.is_unique
    assert chunks.chunk_id.astype(str).tolist() == lookup.chunk_id.astype(str).tolist()
    assert chunks.page_number_1_based.notna().all()
    assert np.isfinite(embeddings).all()
    assert np.allclose(np.linalg.norm(embeddings, axis=1), 1.0, atol=1e-5)

    catalog_rows = set(references.row_number.astype(int))
    linked_rows = {int(row) for raw in chunks.reference_rows_json for row in json.loads(raw)}
    assert linked_rows <= catalog_rows
    assert not references[references.document_retrieval_eligible & ~references.row_number.isin(linked_rows)].any().any()


def test_multilingual_text_survives_parquet_loading() -> None:
    chunks = pd.read_parquet(ROOT / "data/chunks.parquet", columns=["chunk_text"])
    text = "\n".join(chunks.chunk_text.astype(str))
    assert re.search(r"[\u0600-\u06ff]", text)
    assert re.search(r"[éèêàçùôîÉÈÊÀÇÙÔÎ]", text)

