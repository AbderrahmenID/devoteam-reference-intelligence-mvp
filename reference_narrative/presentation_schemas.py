from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .schemas import EditableReferenceSectionNarrative, NarrativeGenerationRequest, REFERENCE_ID_RE


TemplateId = Literal["orange_bank_compact", "detailed_reference"]
SUPPORTED_TEMPLATE_IDS: tuple[TemplateId, ...] = (
    "orange_bank_compact",
    "detailed_reference",
)
TEMPLATE_DISPLAY_NAMES: dict[TemplateId, str] = {
    "orange_bank_compact": "Compact References - Orange Bank style",
    "detailed_reference": "Detailed Reference - Challenges / Réalisations / Bénéfices",
}
ApprovedNarrativeStatus = Literal["DRAFT", "NEEDS_REVIEW", "READY_FOR_PRESENTATION"]
OutputFormat = Literal["pptx", "pdf", "both"]


class DirectPresentationRequest(BaseModel):
    """Primary MVP contract: selected references directly to presentation."""

    model_config = ConfigDict(extra="forbid")

    selected_reference_ids: list[str] = Field(min_length=1, max_length=161)
    opportunity_context: str = Field(default="", max_length=4000)
    target_language: Literal["fr", "en", "ar"] = "fr"
    template_id: TemplateId = "orange_bank_compact"
    output_format: OutputFormat = "both"

    @field_validator("selected_reference_ids")
    @classmethod
    def validate_selected_reference_ids(cls, values: list[str]) -> list[str]:
        cleaned = [str(value).strip() for value in values]
        if any(not REFERENCE_ID_RE.fullmatch(value) for value in cleaned):
            raise ValueError("selected_reference_ids must contain stable reference IDs")
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("selected_reference_ids must be unique")
        return cleaned


class NarrativePresentationRequest(BaseModel):
    """Legacy reviewed-narrative contract retained outside the primary workflow."""

    model_config = ConfigDict(extra="forbid")

    generation_request: NarrativeGenerationRequest
    narrative: EditableReferenceSectionNarrative
    template_id: TemplateId = "detailed_reference"
    approved: bool = False
    approved_narrative_status: ApprovedNarrativeStatus = "DRAFT"
    approved_reference_ids: list[str] = Field(min_length=1, max_length=161)

    @field_validator("approved_reference_ids")
    @classmethod
    def validate_reference_ids(cls, values: list[str]) -> list[str]:
        cleaned = [str(value).strip() for value in values]
        if any(not REFERENCE_ID_RE.fullmatch(value) for value in cleaned):
            raise ValueError("approved_reference_ids must contain stable reference IDs")
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("approved_reference_ids must be unique")
        return cleaned


class NarrativePresentationResponse(BaseModel):
    generation_id: str
    status: Literal["completed"]
    template_id: TemplateId
    selected_reference_count: int
    slide_count: int
    pptx_download_url: str | None = None
    pdf_download_url: str | None = None
    manifest_download_url: str
    warnings: list[str] = Field(default_factory=list)
