from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from retrieval.bm25 import BM25Index


ROOT = Path(__file__).resolve().parents[1]
V2 = ROOT / "data" / "versions" / "v2"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def test_v1_runtime_assets_remain_byte_identical() -> None:
    baseline = json.loads((ROOT / "data" / "V1_RUNTIME_ASSET_HASHES.json").read_text(encoding="utf-8"))
    for record in baseline["assets"]:
        path = ROOT / record["path"]
        assert path.is_file()
        assert _sha256(path) == record["sha256"]


def test_v2_mapping_covers_each_v1_chunk_exactly_once() -> None:
    v1 = pd.read_parquet(ROOT / "data" / "chunks.parquet")
    mapping = pd.read_csv(V2 / "V1_TO_V2_CHUNK_MAP.csv", keep_default_na=False)
    old = mapping[mapping["v1_chunk_id"] != ""]
    assert len(old) == len(v1)
    assert old["v1_chunk_id"].is_unique
    assert set(old["v1_chunk_id"]) == set(v1["chunk_id"].astype(str))
    assert set(mapping["mapping_status"]) <= {
        "UNCHANGED_RETAINED", "RETRIEVAL_ONLY", "REMOVED_GENERIC", "REPLACED",
        "LINKAGE_REVIEW", "HUMAN_CONFIRMATION_QUARANTINE",
        "HUMAN_CONFIRMATION_RETRIEVAL_ONLY", "REMOVED_AUTOMATED_QUALITY_GATE",
        "REMOVED_EMPTY_RETRIEVAL_TEXT", "NEW_REPAIRED_CHUNK",
    }


def test_disallowed_and_quarantined_chunks_are_absent_from_v2() -> None:
    chunks = pd.read_parquet(V2 / "chunks.parquet")
    policies = pd.read_parquet(V2 / "chunk_policy.parquet")
    quarantine = pd.read_parquet(V2 / "quarantined_chunks.parquet")
    assert chunks["chunk_id"].is_unique
    assert chunks["approved_for_retrieval"].all()
    disallowed = set(
        policies.loc[
            (policies["corpus_version"] == "v1_source_decision_for_v2")
            & ~policies["approved_for_retrieval"],
            "chunk_id",
        ].astype(str)
    )
    assert disallowed.isdisjoint(set(chunks["chunk_id"].astype(str)))
    assert set(quarantine["chunk_id"].astype(str)).isdisjoint(set(chunks["chunk_id"].astype(str)))


def test_repair_provenance_is_complete_and_source_lineage_is_preserved() -> None:
    provenance = pd.read_parquet(V2 / "page_repair_provenance.parquet")
    repaired = pd.read_parquet(V2 / "chunks.parquet").query("repair_id != ''")
    assert len(provenance) == 19
    assert provenance["repair_id"].is_unique
    assert provenance["selected_text_sha256"].str.fullmatch(r"[0-9a-f]{64}").all()
    assert provenance["required_human_follow_up"].eq("YES_VERIFY_REPAIRED_TEXT_AND_LINEAGE").all()
    assert set(repaired["repair_id"]) == set(provenance["repair_id"])
    assert repaired["repair_human_follow_up_required"].all()
    for repair_id, group in repaired.groupby("repair_id"):
        source = provenance.set_index("repair_id").loc[repair_id]
        assert group["document_id"].eq(source["source_document_id"]).all()
        assert group["page_number_1_based"].astype(int).eq(int(source["source_page"])).all()


def test_v2_bm25_dense_and_lookup_rows_align_exactly() -> None:
    chunks = pd.read_parquet(V2 / "chunks.parquet")
    lookup = pd.read_parquet(V2 / "indexes" / "chunk_lookup.parquet")
    embeddings = np.load(V2 / "indexes" / "embeddings.npy", mmap_mode="r")
    bm25 = BM25Index.load(V2 / "indexes" / "bm25_index.npz", V2 / "indexes" / "bm25_vocabulary.json")
    assert chunks["chunk_id"].astype(str).tolist() == lookup["chunk_id"].astype(str).tolist()
    assert lookup["vector_row"].tolist() == list(range(len(lookup)))
    assert len(chunks) == len(lookup) == len(embeddings) == bm25.document_count
    assert embeddings.shape[1] == 768
    assert np.allclose(np.linalg.norm(embeddings, axis=1), 1.0, atol=1e-4)


def test_v2_reference_eligibility_requires_linked_retrieval_evidence() -> None:
    chunks = pd.read_parquet(V2 / "chunks.parquet")
    references = pd.read_parquet(V2 / "reference_catalog.parquet")
    linked_rows: set[int] = set()
    for value in chunks["reference_rows_json"]:
        linked_rows.update(int(row) for row in json.loads(str(value)))
    eligible = references[references["document_retrieval_eligible"]]
    assert not eligible.empty
    assert set(eligible["row_number"].astype(int)) <= linked_rows
    assert references.loc[~references["document_retrieval_eligible"], "evidence_available"].eq(False).all()


def test_v2_keeps_model_weights_thresholds_and_prefix_contract_unchanged() -> None:
    v1 = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    v2 = yaml.safe_load((V2 / "config.v2.yaml").read_text(encoding="utf-8"))
    for section in ("model", "bm25", "dense", "hybrid", "evidence_quality", "abstention", "meaningful_terms"):
        assert v2[section] == v1[section]
    assert v2["model"]["passage_prefix"] == "passage: "
    assert v2["model"]["query_prefix"] == "query: "
