from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from .aggregation import aggregate_reference
from .evidence import derive_display_text
from .language import analyze_language
from .normalization import normalize_search_text
from .relevance import decide_relevance
from .service import RetrievalService


ROOT = Path(__file__).resolve().parents[1]


def _load_config() -> dict[str, Any]:
    configured = Path(
        os.getenv(
            "DEVOTEAM_CONFIG",
            "config/baselines/SELECTED_RETRIEVAL_CONFIGURATION.yaml",
        )
    ).expanduser()
    path = configured if configured.is_absolute() else ROOT / configured
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _reference_ids(service: RetrievalService, row: int) -> list[str]:
    chunk = service.chunks.iloc[row]
    try:
        reference_rows = [int(value) for value in json.loads(str(chunk["reference_rows_json"]))]
    except (TypeError, ValueError, json.JSONDecodeError):
        reference_rows = []
    return sorted(
        {
            reference_id
            for reference_row in reference_rows
            for reference_id in service.metadata.reference_ids_by_row.get(reference_row, [])
        }
    )


def _chunk_candidates(
    service: RetrievalService,
    rows: list[int],
    scores: np.ndarray,
    limit: int,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in rows[:limit]:
        chunk = service.chunks.iloc[row]
        output.append(
            {
                "chunk_id": str(chunk["chunk_id"]),
                "reference_ids": _reference_ids(service, row),
                "score": round(float(scores[row]), 8),
                "source_document": str(chunk["source_file_name"]),
                "source_page": int(chunk["page_number_1_based"]),
                "approved_for_retrieval": bool(chunk.get("approved_for_retrieval", True)),
                "approved_for_display": bool(chunk.get("approved_for_display", True)),
            }
        )
    return output


def diagnose(
    query: str,
    filters: dict[str, Any] | None = None,
    *,
    candidate_limit: int = 10,
    service: RetrievalService | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    config = service.config if service is not None else _load_config()
    service = service or RetrievalService(ROOT, config)
    language = analyze_language(query)
    eligible_ids, applied_filters, resolved_period = service.metadata.resolve_filters(filters)
    mask = service._mask_for_reference_ids(eligible_ids)
    outcome = service.search(
        query,
        filters=filters,
        page=1,
        page_size=service.safety_ceiling,
        debug=True,
    )
    if not mask.any():
        return {
            "diagnostic_version": "direct_retrieval_v2",
            "query": query,
            "normalized_query": normalize_search_text(query),
            "language": language.detected_language,
            "scripts": language.scripts,
            "active_filters": applied_filters,
            "resolved_period": resolved_period,
            "eligible_reference_count": len(eligible_ids),
            "bm25_chunk_candidates": [],
            "dense_chunk_candidates": [],
            "hybrid_chunk_candidates": [],
            "reference_aggregation": [],
            "final_returned_references": [],
            "abstention_reason": outcome.abstention_reason,
            "total_latency_ms": round((time.perf_counter() - started) * 1000, 2),
        }

    query_terms, field_scores, lexical_scores = service._field_lexical_scores(
        query, eligible_ids, mask
    )
    scores = service.hybrid.score(
        query,
        mask,
        query_terms=query_terms,
        lexical_scores=lexical_scores,
    )
    grouped = service._group_references(query, scores, eligible_ids)
    service._attach_reference_signals(grouped, field_scores)
    aggregation_rows: list[dict[str, Any]] = []
    for item in grouped[: max(candidate_limit * 3, candidate_limit)]:
        item["scores"] = scores
        service._select_evidence(item, language.detected_language)
        aggregation_settings = config["reference_aggregation"]
        aggregation = aggregate_reference(
            item["evidence"],
            strategy=aggregation_settings["strategy"],
            field_diagnostics=item.get("field_diagnostics"),
            support_bonus=float(aggregation_settings["support_bonus"]),
        )
        features = service._candidate_features(item, int(mask.sum()))
        decision = decide_relevance(query, features, config)
        aggregation_rows.append(
            {
                "reference_id": item["reference"].reference_id,
                "field_aware_bm25": item.get("field_diagnostics", {}),
                "aggregation_strategy": aggregation.strategy,
                "aggregation_explanation": aggregation.explanation,
                "best_evidence_chunk": aggregation.best_chunk_id,
                "second_supporting_chunk": aggregation.supporting_chunk_id,
                "selected_supporting_chunks": [
                    {
                        "chunk_id": str(evidence["chunk"]["chunk_id"]),
                        "source_document": str(evidence["chunk"]["source_file_name"]),
                        "source_page": int(evidence["chunk"]["page_number_1_based"]),
                        "display_text": str(evidence["display_text"]),
                        "evidence_quality": evidence["quality"].as_dict(),
                    }
                    for evidence in item["evidence"]
                ],
                "rejected_evidence": [
                    {
                        "chunk_id": str(evidence["chunk"]["chunk_id"]),
                        "reasons": evidence["quality"].rejection_reasons,
                    }
                    for evidence in item["evaluated_evidence"]
                    if not evidence["quality"].quality_pass
                ],
                "relevance_gate": {
                    "passed": decision.passed,
                    "patterns": decision.patterns,
                    "rejection_reason": None if decision.passed else decision.reason,
                },
            }
        )

    final_references = [
        {
            "reference_id": result.reference_id,
            "rank": result.rank,
            "project_title": result.project_title,
            "match_reasons": result.match_reasons,
            "selected_evidence_chunks": [
                {
                    "citation": passage.citation_label,
                    "source_document": passage.source_document,
                    "source_page": passage.source_page,
                    "display_text": passage.text,
                }
                for passage in result.supporting_passages
            ],
        }
        for result in outcome.results
    ]
    return {
        "diagnostic_version": "direct_retrieval_v2",
        "query": query,
        "normalized_query": query_terms.normalized_query,
        "language": language.detected_language,
        "scripts": language.scripts,
        "meaningful_query_terms": query_terms.diagnostics()["meaningful_terms"],
        "removed_stopwords": query_terms.removed_stopwords,
        "rejected_common_terms": query_terms.rejected_common_terms,
        "active_filters": applied_filters,
        "resolved_period": resolved_period,
        "eligible_reference_count": len(eligible_ids),
        "eligible_chunk_count": int(mask.sum()),
        "bm25_chunk_candidates": _chunk_candidates(
            service, scores.bm25_ranked, scores.bm25, candidate_limit
        ),
        "dense_chunk_candidates": _chunk_candidates(
            service, scores.dense_ranked, scores.dense, candidate_limit
        ),
        "hybrid_chunk_candidates": _chunk_candidates(
            service, scores.fused_ranked, scores.fused, candidate_limit
        ),
        "reference_aggregation": aggregation_rows[:candidate_limit],
        "final_returned_references": final_references,
        "rejected_candidate_count": sum(
            bool(candidate.get("abstained"))
            for candidate in (outcome.diagnostics or {}).get("candidate_gates", {}).values()
        ),
        "abstained": outcome.abstained,
        "abstention_reason": outcome.abstention_reason,
        "total_latency_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Explain a complete v2 retrieval run.")
    parser.add_argument("--query", required=True)
    parser.add_argument("--filters", help="Optional JSON hard-filter object.")
    parser.add_argument("--candidate-limit", type=int, default=10)
    parser.add_argument("--json", action="store_true", help="Emit the complete JSON trace.")
    args = parser.parse_args()
    filters = json.loads(args.filters) if args.filters else None
    payload = diagnose(args.query, filters, candidate_limit=max(1, args.candidate_limit))
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(
            f"{payload['abstention_reason']}: "
            f"{len(payload['final_returned_references'])} reference(s), "
            f"{payload['total_latency_ms']} ms"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
