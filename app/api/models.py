from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from retrieval.schemas import SearchOutcome


class SearchFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    country: str | list[str] | None = None
    business_unit: str | list[str] | None = None
    client: str | list[str] | None = None
    sector: str | list[str] | None = None
    service_nature: str | list[str] | None = None
    offering: str | list[str] | None = None
    project_year: str | list[str] | None = None
    attestation_available: str | list[str] | None = None
    document_type: str | list[str] | None = None
    data_quality_status: str | list[str] | None = None
    year_before: int | None = Field(default=None, ge=1900, le=2100)
    year_after: int | None = Field(default=None, ge=1900, le=2100)


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    top_k: int = Field(default=3, ge=1)
    filters: SearchFilters | None = None
    debug: bool = False


class HealthResponse(BaseModel):
    status: str
    data_ready: bool
    model_available: bool
    service_loaded: bool
    reranker_enabled: bool


class ConfigSummaryResponse(BaseModel):
    model_id: str
    embedding_dimensions: int
    retrieval_mode: str
    maximum_results: int
    supported_languages: list[str]
    supported_filters: list[str]
    ocr_languages: str
    reranker_enabled: bool
    debug_enabled: bool


SearchResponse = SearchOutcome

