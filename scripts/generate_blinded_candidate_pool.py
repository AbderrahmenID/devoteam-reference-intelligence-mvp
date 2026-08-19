from __future__ import annotations

import csv
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

from retrieval.dense import E5QueryEncoder
from retrieval.evidence import select_best_evidence
from retrieval.language import analyze_language
from retrieval.service import RetrievalService
from retrieval.terms import QueryTermAnalysis


ROOT = Path(__file__).resolve().parents[1]
FROZEN = ROOT / "evaluation" / "judging" / "frozen" / "development_queries_v1.csv"
PRIVATE = ROOT / "evaluation" / "judging" / "private"
PUBLIC_POOL = ROOT / "evaluation" / "judging" / "CANDIDATE_JUDGMENTS_BLINDED.csv"
UNBLINDED = PRIVATE / "CANDIDATE_POOL_UNBLINDED.csv"
CONTRIBUTIONS = PRIVATE / "CANDIDATE_POOL_SYSTEM_CONTRIBUTIONS.csv"
MANIFEST = PRIVATE / "CANDIDATE_POOL_MANIFEST.json"
SEED = "devoteam-development-v1-blind-20260802"
LANES = (
    "v1_bm25", "v1_dense", "v1_hybrid",
    "v2_bm25", "v2_dense", "v2_hybrid",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def empty_query_terms() -> QueryTermAnalysis:
    return QueryTermAnalysis("", [], [], [], [], [], [], [])


def reference_ids_for_row(service: RetrievalService, row_index: int, eligible_ids: set[str]) -> list[str]:
    chunk = service.chunks.iloc[row_index]
    try:
        reference_rows = [int(value) for value in json.loads(str(chunk["reference_rows_json"]))]
    except (TypeError, ValueError, json.JSONDecodeError):
        reference_rows = []
    return sorted(
        {
            reference_id
            for row in reference_rows
            for reference_id in service.metadata.reference_ids_by_row.get(row, [])
            if reference_id in eligible_ids
        }
    )


def rank_reference_lane(
    service: RetrievalService,
    ranked_rows: list[int],
    score_values: np.ndarray,
    eligible_ids: set[str],
    limit: int,
) -> dict[str, dict[str, Any]]:
    ranked: dict[str, dict[str, Any]] = {}
    for row_index in ranked_rows:
        for reference_id in reference_ids_for_row(service, row_index, eligible_ids):
            if reference_id in ranked:
                continue
            ranked[reference_id] = {
                "rank": len(ranked) + 1,
                "score": float(score_values[row_index]),
                "best_chunk_id": str(service.chunks.iloc[row_index]["chunk_id"]),
            }
            if len(ranked) >= limit:
                return ranked
    return ranked


def score_system(
    version: str,
    service: RetrievalService,
    query: str,
    filters: dict[str, Any],
) -> tuple[dict[str, dict[str, dict[str, Any]]], Any, set[str]]:
    eligible_ids, _, _ = service.metadata.resolve_filters(filters)
    mask = service._mask_for_reference_ids(eligible_ids)
    scores = service.hybrid.score(query, mask)
    lanes = {
        f"{version}_bm25": rank_reference_lane(service, scores.bm25_ranked, scores.bm25, eligible_ids, 10),
        f"{version}_dense": rank_reference_lane(service, scores.dense_ranked, scores.dense, eligible_ids, 10),
        f"{version}_hybrid": rank_reference_lane(service, scores.fused_ranked, scores.fused, eligible_ids, 20),
    }
    return lanes, scores, eligible_ids


def readable_evidence(
    version: str,
    service: RetrievalService,
    reference_id: str,
    scores: Any,
    query_language: str,
) -> list[dict[str, Any]]:
    reference = service.metadata.by_id.get(reference_id)
    if reference is None:
        return []
    candidates: list[dict[str, Any]] = []
    for row_index in reference.linked_chunk_indices:
        candidates.append(
            {
                "row": row_index,
                "chunk": service.chunks.iloc[row_index].to_dict(),
                "coverage": 0.0,
                "fused": float(scores.fused[row_index]),
                "bm25": float(scores.bm25[row_index]),
                "dense": float(scores.dense[row_index]),
            }
        )
    candidates.sort(
        key=lambda item: (
            -float(item["fused"]),
            -float(item["dense"]),
            -float(item["bm25"]),
            str(item["chunk"]["chunk_id"]),
        )
    )
    reference_text = " ".join(
        value
        for value in (reference.service_nature, reference.offering, reference.sector)
        if value
    )
    selection_settings = dict(service.config["evidence_quality"])
    selection_settings["maximum_passages_per_reference"] = 2
    selected, _ = select_best_evidence(
        candidates[: int(service.config["evidence_quality"]["candidate_pool_per_reference"])],
        empty_query_terms(),
        query_language,
        reference_text,
        service.evidence_evaluator,
        service.config["meaningful_terms"],
        selection_settings,
    )
    return [{**item, "source_version": version} for item in selected]


def pooled_priority(candidates: dict[str, dict[str, Any]]) -> list[str]:
    selected: list[str] = []
    for lane in LANES:
        lane_candidates = [
            reference_id
            for reference_id, item in candidates.items()
            if lane in item["lanes"]
        ]
        lane_candidates.sort(key=lambda reference_id: (candidates[reference_id]["lanes"][lane]["rank"], reference_id))
        if lane_candidates and lane_candidates[0] not in selected:
            selected.append(lane_candidates[0])
    remaining = [reference_id for reference_id in candidates if reference_id not in selected]
    remaining.sort(
        key=lambda reference_id: (
            min(value["rank"] for value in candidates[reference_id]["lanes"].values()),
            -len(candidates[reference_id]["lanes"]),
            min(
                (value["rank"] for lane, value in candidates[reference_id]["lanes"].items() if lane.endswith("hybrid")),
                default=999,
            ),
            reference_id,
        )
    )
    return (selected + remaining)[:25]


def run() -> dict[str, Any]:
    os.environ.setdefault("USE_TF", "0")
    os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    config_v1 = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    config_v2 = yaml.safe_load((ROOT / "data" / "versions" / "v2" / "config.v2.yaml").read_text(encoding="utf-8"))
    queries = pd.read_csv(FROZEN, keep_default_na=False, encoding="utf-8-sig")
    if len(queries) != 50 or not queries["query_id"].is_unique:
        raise AssertionError("Frozen query set is invalid")
    encoder = E5QueryEncoder(config_v1["model"], device="cpu")
    services = {
        "v1": RetrievalService(ROOT, config_v1, encoder=encoder),
        "v2": RetrievalService(ROOT, config_v2, encoder=encoder),
    }
    v2_allowed_reference_ids = set(services["v2"].metadata.all_ids)
    public_rows: list[dict[str, Any]] = []
    private_rows: list[dict[str, Any]] = []
    contribution_rows: list[dict[str, Any]] = []
    per_query_counts: dict[str, int] = {}
    excluded_no_evidence = 0
    excluded_quarantined = 0

    for query in queries.to_dict(orient="records"):
        query_id = query["query_id"]
        query_text = query["query_text"]
        query_language = query["language"]
        filters = json.loads(query["mandatory_filters_json"])
        all_lanes: dict[str, dict[str, dict[str, Any]]] = {}
        system_scores: dict[str, Any] = {}
        system_eligible: dict[str, set[str]] = {}
        for version, service in services.items():
            lanes, scores, eligible = score_system(version, service, query_text, filters)
            all_lanes.update(lanes)
            system_scores[version] = scores
            system_eligible[version] = eligible
        union_ids = set().union(*(set(lane) for lane in all_lanes.values()))
        candidates: dict[str, dict[str, Any]] = {}
        for reference_id in sorted(union_ids):
            if reference_id not in v2_allowed_reference_ids:
                excluded_quarantined += 1
                continue
            lanes = {
                lane_name: lane[reference_id]
                for lane_name, lane in all_lanes.items()
                if reference_id in lane
            }
            evidence: list[dict[str, Any]] = []
            for version in ("v2", "v1"):
                if reference_id in system_eligible[version]:
                    evidence.extend(
                        readable_evidence(
                            version,
                            services[version],
                            reference_id,
                            system_scores[version],
                            query_language,
                        )
                    )
            evidence.sort(
                key=lambda item: (
                    -float(item["selection_score"]),
                    -float(item["quality"].quality_score),
                    0 if item["source_version"] == "v2" else 1,
                    str(item["chunk"]["chunk_id"]),
                )
            )
            deduplicated_evidence: list[dict[str, Any]] = []
            seen_evidence: set[tuple[str, str]] = set()
            for item in evidence:
                key = (str(item["chunk"]["citation_uri"]), str(item["display_text"]))
                if key in seen_evidence:
                    continue
                seen_evidence.add(key)
                deduplicated_evidence.append(item)
                if len(deduplicated_evidence) == 2:
                    break
            if not deduplicated_evidence:
                excluded_no_evidence += 1
                continue
            reference = services["v2"].metadata.by_id[reference_id]
            candidates[reference_id] = {
                "reference": reference,
                "lanes": lanes,
                "evidence": deduplicated_evidence,
            }

        selected_ids = pooled_priority(candidates)
        random_order = sorted(
            selected_ids,
            key=lambda reference_id: hashlib.sha256(f"{SEED}|{query_id}|{reference_id}".encode("utf-8")).hexdigest(),
        )
        per_query_counts[query_id] = len(random_order)
        for blind_index, reference_id in enumerate(random_order, start=1):
            item = candidates[reference_id]
            reference = item["reference"]
            evidence = item["evidence"]
            blinded_candidate_id = f"{query_id}-C{blind_index:02d}"
            random_key = hashlib.sha256(f"{SEED}|{query_id}|{reference_id}".encode("utf-8")).hexdigest()
            first = evidence[0]
            second = evidence[1] if len(evidence) > 1 else None
            public_rows.append(
                {
                    "query_id": query_id,
                    "blinded_candidate_id": blinded_candidate_id,
                    "query_text": query_text,
                    "query_language": query_language,
                    "business_context": query["business_context"],
                    "mandatory_filters": query["mandatory_filters_json"],
                    "candidate_project_title": reference.project_title,
                    "client": reference.client,
                    "country": reference.country,
                    "period": reference.period,
                    "sector": reference.sector,
                    "offering": reference.offering,
                    "technologies": "; ".join(reference.technologies),
                    "evidence_passage_1": first["display_text"],
                    "evidence_source_1": first["chunk"]["source_file_name"],
                    "evidence_page_1": int(first["chunk"]["page_number_1_based"]),
                    "evidence_passage_2": second["display_text"] if second else "",
                    "evidence_source_2": second["chunk"]["source_file_name"] if second else "",
                    "evidence_page_2": int(second["chunk"]["page_number_1_based"]) if second else "",
                    "evidence_language": str(first["chunk"].get("page_language") or first["chunk"].get("document_language") or "und"),
                    "reviewer_1_relevance": "",
                    "reviewer_1_confidence": "",
                    "reviewer_1_notes": "",
                    "reviewer_2_relevance": "",
                    "reviewer_2_confidence": "",
                    "reviewer_2_notes": "",
                    "adjudicated_relevance": "",
                    "adjudicator_notes": "",
                }
            )
            lane_values = item["lanes"]
            private_rows.append(
                {
                    "query_id": query_id,
                    "blinded_candidate_id": blinded_candidate_id,
                    "reference_id": reference_id,
                    "v1_presence": any(lane.startswith("v1_") for lane in lane_values),
                    "v2_presence": any(lane.startswith("v2_") for lane in lane_values),
                    **{
                        f"{lane}_{field}": lane_values.get(lane, {}).get(field, "")
                        for lane in LANES
                        for field in ("rank", "score", "best_chunk_id")
                    },
                    "selected_evidence_chunk_ids": ";".join(str(value["chunk"]["chunk_id"]) for value in evidence),
                    "selected_evidence_source_versions": ";".join(str(value["source_version"]) for value in evidence),
                    "pool_inclusion_reason": "DETERMINISTIC_MULTI_SYSTEM_UNION_PRIORITY",
                    "filter_eligibility": True,
                    "deterministic_random_order_key": random_key,
                }
            )
            for lane, value in sorted(lane_values.items()):
                contribution_rows.append(
                    {
                        "query_id": query_id,
                        "blinded_candidate_id": blinded_candidate_id,
                        "reference_id": reference_id,
                        "corpus_version": lane[:2],
                        "retriever": lane.split("_", 1)[1],
                        "reference_rank": value["rank"],
                        "score": value["score"],
                        "best_chunk_id": value["best_chunk_id"],
                    }
                )

    public = pd.DataFrame(public_rows)
    unblinded = pd.DataFrame(private_rows)
    contributions = pd.DataFrame(contribution_rows)
    if public.duplicated(["query_id", "blinded_candidate_id"]).any():
        raise AssertionError("Blinded candidate IDs are duplicated")
    if unblinded.duplicated(["query_id", "reference_id"]).any():
        raise AssertionError("A reference is duplicated within a query")
    if len(public) != len(unblinded):
        raise AssertionError("Public and private candidate rows do not align")
    label_columns = [column for column in public.columns if "relevance" in column or column.endswith("_confidence") or column.endswith("_notes")]
    if any(public[column].astype(str).str.strip().ne("").any() for column in label_columns):
        raise AssertionError("Human judgment fields must remain blank")
    if any(count > 25 for count in per_query_counts.values()):
        raise AssertionError("Candidate cap exceeded")
    PUBLIC_POOL.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE.mkdir(parents=True, exist_ok=True)
    public.to_csv(PUBLIC_POOL, index=False, encoding="utf-8-sig", quoting=csv.QUOTE_ALL, lineterminator="\n")
    unblinded.to_csv(UNBLINDED, index=False, encoding="utf-8-sig", quoting=csv.QUOTE_ALL, lineterminator="\n")
    contributions.to_csv(CONTRIBUTIONS, index=False, encoding="utf-8-sig", quoting=csv.QUOTE_ALL, lineterminator="\n")
    manifest = {
        "schema_version": 1,
        "pool_version": "development_candidate_pool_v1",
        "status": "FROZEN_BLINDED_POOL_CSV_AND_PRIVATE_MAPPING",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "random_seed": SEED,
        "query_count": len(queries),
        "candidate_count": len(public),
        "per_query_candidate_counts": per_query_counts,
        "queries_with_zero_candidates": sorted(query_id for query_id, count in per_query_counts.items() if count == 0),
        "candidate_cap": 25,
        "pool_depths": {"bm25_per_version": 10, "dense_per_version": 10, "hybrid_per_version": 20},
        "abstention_used_for_pool_filtering": False,
        "mandatory_filters_enforced": True,
        "quarantined_references_excluded": True,
        "references_without_usable_evidence_excluded": True,
        "excluded_quarantined_occurrences": excluded_quarantined,
        "excluded_no_usable_evidence_occurrences": excluded_no_evidence,
        "human_judgment_fields_blank": True,
        "blinded_view_exposes_system_origin_or_scores": False,
        "inputs": {
            "frozen_queries": {"path": str(FROZEN.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256_file(FROZEN)},
            "v1_manifest": {"path": "data/DATA_MANIFEST.json", "sha256": sha256_file(ROOT / "data" / "DATA_MANIFEST.json")},
            "v2_manifest": {"path": "data/versions/v2/V2_MIGRATION_MANIFEST.json", "sha256": sha256_file(ROOT / "data" / "versions" / "v2" / "V2_MIGRATION_MANIFEST.json")},
        },
        "outputs": {
            "blinded_csv": {"path": str(PUBLIC_POOL.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256_file(PUBLIC_POOL), "rows": len(public)},
            "unblinded_mapping": {"path": str(UNBLINDED.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256_file(UNBLINDED), "rows": len(unblinded)},
            "system_contributions": {"path": str(CONTRIBUTIONS.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256_file(CONTRIBUTIONS), "rows": len(contributions)},
        },
        "contribution_counts": {
            f"{version}_{retriever}": int(len(group))
            for (version, retriever), group in contributions.groupby(["corpus_version", "retriever"])
        },
        "unresolved_issues": (
            ["DEV-041 has zero filter-eligible references under the owner-approved strict filter."]
            if per_query_counts.get("DEV-041") == 0
            else []
        ),
        "official_retrieval_metrics_exist": False,
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: manifest[key] for key in ("status", "query_count", "candidate_count", "queries_with_zero_candidates", "contribution_counts", "unresolved_issues")}, ensure_ascii=True, indent=2))
    return manifest


if __name__ == "__main__":
    run()
