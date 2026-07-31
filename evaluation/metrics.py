from __future__ import annotations

import math
from typing import Mapping, Sequence


def success_at(ranked: Sequence[str], relevant: set[str], k: int) -> float:
    return float(bool(set(ranked[:k]) & relevant))


def precision_at(ranked: Sequence[str], relevant: set[str], k: int) -> float:
    return len(set(ranked[:k]) & relevant) / k


def recall_at(ranked: Sequence[str], relevant: set[str], k: int) -> float:
    return len(set(ranked[:k]) & relevant) / len(relevant) if relevant else 0.0


def reciprocal_rank_at(ranked: Sequence[str], relevant: set[str], k: int) -> float:
    for rank, reference_id in enumerate(ranked[:k], start=1):
        if reference_id in relevant:
            return 1.0 / rank
    return 0.0


def ndcg_at(ranked: Sequence[str], graded_relevance: Mapping[str, float], k: int) -> float:
    gains = [float(graded_relevance.get(reference_id, 0.0)) for reference_id in ranked[:k]]
    dcg = sum((2**gain - 1) / math.log2(rank + 1) for rank, gain in enumerate(gains, start=1))
    ideal = sorted((float(value) for value in graded_relevance.values()), reverse=True)[:k]
    idcg = sum((2**gain - 1) / math.log2(rank + 1) for rank, gain in enumerate(ideal, start=1))
    return dcg / idcg if idcg else 0.0

