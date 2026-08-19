from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ScoreComponents(BaseModel):
    bm25_score: float
    dense_cosine: float
    hybrid_rrf: float
    query_term_coverage: float
    supporting_passages: int


class EvidencePassage(BaseModel):
    text: str
    source_document: str
    source_page: int
    citation_label: str
    citation_uri: str
    language: str


class MatchReason(BaseModel):
    category: str
    values: list[str] = Field(default_factory=list)
    description: str


class RetrievalResult(BaseModel):
    reference_id: str
    reference_number: str | None = None
    display_title: str = ""
    project_title: str
    mission_name: str
    client: str
    contracting_authority: str
    country: str
    country_code: str | None = None
    country_label: str = ""
    project_start_year: int | None = None
    project_end_year: int | None = None
    project_ongoing: bool = False
    project_start_date: str | None = None
    completion_date: str | None = None
    period: str
    period_display: str = ""
    status: str | None = None
    sector: str
    offerings: list[str]
    service_nature: str
    technologies: list[str]
    key_themes: list[str]
    themes: list[str] = Field(default_factory=list)
    description: str
    services_delivered: list[str]
    supporting_passages: list[EvidencePassage]
    evidence_available: bool
    evidence_types: list[str]
    evidence_type: list[str] = Field(default_factory=list)
    document_languages: list[str]
    match_reasons: list[str]
    match_details: list[MatchReason] = Field(default_factory=list)
    rank: int
    relevance_rank: int
    score_components: ScoreComponents

    # Compatibility conveniences retained for existing API clients.
    title: str
    offering: str
    supporting_passage: str
    source_document: str
    source_page: int
    citation_label: str
    citation_uri: str
    source_uri: str = ""
    evidence_language: str


class SearchOutcome(BaseModel):
    query: str
    applied_filters: dict[str, Any] = Field(default_factory=dict)
    resolved_period: dict[str, int] | None = None
    resolved_time_interval: dict[str, int] | None = None
    detected_language: str
    scripts: list[str]
    rtl: bool
    retrieval_mode: str = "hybrid"
    abstained: bool
    abstention_reason: str
    total_count: int
    result_count: int
    page: int
    page_size: int
    total_pages: int
    sort: str
    latency_ms: float
    facets: dict[str, Any] | None = None
    results: list[RetrievalResult]
    diagnostics: dict[str, Any] | None = Field(default=None)
