from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from retrieval.metadata import ReferenceMetadataIndex


ROOT = Path(__file__).resolve().parents[1]
JUDGING = ROOT / "evaluation" / "judging"
PRIVATE = JUDGING / "private"
PUBLIC_PATH = JUDGING / "CANDIDATE_JUDGMENTS_BLINDED.csv"
UNBLINDED_PATH = PRIVATE / "CANDIDATE_POOL_UNBLINDED.csv"
CONTRIBUTIONS_PATH = PRIVATE / "CANDIDATE_POOL_SYSTEM_CONTRIBUTIONS.csv"
MANIFEST_PATH = PRIVATE / "CANDIDATE_POOL_MANIFEST.json"
FROZEN_PATH = JUDGING / "frozen" / "development_queries_v1.csv"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run() -> dict:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    public = pd.read_csv(PUBLIC_PATH, keep_default_na=False, encoding="utf-8-sig")
    unblinded = pd.read_csv(UNBLINDED_PATH, keep_default_na=False, encoding="utf-8-sig")
    contributions = pd.read_csv(CONTRIBUTIONS_PATH, keep_default_na=False, encoding="utf-8-sig")
    frozen = pd.read_csv(FROZEN_PATH, keep_default_na=False, encoding="utf-8-sig")
    issues: list[str] = []

    if len(frozen) != 50 or not frozen["query_id"].is_unique:
        issues.append("Frozen queries are not exactly 50 unique rows")
    if len(public) != len(unblinded) or len(public) != int(manifest["candidate_count"]):
        issues.append("Public/private/manifest candidate counts differ")
    if public.duplicated(["query_id", "blinded_candidate_id"]).any():
        issues.append("Public blinded candidate IDs are duplicated")
    if unblinded.duplicated(["query_id", "reference_id"]).any():
        issues.append("Private reference IDs are duplicated within a query")
    public_ids = set(zip(public["query_id"], public["blinded_candidate_id"]))
    private_ids = set(zip(unblinded["query_id"], unblinded["blinded_candidate_id"]))
    if public_ids != private_ids:
        issues.append("Public and private blinded identities do not reconcile")
    if set(public["query_id"]) - set(frozen["query_id"]):
        issues.append("Pool contains an unknown query ID")
    if public.groupby("query_id").size().max() > 25:
        issues.append("A query exceeds the 25-candidate cap")

    hidden_fragments = ("reference_id", "v1", "v2", "bm25", "dense", "hybrid", "rank", "score", "abstention")
    leaked_columns = [column for column in public.columns if any(fragment in column.casefold() for fragment in hidden_fragments)]
    if leaked_columns:
        issues.append(f"Blinded CSV leaks private system columns: {leaked_columns}")
    judgment_columns = [
        "reviewer_1_relevance", "reviewer_1_confidence", "reviewer_1_notes",
        "reviewer_2_relevance", "reviewer_2_confidence", "reviewer_2_notes",
        "adjudicated_relevance", "adjudicator_notes",
    ]
    prefilled = [column for column in judgment_columns if public[column].astype(str).str.strip().ne("").any()]
    if prefilled:
        issues.append(f"Judgment fields are prefilled: {prefilled}")
    required_evidence = ["evidence_passage_1", "evidence_source_1", "evidence_page_1", "evidence_language"]
    missing_evidence_rows = public[required_evidence].astype(str).apply(lambda column: column.str.strip().eq("")).any(axis=1)
    if missing_evidence_rows.any():
        issues.append(f"Candidates missing primary evidence lineage: {int(missing_evidence_rows.sum())}")

    merged = public[["query_id", "blinded_candidate_id"]].merge(
        unblinded[["query_id", "blinded_candidate_id", "reference_id", "deterministic_random_order_key"]],
        on=["query_id", "blinded_candidate_id"],
        how="outer",
        validate="one_to_one",
    )
    seed = manifest["random_seed"]
    for query_id, group in merged.groupby("query_id"):
        expected = sorted(
            group["reference_id"],
            key=lambda reference_id: hashlib.sha256(f"{seed}|{query_id}|{reference_id}".encode("utf-8")).hexdigest(),
        )
        actual = group.sort_values("blinded_candidate_id")["reference_id"].tolist()
        if actual != expected:
            issues.append(f"Deterministic blinding order mismatch for {query_id}")
        for row in group.to_dict(orient="records"):
            key = hashlib.sha256(f"{seed}|{query_id}|{row['reference_id']}".encode("utf-8")).hexdigest()
            if row["deterministic_random_order_key"] != key:
                issues.append(f"Random key mismatch for {query_id}/{row['reference_id']}")

    v2_chunks = pd.read_parquet(ROOT / "data" / "versions" / "v2" / "chunks.parquet")
    v1_chunks = pd.read_parquet(ROOT / "data" / "chunks.parquet")
    v2_references = pd.read_parquet(ROOT / "data" / "versions" / "v2" / "reference_catalog.parquet")
    metadata = ReferenceMetadataIndex(v2_references, v2_chunks)
    query_by_id = frozen.set_index("query_id")
    for query_id, group in unblinded.groupby("query_id"):
        eligible, _, _ = metadata.resolve_filters(json.loads(query_by_id.loc[query_id, "mandatory_filters_json"]))
        invalid = set(group["reference_id"]) - eligible
        if invalid:
            issues.append(f"Hard-filter violations for {query_id}: {sorted(invalid)}")
    zero_queries = sorted(set(frozen["query_id"]) - set(public["query_id"]))
    if zero_queries != sorted(manifest["queries_with_zero_candidates"]):
        issues.append("Zero-candidate queries do not match the manifest")
    if zero_queries != ["DEV-041"]:
        issues.append(f"Unexpected zero-candidate query set: {zero_queries}")

    v1_ids = set(v1_chunks["chunk_id"].astype(str))
    v2_ids = set(v2_chunks["chunk_id"].astype(str))
    v2_display = v2_chunks.set_index(v2_chunks["chunk_id"].astype(str))["approved_for_display"].to_dict()
    unknown_evidence: list[str] = []
    prohibited_display: list[str] = []
    for value in unblinded["selected_evidence_chunk_ids"]:
        for chunk_id in str(value).split(";"):
            if chunk_id not in v1_ids and chunk_id not in v2_ids:
                unknown_evidence.append(chunk_id)
            if chunk_id in v2_display and not bool(v2_display[chunk_id]):
                prohibited_display.append(chunk_id)
    if unknown_evidence:
        issues.append(f"Unknown selected evidence chunk IDs: {len(unknown_evidence)}")
    if prohibited_display:
        issues.append(f"Retrieval-only v2 chunks selected for display: {len(prohibited_display)}")

    contribution_ids = set(zip(contributions["query_id"], contributions["blinded_candidate_id"]))
    if not contribution_ids <= public_ids:
        issues.append("System contribution rows contain unknown candidates")
    expected_hashes = {
        "blinded_csv": sha256_file(PUBLIC_PATH),
        "unblinded_mapping": sha256_file(UNBLINDED_PATH),
        "system_contributions": sha256_file(CONTRIBUTIONS_PATH),
    }
    for key, actual in expected_hashes.items():
        if manifest["outputs"][key]["sha256"] != actual:
            issues.append(f"Manifest hash mismatch: {key}")

    result = {
        "schema_version": 1,
        "validated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if not issues else "FAIL",
        "query_count": len(frozen),
        "candidate_count": len(public),
        "zero_candidate_queries": zero_queries,
        "maximum_candidates_per_query": int(public.groupby("query_id").size().max()),
        "judgment_fields_blank": not prefilled,
        "public_private_identity_match": public_ids == private_ids,
        "evidence_lineage_complete": not missing_evidence_rows.any() and not unknown_evidence,
        "retrieval_only_evidence_displayed": bool(prohibited_display),
        "mandatory_filter_violations": sum(issue.startswith("Hard-filter violations") for issue in issues),
        "manifest_hashes_match": not any(issue.startswith("Manifest hash mismatch") for issue in issues),
        "issues": issues,
    }
    output = PRIVATE / "CANDIDATE_POOL_VALIDATION.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=True, indent=2))
    if issues:
        raise AssertionError("Candidate pool validation failed")
    return result


if __name__ == "__main__":
    run()
