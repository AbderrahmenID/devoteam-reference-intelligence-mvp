from __future__ import annotations

import html
import re
import unicodedata
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


Language = Literal["fr", "en", "ar"]
OutputFormat = Literal["pptx", "pdf"]
GenerationStatus = Literal["completed", "completed_with_warnings", "failed"]

TAG_RE = re.compile(r"<[^>]*>")
SCRIPT_RE = re.compile(r"<(?:script|style)\b[^>]*>.*?</(?:script|style)>", re.IGNORECASE | re.DOTALL)
WHITESPACE_RE = re.compile(r"[ \t\f\v]+")


def sanitize_user_text(value: str) -> str:
    """Remove markup/control characters without damaging Unicode content."""
    decoded = html.unescape(str(value or ""))
    without_tags = TAG_RE.sub("", SCRIPT_RE.sub("", decoded))
    cleaned = "".join(
        character
        for character in without_tags
        if character in "\n\r" or not unicodedata.category(character).startswith("C")
    )
    cleaned = WHITESPACE_RE.sub(" ", cleaned)
    return "\n".join(line.strip() for line in cleaned.splitlines() if line.strip()).strip()


class ReferencePackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=180)
    client_name: str = Field(min_length=1, max_length=120)
    subtitle: str | None = Field(default=None, max_length=240)
    preparation_date: date = Field(default_factory=date.today)
    language: Language = "fr"
    reference_ids: list[str] = Field(min_length=1, max_length=161)
    include_summary: bool = True
    include_reference_details: bool = True
    include_evidence_annex: bool = True
    include_logos: bool = True
    output_formats: list[OutputFormat] = Field(default_factory=lambda: ["pptx", "pdf"])

    @field_validator("title", "client_name", "subtitle", mode="before")
    @classmethod
    def sanitize_metadata(cls, value: Any) -> Any:
        if value is None:
            return None
        return sanitize_user_text(str(value))

    @field_validator("reference_ids")
    @classmethod
    def validate_reference_ids(cls, values: list[str]) -> list[str]:
        cleaned = [str(value).strip() for value in values]
        if any(not re.fullmatch(r"[0-9a-f]{64}", value) for value in cleaned):
            raise ValueError("reference_ids must contain stable 64-character lowercase hexadecimal IDs")
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("reference_ids must be unique")
        return cleaned

    @field_validator("output_formats")
    @classmethod
    def validate_output_formats(cls, values: list[OutputFormat]) -> list[OutputFormat]:
        if not values:
            raise ValueError("at least one output format is required")
        return list(dict.fromkeys(values))

    @model_validator(mode="after")
    def validate_sections(self) -> "ReferencePackRequest":
        if not (self.include_summary or self.include_reference_details or self.include_evidence_annex):
            raise ValueError("at least one reference content section must be enabled")
        return self


class TrustedEvidence(BaseModel):
    chunk_id: str
    document_id: str
    source_file_name: str
    source_sha256: str
    source_page: int
    citation_label: str
    citation_uri: str
    language: str
    display_text: str
    source_relative_path: str = ""


class TrustedReference(BaseModel):
    reference_id: str
    reference_number: str | None = None
    row_number: int
    mission_title: str
    client: str
    country: str
    period: str
    sector: str
    offering: str
    business_unit: str
    description: str
    services_delivered: list[str]
    technologies: list[str]
    capabilities: list[str]
    evidence: list[TrustedEvidence]


class BulletSource(BaseModel):
    text: str
    source_fields: list[str]
    evidence_chunk_ids: list[str] = Field(default_factory=list)


class PreparedReference(BaseModel):
    reference: TrustedReference
    summary_bullets: list[BulletSource]
    description_items: list[BulletSource]
    service_items: list[BulletSource]
    why_selected: list[BulletSource]
    evidence_items: list[TrustedEvidence]


class SlideProvenance(BaseModel):
    slide_number: int
    slide_type: str
    reference_ids: list[str] = Field(default_factory=list)
    bullet_sources: list[BulletSource] = Field(default_factory=list)
    evidence_chunk_ids: list[str] = Field(default_factory=list)
    evidence_visuals: list[dict[str, Any]] = Field(default_factory=list)


class ReferencePackResponse(BaseModel):
    generation_id: str
    status: GenerationStatus
    selected_reference_count: int
    slide_count: int
    pptx_download_url: str | None = None
    pdf_download_url: str | None = None
    manifest_download_url: str
    warnings: list[str] = Field(default_factory=list)


class GenerationArtifacts(BaseModel):
    response: ReferencePackResponse
    directory: str
    manifest: dict[str, Any]
