from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from extraction.chunking import chunk_page
from retrieval.bm25 import BM25Index
from retrieval.evidence import EvidenceQualityEvaluator, clean_display_text, derive_display_text
from retrieval.language import analyze_language
from retrieval.normalization import normalize_search_text, tokenize_multilingual
from retrieval.terms import QueryTermAnalysis
try:
    from import_final_review import _normalize_bool, read_xlsx_sheet, sha256_file
except ModuleNotFoundError:
    from scripts.import_final_review import _normalize_bool, read_xlsx_sheet, sha256_file


ROOT = Path(__file__).resolve().parents[1]
V2_ROOT = ROOT / "data" / "versions" / "v2"
PIPELINE_VERSION = "targeted_repair_v2"


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def stable_id(*values: object) -> str:
    return sha256_text("\x1f".join(str(value) for value in values))


def empty_query_terms() -> QueryTermAnalysis:
    return QueryTermAnalysis("", [], [], [], [], [], [], [])


def build_repaired_chunks(
    repaired_pages: pd.DataFrame,
    v1_chunks: pd.DataFrame,
    config: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[tuple[str, int], list[str]]]:
    evaluator = EvidenceQualityEvaluator(config["evidence_quality"])
    output: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    ids_by_page: dict[tuple[str, int], list[str]] = {}
    for page_record in repaired_pages.to_dict(orient="records"):
        document_id = str(page_record["source_document_id"])
        page_number = int(page_record["source_page"])
        page_v1 = v1_chunks[
            (v1_chunks["document_id"].astype(str) == document_id)
            & (v1_chunks["page_number_1_based"].astype(int) == page_number)
        ].copy()
        if page_v1.empty:
            raise AssertionError(f"No v1 page metadata for {document_id} page {page_number}")
        base = page_v1.iloc[0].to_dict()
        display_page_text = str(page_record["selected_display_text"])
        source_page_text = str(page_record["selected_text"])
        page_language = analyze_language(display_page_text)
        new_page_id = stable_id(
            PIPELINE_VERSION,
            document_id,
            page_number,
            page_record["selected_text_sha256"],
        )
        chunk_inputs = chunk_page(
            {
                "source_filename": base["source_file_name"],
                "page_number": page_number,
                "original_text": display_page_text,
                "quality_status": "REPAIRED_PENDING_HUMAN_FOLLOW_UP",
            },
            maximum=int(config["extraction"]["chunk_max_characters"]),
            overlap=int(config["extraction"]["chunk_overlap_characters"]),
            minimum=int(config["extraction"]["chunk_min_characters"]),
        )
        union_fields = [column for column in v1_chunks.columns if column.endswith("_values_json")]
        union_metadata: dict[str, str] = {}
        for column in union_fields:
            values: list[Any] = []
            for raw in page_v1[column]:
                try:
                    decoded = json.loads(str(raw))
                except (TypeError, ValueError, json.JSONDecodeError):
                    decoded = []
                values.extend(decoded if isinstance(decoded, list) else [])
            union_metadata[column] = json.dumps(list(dict.fromkeys(values)), ensure_ascii=False)
        reference_rows: list[int] = []
        for raw in page_v1["reference_rows_json"]:
            try:
                reference_rows.extend(int(value) for value in json.loads(str(raw)))
            except (TypeError, ValueError, json.JSONDecodeError):
                pass
        reference_rows_json = json.dumps(sorted(set(reference_rows)))
        page_chunk_ids: list[str] = []
        for chunk_input in chunk_inputs:
            retrieval_text = clean_display_text(chunk_input["original_text"])
            display_text = derive_display_text(retrieval_text)
            quality = evaluator.evaluate(
                retrieval_text,
                retrieval_text,
                empty_query_terms(),
                dense_score=0.0,
                query_language="und",
                extraction_quality="REPAIRED_PENDING_HUMAN_FOLLOW_UP",
            )
            chunk_index = int(chunk_input["chunk_index"])
            chunk_id = stable_id(PIPELINE_VERSION, new_page_id, chunk_index, retrieval_text)
            record = dict(base)
            record.update(union_metadata)
            record.update(
                {
                    "chunk_id": chunk_id,
                    "page_id": new_page_id,
                    "pipeline_version": PIPELINE_VERSION,
                    "page_number_1_based": page_number,
                    "chunk_index_in_page": chunk_index,
                    "character_start": int(chunk_input["character_start"]),
                    "character_end": int(chunk_input["character_end"]),
                    "chunk_character_count": len(retrieval_text),
                    "chunk_word_count": len(retrieval_text.split()),
                    "chunk_text_sha256": sha256_text(retrieval_text),
                    "chunk_text": retrieval_text,
                    "page_language": page_language.detected_language,
                    "document_language": page_language.detected_language,
                    "data_quality_status": "REPAIRED_PENDING_HUMAN_FOLLOW_UP",
                    "reference_rows_json": reference_rows_json,
                    "exact_duplicate_count": 1,
                    "duplicate_group_id": "",
                    "original_source_text": source_page_text,
                    "retrieval_text": retrieval_text,
                    "display_text": display_text,
                    "approved_for_retrieval": bool(quality.quality_pass),
                    "approved_for_display": bool(quality.quality_pass),
                    "policy_source": "TARGETED_REPAIR_QUALITY_GATE",
                    "policy_action": "REPAIRED_CHUNK" if quality.quality_pass else "REPAIRED_CHUNK_QUALITY_REJECTED",
                    "evidence_quality_score": quality.quality_score,
                    "evidence_quality_reasons_json": json.dumps(quality.rejection_reasons),
                    "repair_id": page_record["repair_id"],
                    "repair_method": page_record["selected_extraction_method"],
                    "repair_ocr_confidence": page_record["selected_ocr_confidence"],
                    "repair_human_follow_up_required": True,
                    "replaces_v1_chunk_ids_json": json.dumps(sorted(page_v1["chunk_id"].astype(str))),
                }
            )
            if quality.quality_pass and tokenize_multilingual(retrieval_text):
                output.append(record)
                page_chunk_ids.append(chunk_id)
            else:
                record["quarantine_reason"] = "REPAIRED_CHUNK_FAILED_EVIDENCE_QUALITY_GATE"
                rejected.append(record)
        if not page_chunk_ids:
            raise AssertionError(f"Repair produced no usable v2 chunks for {document_id} page {page_number}")
        ids_by_page[(document_id, page_number)] = page_chunk_ids
    return output, rejected, ids_by_page


def build_policy(
    v1_chunks: pd.DataFrame,
    repaired_page_keys: set[tuple[str, int]],
    replacement_ids: dict[tuple[str, int], list[str]],
    review_by_chunk: dict[str, dict[str, str]],
    audit_by_chunk: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, str]]]:
    retained: list[dict[str, Any]] = []
    quarantine: list[dict[str, Any]] = []
    policy_rows: list[dict[str, Any]] = []
    mappings: list[dict[str, str]] = []
    for original in v1_chunks.to_dict(orient="records"):
        chunk_id = str(original["chunk_id"])
        page_key = (str(original["document_id"]), int(original["page_number_1_based"]))
        review = review_by_chunk.get(chunk_id)
        audit = audit_by_chunk[chunk_id]
        retrieval = False
        display = False
        source = "AUTOMATED_FULL_CORPUS_AUDIT"
        action = ""
        mapping_status = ""
        v2_chunk_ids = ""

        if page_key in repaired_page_keys:
            source = "TARGETED_PAGE_REPAIR"
            action = "REPLACED_BY_REPAIRED_PAGE"
            mapping_status = "REPLACED"
            v2_chunk_ids = ";".join(replacement_ids[page_key])
        elif review is not None:
            source = "HUMAN_REVIEW_FINAL"
            action = str(review["final_action"])
            retrieval = _normalize_bool(review["approved_for_retrieval"]) == "YES"
            display = _normalize_bool(review["approved_for_display"]) == "YES"
            mapping_status = {
                "KEEP_RETRIEVAL_AND_DISPLAY": "UNCHANGED_RETAINED",
                "KEEP_RETRIEVAL_ONLY": "RETRIEVAL_ONLY",
                "EXCLUDE_GENERIC_OR_NON_EVIDENTIARY_TEXT": "REMOVED_GENERIC",
                "REVIEW_REFERENCE_LINKAGE": "LINKAGE_REVIEW",
                "HUMAN_CONFIRMATION_REQUIRED": "HUMAN_CONFIRMATION_RETRIEVAL_ONLY" if retrieval else "HUMAN_CONFIRMATION_QUARANTINE",
                "REPAIR_OR_REEXTRACT": "REPLACED",
            }[action]
            v2_chunk_ids = chunk_id if retrieval else ""
        else:
            retrieval = bool(audit["evidence_quality_pass"])
            display = retrieval
            action = "AUTO_QUALITY_PASS" if retrieval else "AUTO_QUALITY_REJECT"
            mapping_status = "UNCHANGED_RETAINED" if retrieval else "REMOVED_AUTOMATED_QUALITY_GATE"
            v2_chunk_ids = chunk_id if retrieval else ""

        if display and not retrieval:
            raise AssertionError(f"Display approval without retrieval approval for {chunk_id}")
        policy = {
            "corpus_version": "v1_source_decision_for_v2",
            "chunk_id": chunk_id,
            "approved_for_retrieval": retrieval,
            "approved_for_display": display,
            "policy_source": source,
            "policy_action": action,
            "automatic_classification": audit["automatic_classification"],
            "automatic_reason": audit["automatic_reason"],
            "human_classification": review["human_classification"] if review else "",
            "human_follow_up_required": action in {"HUMAN_CONFIRMATION_REQUIRED", "REVIEW_REFERENCE_LINKAGE"},
        }
        policy_rows.append(policy)
        mappings.append(
            {
                "v1_chunk_id": chunk_id,
                "v2_chunk_ids": v2_chunk_ids,
                "mapping_status": mapping_status,
                "policy_source": source,
                "policy_action": action,
                "document_id": str(original["document_id"]),
                "page_number_1_based": str(original["page_number_1_based"]),
            }
        )
        if retrieval:
            record = dict(original)
            record.update(
                {
                    "original_source_text": str(original["chunk_text"]),
                    "retrieval_text": str(original["chunk_text"]),
                    "display_text": derive_display_text(original["chunk_text"]),
                    "approved_for_retrieval": True,
                    "approved_for_display": display,
                    "policy_source": source,
                    "policy_action": action,
                    "evidence_quality_score": float(audit["evidence_quality_score"]),
                    "evidence_quality_reasons_json": json.dumps(
                        [value for value in str(audit["rejection_reasons"]).split(";") if value]
                    ),
                    "repair_id": "",
                    "repair_method": "",
                    "repair_ocr_confidence": np.nan,
                    "repair_human_follow_up_required": False,
                    "replaces_v1_chunk_ids_json": "[]",
                }
            )
            if tokenize_multilingual(str(record["retrieval_text"])):
                retained.append(record)
            else:
                record["quarantine_reason"] = "EMPTY_RETRIEVAL_TOKEN_SEQUENCE"
                quarantine.append(record)
                mappings[-1]["v2_chunk_ids"] = ""
                mappings[-1]["mapping_status"] = "REMOVED_EMPTY_RETRIEVAL_TEXT"
                policy_rows[-1]["approved_for_retrieval"] = False
                policy_rows[-1]["approved_for_display"] = False
        elif page_key not in repaired_page_keys:
            record = dict(original)
            record["quarantine_reason"] = mapping_status
            record["policy_source"] = source
            record["policy_action"] = action
            quarantine.append(record)
    return retained, quarantine, policy_rows, mappings


def encode_passages(texts: list[str], config: dict[str, Any]) -> np.ndarray:
    os.environ.setdefault("USE_TF", "0")
    os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    from sentence_transformers import SentenceTransformer

    model_config = config["model"]
    local_path = Path(model_config["local_path"]).expanduser().resolve()
    if not local_path.is_dir():
        raise FileNotFoundError(local_path)
    model = SentenceTransformer(str(local_path), device="cpu", local_files_only=True)
    if int(model.get_sentence_embedding_dimension()) != int(model_config["dimensions"]):
        raise AssertionError("Pinned E5 model dimension changed")
    embeddings = model.encode(
        [str(model_config["passage_prefix"]) + text for text in texts],
        batch_size=int(config["dense"]["batch_size_cpu"]),
        normalize_embeddings=bool(model_config["normalize_embeddings"]),
        convert_to_numpy=True,
        show_progress_bar=True,
    )
    embeddings = np.asarray(embeddings, dtype=np.float32)
    norms = np.linalg.norm(embeddings, axis=1)
    if embeddings.shape != (len(texts), int(model_config["dimensions"])):
        raise AssertionError("V2 embedding shape is invalid")
    if not np.isfinite(embeddings).all() or not np.allclose(norms, 1.0, atol=1e-4):
        raise AssertionError("V2 embeddings are not finite and L2-normalized")
    return embeddings


def artifact_record(path: Path, rows: int | None = None) -> dict[str, Any]:
    return {
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
        "rows": rows,
    }


def run(output_root: Path) -> dict[str, Any]:
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    v1_chunks_path = ROOT / "data" / "chunks.parquet"
    v1_references_path = ROOT / "data" / "reference_catalog.parquet"
    review_path = ROOT / "audit" / "corpus_quality" / "HUMAN_CHUNK_REVIEW_FINAL.xlsx"
    audit_path = ROOT / "audit" / "corpus_quality" / "CHUNK_QUALITY_AUDIT.csv"
    repaired_pages_path = output_root / "repaired_pages.parquet"
    repair_run_path = output_root / "PAGE_REPAIR_RUN_MANIFEST.json"
    if json.loads(repair_run_path.read_text(encoding="utf-8"))["status"] != "PASS":
        raise RuntimeError("Targeted page repair has not passed")

    v1_chunks = pd.read_parquet(v1_chunks_path).reset_index(drop=True)
    v1_references = pd.read_parquet(v1_references_path).reset_index(drop=True)
    repaired_pages = pd.read_parquet(repaired_pages_path)
    review_rows, formula_count = read_xlsx_sheet(review_path, "Review")
    if formula_count:
        raise AssertionError("Review workbook contains formula cells")
    review_by_chunk = {str(row["chunk_id"]): row for row in review_rows}
    audit_frame = pd.read_csv(audit_path, keep_default_na=False)
    audit_by_chunk = {str(row["chunk_id"]): row for row in audit_frame.to_dict(orient="records")}
    if set(v1_chunks["chunk_id"].astype(str)) != set(audit_by_chunk):
        raise AssertionError("Full corpus audit does not align exactly with v1 chunks")

    repaired_page_keys = {
        (str(row["source_document_id"]), int(row["source_page"]))
        for row in repaired_pages.to_dict(orient="records")
    }
    repaired_chunks, rejected_repairs, replacement_ids = build_repaired_chunks(repaired_pages, v1_chunks, config)
    retained, quarantine, policy_rows, mappings = build_policy(
        v1_chunks,
        repaired_page_keys,
        replacement_ids,
        review_by_chunk,
        audit_by_chunk,
    )
    for repaired in repaired_chunks:
        policy_rows.append(
            {
                "corpus_version": "v2",
                "chunk_id": repaired["chunk_id"],
                "approved_for_retrieval": True,
                "approved_for_display": True,
                "policy_source": "TARGETED_REPAIR_QUALITY_GATE",
                "policy_action": "REPAIRED_CHUNK",
                "automatic_classification": "REPAIRED",
                "automatic_reason": "CONTROLLED_OCR_AND_EVIDENCE_QUALITY_PASS",
                "human_classification": "",
                "human_follow_up_required": True,
            }
        )
        mappings.append(
            {
                "v1_chunk_id": "",
                "v2_chunk_ids": str(repaired["chunk_id"]),
                "mapping_status": "NEW_REPAIRED_CHUNK",
                "policy_source": "TARGETED_REPAIR_QUALITY_GATE",
                "policy_action": "REPAIRED_CHUNK",
                "document_id": str(repaired["document_id"]),
                "page_number_1_based": str(repaired["page_number_1_based"]),
            }
        )
    quarantine.extend(rejected_repairs)

    chunks_v2 = pd.DataFrame([*retained, *repaired_chunks])
    chunks_v2 = chunks_v2.sort_values(
        ["document_id", "page_number_1_based", "chunk_index_in_page", "chunk_id"], kind="stable"
    ).reset_index(drop=True)
    if chunks_v2.empty or not chunks_v2["chunk_id"].is_unique:
        raise AssertionError("V2 chunk IDs are empty or duplicated")
    if not chunks_v2["approved_for_retrieval"].all():
        raise AssertionError("V2 retrieval collection contains a disallowed chunk")

    linked_rows: set[int] = set()
    for raw in chunks_v2["reference_rows_json"]:
        linked_rows.update(int(value) for value in json.loads(str(raw)))
    references_v2 = v1_references.copy()
    references_v2["document_retrieval_eligible"] = references_v2.apply(
        lambda row: bool(row["document_retrieval_eligible"]) and int(row["row_number"]) in linked_rows,
        axis=1,
    )
    references_v2["evidence_available"] = references_v2.apply(
        lambda row: bool(row["evidence_available"]) and int(row["row_number"]) in linked_rows,
        axis=1,
    )

    output_root.mkdir(parents=True, exist_ok=True)
    index_root = output_root / "indexes"
    index_root.mkdir(parents=True, exist_ok=True)
    chunks_path = output_root / "chunks.parquet"
    references_path = output_root / "reference_catalog.parquet"
    policy_path = output_root / "chunk_policy.parquet"
    quarantine_path = output_root / "quarantined_chunks.parquet"
    provenance_path = output_root / "page_repair_provenance.parquet"
    mapping_path = output_root / "V1_TO_V2_CHUNK_MAP.csv"
    chunks_v2.to_parquet(chunks_path, index=False)
    references_v2.to_parquet(references_path, index=False)
    pd.DataFrame(policy_rows).to_parquet(policy_path, index=False)
    pd.DataFrame(quarantine).to_parquet(quarantine_path, index=False)
    provenance_columns = [
        "repair_id", "source_document_id", "source_document_hash", "source_file_name", "source_file_path_resolution",
        "source_page", "page_v1_chunk_ids", "reference_ids", "selected_extraction_method", "selected_ocr_confidence",
        "selected_text_sha256", "selected_display_text_sha256", "selected_diagnostics_json",
        "selected_display_diagnostics_json", "repair_status", "repair_attempt_count", "required_human_follow_up",
    ]
    repaired_pages[provenance_columns].to_parquet(provenance_path, index=False)
    mapping_frame = pd.DataFrame(mappings)
    mapping_frame.to_csv(mapping_path, index=False, encoding="utf-8-sig")
    old_mapping = mapping_frame[mapping_frame["v1_chunk_id"] != ""]
    if len(old_mapping) != len(v1_chunks) or not old_mapping["v1_chunk_id"].is_unique:
        raise AssertionError("Every v1 chunk must have exactly one mapping row")

    texts = chunks_v2["retrieval_text"].astype(str).tolist()
    bm25 = BM25Index.build(texts, k1=float(config["bm25"]["k1"]), b=float(config["bm25"]["b"]))
    bm25_path = index_root / "bm25_index.npz"
    vocabulary_path = index_root / "bm25_vocabulary.json"
    bm25.save(bm25_path, vocabulary_path)
    bm25.verify()
    embeddings = encode_passages(texts, config)
    embeddings_path = index_root / "embeddings.npy"
    np.save(embeddings_path, embeddings, allow_pickle=False)
    lookup = chunks_v2.copy()
    lookup.insert(0, "vector_row", np.arange(len(lookup), dtype=np.int64))
    lookup["retrieval_text_sha256"] = lookup["retrieval_text"].map(sha256_text)
    lookup_path = index_root / "chunk_lookup.parquet"
    lookup.to_parquet(lookup_path, index=False)
    if lookup["chunk_id"].astype(str).tolist() != chunks_v2["chunk_id"].astype(str).tolist():
        raise AssertionError("V2 chunk lookup ordering differs")
    if len(lookup) != bm25.document_count or len(lookup) != embeddings.shape[0]:
        raise AssertionError("V2 index rows do not align exactly")

    v2_config = json.loads(json.dumps(config))
    v2_config["data"] = {
        "chunks": "data/versions/v2/chunks.parquet",
        "reference_catalog": "data/versions/v2/reference_catalog.parquet",
        "bm25_index": "data/versions/v2/indexes/bm25_index.npz",
        "bm25_vocabulary": "data/versions/v2/indexes/bm25_vocabulary.json",
        "embeddings": "data/versions/v2/indexes/embeddings.npy",
        "chunk_lookup": "data/versions/v2/indexes/chunk_lookup.parquet",
        "manifest": "data/versions/v2/V2_MIGRATION_MANIFEST.json",
    }
    config_path = output_root / "config.v2.yaml"
    config_path.write_text(yaml.safe_dump(v2_config, allow_unicode=True, sort_keys=False), encoding="utf-8")

    runtime = {
        "schema_version": 1,
        "pipeline_version": PIPELINE_VERSION,
        "model_id": config["model"]["id"],
        "model_revision": config["model"]["revision"],
        "dimensions": int(config["model"]["dimensions"]),
        "query_prefix": config["model"]["query_prefix"],
        "passage_prefix": config["model"]["passage_prefix"],
        "normalize_embeddings": bool(config["model"]["normalize_embeddings"]),
        "bm25_k1": float(config["bm25"]["k1"]),
        "bm25_b": float(config["bm25"]["b"]),
        "hybrid_lexical_weight": float(config["hybrid"]["lexical_weight"]),
        "hybrid_dense_weight": float(config["hybrid"]["dense_weight"]),
        "abstention_unchanged_from_v1": True,
    }
    runtime_path = index_root / "retrieval_runtime.json"
    runtime_path.write_text(json.dumps(runtime, ensure_ascii=False, indent=2), encoding="utf-8")

    counts = {
        "v1_chunks": len(v1_chunks),
        "v2_retrieval_chunks": len(chunks_v2),
        "unchanged_v1_chunks_retained": len(retained),
        "new_repaired_chunks": len(repaired_chunks),
        "repaired_chunks_rejected": len(rejected_repairs),
        "quarantined_rows": len(quarantine),
        "v1_references": len(v1_references),
        "v2_retrieval_eligible_references": int(references_v2["document_retrieval_eligible"].sum()),
        "repair_pages": len(repaired_pages),
    }
    manifest = {
        "schema_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "pipeline_version": PIPELINE_VERSION,
        "status": "PASS",
        "inputs": {
            "v1_chunks": artifact_record(v1_chunks_path, len(v1_chunks)),
            "v1_reference_catalog": artifact_record(v1_references_path, len(v1_references)),
            "human_review_workbook": artifact_record(review_path, len(review_rows)),
            "full_corpus_audit": artifact_record(audit_path, len(audit_frame)),
            "repaired_pages": artifact_record(repaired_pages_path, len(repaired_pages)),
            "repair_run_manifest": artifact_record(repair_run_path),
            "v1_config_sha256": sha256_file(ROOT / "config.yaml"),
        },
        "counts": counts,
        "policy_counts": dict(sorted(Counter(row["mapping_status"] for row in mappings).items())),
        "artifacts": [],
        "model": runtime,
        "validation": {
            "v1_mapping_exact": True,
            "v2_chunk_ids_unique": True,
            "lookup_order_matches_chunks": True,
            "bm25_rows": bm25.document_count,
            "embedding_shape": list(embeddings.shape),
            "embedding_norm_min": float(np.linalg.norm(embeddings, axis=1).min()),
            "embedding_norm_max": float(np.linalg.norm(embeddings, axis=1).max()),
            "source_project_written": False,
            "v1_assets_written": False,
        },
        "reproduction_command": ".\\.venv\\Scripts\\python.exe scripts\\build_corpus_v2.py",
    }
    for path, rows in (
        (chunks_path, len(chunks_v2)),
        (references_path, len(references_v2)),
        (policy_path, len(policy_rows)),
        (quarantine_path, len(quarantine)),
        (provenance_path, len(repaired_pages)),
        (mapping_path, len(mapping_frame)),
        (bm25_path, bm25.document_count),
        (vocabulary_path, len(bm25.vocabulary)),
        (embeddings_path, len(embeddings)),
        (lookup_path, len(lookup)),
        (runtime_path, None),
        (config_path, None),
    ):
        manifest["artifacts"].append(artifact_record(path, rows))
    manifest_path = output_root / "V2_MIGRATION_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", **counts, "manifest": str(manifest_path)}, indent=2))
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Build immutable targeted-repair corpus and complete retrieval indexes v2.")
    parser.add_argument("--output-root", type=Path, default=V2_ROOT)
    args = parser.parse_args()
    run(args.output_root.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
