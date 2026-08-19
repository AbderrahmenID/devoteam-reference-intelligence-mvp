from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class ReferenceAggregation:
    strategy: str
    score: float
    best_chunk_id: str | None
    supporting_chunk_id: str | None
    explanation: str
    clean_chunk_count: int


def aggregate_reference(
    evidence: list[dict[str, Any]],
    *,
    strategy: str,
    field_diagnostics: dict[str, Any] | None = None,
    support_bonus: float = 0.0008,
) -> ReferenceAggregation:
    """Aggregate only clean, display-eligible evidence selected for a reference."""
    ordered = sorted(
        evidence,
        key=lambda item: (
            -float(item.get("fused", 0.0)),
            -float(item.get("selection_score", 0.0)),
            str(item["chunk"]["chunk_id"]),
        ),
    )
    values = [float(item.get("fused", 0.0)) for item in ordered]
    best = values[0] if values else 0.0
    second = values[1] if len(values) > 1 else None
    matched_fields = set((field_diagnostics or {}).get("matched_fields", []))
    strong_fields = matched_fields & {
        "title", "mission_name", "services_delivered", "description", "technologies"
    }
    evidence_agreement = "evidence" in matched_fields

    if strategy == "A_MAX":
        score = best
        explanation = "Best clean supporting passage."
    elif strategy == "B_TOP2_MEAN":
        score = float(np.mean(values[:2])) if values else 0.0
        explanation = "Mean support from the two strongest clean passages."
    elif strategy == "C_BEST_PLUS_SUPPORT":
        coherent_second = (
            len(ordered) > 1
            and (
                float(ordered[1].get("coverage", 0.0)) > 0.0
                or float(ordered[1].get("dense", -1.0)) >= 0.72
            )
        )
        score = best + (support_bonus if coherent_second else 0.0)
        explanation = (
            "Best clean passage with corroborating project evidence."
            if coherent_second
            else "One strong clean project passage."
        )
    elif strategy == "D_FIELD_AGREEMENT":
        agreement_count = len(strong_fields) + int(evidence_agreement)
        score = best + support_bonus * min(agreement_count, 3)
        explanation = (
            "Agreement across capability fields and clean evidence."
            if agreement_count >= 2
            else "Limited field agreement; ranking relies on the best clean passage."
        )
    else:
        raise ValueError(f"Unknown reference aggregation strategy: {strategy}")

    return ReferenceAggregation(
        strategy=strategy,
        score=float(score),
        best_chunk_id=str(ordered[0]["chunk"]["chunk_id"]) if ordered else None,
        supporting_chunk_id=(
            str(ordered[1]["chunk"]["chunk_id"]) if len(ordered) > 1 else None
        ),
        explanation=explanation,
        clean_chunk_count=len(ordered),
    )
