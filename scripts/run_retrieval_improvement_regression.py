from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from retrieval.normalization import normalize_search_text  # noqa: E402
from retrieval.service import RetrievalService  # noqa: E402


WEIGHT_SWEEP = (
    ("LEX90_DENSE10", 0.90, 0.10),
    ("LEX80_DENSE20", 0.80, 0.20),
    ("LEX75_DENSE25", 0.75, 0.25),
    ("LEX70_DENSE30", 0.70, 0.30),
    ("LEX60_DENSE40", 0.60, 0.40),
)
BROKEN_QUERY = {
    "query_id": "BROKEN-REAL-001",
    "query_text": "Références PCA pour une banque",
    "language": "fr",
    "mandatory_filters_json": "{}",
    "query_type": "known_broken_regression",
    "answerability": "answerable",
}


def _technical_issues(
    service: RetrievalService,
    outcome: Any,
    filters: dict[str, Any] | None,
    answerability: str,
    language: str,
) -> list[str]:
    issues: list[str] = []
    ids = [result.reference_id for result in outcome.results]
    if len(ids) != len(set(ids)):
        issues.append("DUPLICATE_REFERENCE")
    eligible_ids, _, _ = service.metadata.resolve_filters(filters)
    if not set(ids) <= eligible_ids:
        issues.append("HARD_FILTER_VIOLATION")
    if any(
        not result.supporting_passages
        or any(
            not passage.source_document or passage.source_page <= 0 or not passage.citation_uri
            for passage in result.supporting_passages
        )
        for result in outcome.results
    ):
        issues.append("MISSING_CITATION")
    forbidden_reason_tokens = {"pour", "une", "avec", "the", "for", "with", "من", "في"}
    reason_values = {
        normalize_search_text(value)
        for result in outcome.results
        for detail in result.match_details
        for value in detail.values
    }
    if reason_values & forbidden_reason_tokens:
        issues.append("STOPWORD_EXPLANATION")
    displayed = " ".join(
        passage.text
        for result in outcome.results
        for passage in result.supporting_passages
    )
    normalized_display = normalize_search_text(displayed)
    legal_markers = (
        "article 8 confidentialite",
        "dommages et interets",
        "servir et valoir ce que de droit",
        "conditions generales",
    )
    if any(marker in normalized_display for marker in legal_markers):
        issues.append("GENERIC_LEGAL_EVIDENCE")
    if any(marker in displayed for marker in ("ï¿½", "�", "Ø§", "Ù„")):
        issues.append("CORRUPTED_OR_MOJIBAKE_EVIDENCE")
    gates = (outcome.diagnostics or {}).get("candidate_gates", {})
    chunk_by_id = service.chunks.set_index(service.chunks.chunk_id.astype(str))
    selected_chunk_ids = {
        chunk_id
        for reference_id in ids
        for chunk_id in (
            gates.get(reference_id, {}).get("aggregation", {}).get("best_chunk_id"),
            gates.get(reference_id, {}).get("aggregation", {}).get("supporting_chunk_id"),
        )
        if chunk_id
    }
    if any(
        chunk_id not in chunk_by_id.index
        or not bool(chunk_by_id.loc[chunk_id].get("approved_for_display", True))
        for chunk_id in selected_chunk_ids
    ):
        issues.append("DISPLAY_PROHIBITED_CHUNK")
    if answerability == "no_answer" and not outcome.abstained:
        issues.append("UNSUPPORTED_QUERY_DID_NOT_ABSTAIN")
    if language in {"ar", "mixed"} and any(
        not passage.text.strip()
        for result in outcome.results
        for passage in result.supporting_passages
    ):
        issues.append("ARABIC_OR_MIXED_RENDERING_FAILURE")
    if float(outcome.latency_ms) > 5000:
        issues.append("EXCESSIVE_LATENCY")
    return sorted(set(issues))


def main() -> int:
    config = yaml.safe_load(
        (ROOT / "config/baselines/SELECTED_RETRIEVAL_CONFIGURATION.yaml").read_text(
            encoding="utf-8"
        )
    )
    service = RetrievalService(ROOT, config)
    query_frame = pd.read_csv(ROOT / "evaluation/judging/frozen/development_queries_v1.csv")
    queries = [*query_frame.to_dict(orient="records"), BROKEN_QUERY]
    rows: list[dict[str, Any]] = []

    for config_id, lexical_weight, dense_weight in WEIGHT_SWEEP:
        service.config["hybrid"]["lexical_weight"] = lexical_weight
        service.config["hybrid"]["dense_weight"] = dense_weight
        for query in queries:
            filters = json.loads(str(query.get("mandatory_filters_json") or "{}")) or None
            outcome = service.search(
                str(query["query_text"]),
                filters=filters,
                page=1,
                page_size=service.safety_ceiling,
                debug=True,
            )
            gates = (outcome.diagnostics or {}).get("candidate_gates", {})
            returned_ids = [result.reference_id for result in outcome.results]
            rejected = [gate for gate in gates.values() if gate.get("abstained")]
            rejection_categories = Counter(str(gate.get("reason")) for gate in rejected)
            selected_chunks = {
                reference_id: [
                    chunk_id
                    for chunk_id in (
                        gates.get(reference_id, {}).get("aggregation", {}).get("best_chunk_id"),
                        gates.get(reference_id, {}).get("aggregation", {}).get("supporting_chunk_id"),
                    )
                    if chunk_id
                ]
                for reference_id in returned_ids
            }
            reasons = {
                result.reference_id: result.match_reasons for result in outcome.results
            }
            issues = _technical_issues(
                service,
                outcome,
                filters,
                str(query.get("answerability") or ""),
                str(query.get("language") or ""),
            )
            rows.append(
                {
                    "configuration_id": config_id,
                    "lexical_weight": lexical_weight,
                    "dense_weight": dense_weight,
                    "aggregation_strategy": service.config["reference_aggregation"]["strategy"],
                    "query_id": query["query_id"],
                    "query_text": query["query_text"],
                    "language": query.get("language"),
                    "query_type": query.get("query_type"),
                    "mandatory_filters_json": json.dumps(filters or {}, ensure_ascii=False, sort_keys=True),
                    "returned_reference_ids_json": json.dumps(returned_ids),
                    "result_count": outcome.total_count,
                    "selected_evidence_chunks_json": json.dumps(selected_chunks, sort_keys=True),
                    "meaningful_match_reasons_json": json.dumps(reasons, ensure_ascii=False, sort_keys=True),
                    "rejected_candidate_count": len(rejected),
                    "rejection_categories_json": json.dumps(rejection_categories, sort_keys=True),
                    "abstained": outcome.abstained,
                    "abstention_decision": outcome.abstention_reason,
                    "latency_ms": outcome.latency_ms,
                    "technical_issues_json": json.dumps(issues),
                }
            )
    output = ROOT / "evaluation/results/RETRIEVAL_IMPROVEMENT_REGRESSION.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(output, index=False, encoding="utf-8")
    print(f"Wrote {len(rows)} rows to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
