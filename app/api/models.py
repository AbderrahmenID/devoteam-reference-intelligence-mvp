from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from retrieval.schemas import SearchOutcome


FilterValue = str | list[str] | None


class PeriodFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_year: int | None = Field(default=None, ge=1900, le=2100)
    end_year: int | None = Field(default=None, ge=1900, le=2100)
    preset: Literal["last_3_years", "last_5_years", "last_10_years"] | None = None

    @model_validator(mode="after")
    def validate_interval(self) -> "PeriodFilter":
        if self.preset and (self.start_year is not None or self.end_year is not None):
            raise ValueError("period preset cannot be combined with explicit years")
        if self.start_year and self.end_year and self.start_year > self.end_year:
            raise ValueError("period start_year cannot exceed end_year")
        return self


class SearchFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period: PeriodFilter | None = None
    country: FilterValue = None
    sector: FilterValue = None
    client: FilterValue = None
    offering: FilterValue = None
    service_nature: FilterValue = None
    technology: FilterValue = None
    status: FilterValue = None
    evidence_available: FilterValue = None
    evidence_type: FilterValue = None
    language: FilterValue = None
    themes: FilterValue = None
    business_unit: FilterValue = None
    data_quality_status: FilterValue = None

    # Legacy names mapped onto evidence_type by the normalized metadata layer.
    attestation_available: FilterValue = None
    document_type: FilterValue = None

    # Backward-compatible time fields; all use interval-overlap semantics.
    project_year: str | list[str] | None = None
    year_before: int | None = Field(default=None, ge=1900, le=2100)
    year_after: int | None = Field(default=None, ge=1900, le=2100)


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    filters: SearchFilters | None = None
    page: int = Field(default=1, ge=1)
    page_size: Literal[10, 20, 50] = 20
    sort: Literal["relevance", "newest", "oldest", "project_title", "client", "country"] = "relevance"
    debug: bool = False
    include_facets: bool = False


class ExportOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    include_summary_table: bool = True
    include_detailed_annex: bool = True
    include_evidence_passages: bool = True
    include_scores: bool = False
    missing_value_policy: Literal["blank", "not_available"] = "blank"

    @model_validator(mode="after")
    def require_content(self) -> "ExportOptions":
        if not self.include_summary_table and not self.include_detailed_annex:
            raise ValueError("at least one export section must be enabled")
        return self


class ExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    filters: SearchFilters | None = None
    selected_reference_ids: list[str] = Field(default_factory=list)
    export_all_filtered: bool = False
    sort: Literal["relevance", "newest", "oldest", "project_title", "client", "country"] = "relevance"
    options: ExportOptions = Field(default_factory=ExportOptions)

    @model_validator(mode="after")
    def validate_selection_mode(self) -> "ExportRequest":
        if self.export_all_filtered and self.selected_reference_ids:
            raise ValueError("choose selected_reference_ids or export_all_filtered, not both")
        if not self.export_all_filtered and not self.selected_reference_ids:
            raise ValueError("selected_reference_ids are required unless export_all_filtered is true")
        if len(self.selected_reference_ids) != len(set(self.selected_reference_ids)):
            raise ValueError("selected_reference_ids must be unique")
        return self


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
    default_page_size: int
    page_sizes: list[int]
    supported_sorts: list[str]
    supported_languages: list[str]
    supported_filters: list[str]
    ocr_languages: str
    reranker_enabled: bool
    debug_enabled: bool


SearchResponse = SearchOutcome
