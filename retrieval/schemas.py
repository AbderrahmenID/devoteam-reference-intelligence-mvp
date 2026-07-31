from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ScoreComponents(BaseModel):
    bm25_score: float
    dense_cosine: float
    hybrid_rrf: float
    query_term_coverage: float
    supporting_passages: int


class RetrievalResult(BaseModel):
    reference_id: str
    title: str
    client: str
    sector: str
    offering: str
    supporting_passage: str
    source_document: str
    source_page: int
    citation_label: str
    citation_uri: str
    evidence_language: str
    match_reasons: list[str]
    rank: int
    score_components: ScoreComponents


class SearchOutcome(BaseModel):
    query: str
    detected_language: str
    scripts: list[str]
    rtl: bool
    retrieval_mode: str = "hybrid"
    abstained: bool
    abstention_reason: str
    result_count: int
    latency_ms: float
    results: list[RetrievalResult]
    diagnostics: dict[str, Any] | None = Field(default=None)

