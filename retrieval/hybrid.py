from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .bm25 import BM25Index
from .dense import DenseIndex
from .terms import QueryTermAnalysis, analyze_query_terms


@dataclass(frozen=True)
class HybridScores:
    bm25: np.ndarray
    chunk_bm25: np.ndarray
    dense: np.ndarray
    fused: np.ndarray
    bm25_ranked: list[int]
    dense_ranked: list[int]
    fused_ranked: list[int]
    top_retriever_agreement: int
    query_terms: QueryTermAnalysis


def _stable_top(scores: np.ndarray, allowed_mask: np.ndarray, tie_ids: list[str], limit: int) -> list[int]:
    eligible = np.flatnonzero(allowed_mask & np.isfinite(scores))
    ordered = sorted(eligible.tolist(), key=lambda row: (-float(scores[row]), tie_ids[row]))
    return ordered[:limit]


class HybridRetriever:
    def __init__(self, bm25: BM25Index, dense: DenseIndex, tie_ids: list[str], config: dict):
        self.bm25 = bm25
        self.dense = dense
        self.tie_ids = tie_ids
        self.config = config
        count = len(tie_ids)
        if bm25.document_count != count or dense.embeddings.shape[0] != count:
            raise AssertionError("Retriever rows do not align")

    def score(
        self,
        query: str,
        allowed_mask: np.ndarray,
        *,
        query_terms: QueryTermAnalysis | None = None,
        lexical_scores: np.ndarray | None = None,
    ) -> HybridScores:
        settings = self.config["hybrid"]
        depth = int(settings["candidate_depth"])
        term_settings = self.config.get(
            "meaningful_terms",
            {
                "minimum_idf": 0.5,
                "maximum_document_frequency_ratio": 0.62,
                "exact_match_bonus_per_term": 0.04,
                "maximum_exact_match_bonus": 0.12,
            },
        )
        query_terms = query_terms or analyze_query_terms(query, self.bm25, term_settings)
        chunk_bm25_scores = self.bm25.score(
            query, allowed_mask, query_tokens=query_terms.bm25_tokens
        )
        if lexical_scores is None:
            bm25_scores = chunk_bm25_scores
        else:
            bm25_scores = np.asarray(lexical_scores, dtype=np.float32).copy()
            if bm25_scores.shape != allowed_mask.shape:
                raise ValueError("Field-aware lexical scores have the wrong shape")
            bm25_scores[~allowed_mask] = -np.inf
        dense_scores, _ = self.dense.score(query, allowed_mask)
        lexical = _stable_top(bm25_scores, allowed_mask, self.tie_ids, depth)
        semantic = _stable_top(dense_scores, allowed_mask, self.tie_ids, depth)
        fused = np.full(len(self.tie_ids), -np.inf, dtype=np.float32)
        for row in np.flatnonzero(allowed_mask):
            fused[row] = 0.0
        rrf_k = float(settings["rrf_k"])
        lexical_weight = float(settings["lexical_weight"])
        dense_weight = float(settings["dense_weight"])
        for rank, row in enumerate(lexical, start=1):
            fused[row] += lexical_weight / (rrf_k + rank)
        for rank, row in enumerate(semantic, start=1):
            fused[row] += dense_weight / (rrf_k + rank)
        fused_ranked = _stable_top(fused, allowed_mask, self.tie_ids, depth)
        agreement_depth = min(10, depth)
        agreement = len(set(lexical[:agreement_depth]) & set(semantic[:agreement_depth]))
        return HybridScores(
            bm25=bm25_scores, chunk_bm25=chunk_bm25_scores,
            dense=dense_scores, fused=fused,
            bm25_ranked=lexical, dense_ranked=semantic, fused_ranked=fused_ranked,
            top_retriever_agreement=agreement,
            query_terms=query_terms,
        )
