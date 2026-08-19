from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


REFERENCE_ID_RE = re.compile(r"[0-9a-f]{64}")

TargetLanguage = Literal["fr", "en", "ar"]
Tone = Literal["commercial", "executive", "technical", "concise"]
Audience = Literal["executive", "technical", "procurement", "mixed"]
DetailLevel = Literal["short", "medium", "detailed"]


class SourceType(str, Enum):
    FACT = "FACT"
    COMPLETED_WORK_EVIDENCE = "COMPLETED_WORK_EVIDENCE"
    STRUCTURED_METADATA = "STRUCTURED_METADATA"
    PROPOSAL_SCOPE = "PROPOSAL_SCOPE"
    CLIENT_ATTESTATION = "CLIENT_ATTESTATION"
    CONTRACTUAL_SCOPE = "CONTRACTUAL_SCOPE"
    UNVERIFIED_METADATA = "UNVERIFIED_METADATA"


class ValidationSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    BLOCKING = "BLOCKING"


class NarrativeGenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_reference_ids: list[str] = Field(min_length=1, max_length=161)
    opportunity_title: str = Field(min_length=1, max_length=180)
    opportunity_description: str = Field(default="", max_length=4000)
    requirements: list[str] = Field(default_factory=list, max_length=50)
    target_language: TargetLanguage = "fr"
    tone: Tone = "commercial"
    audience: Audience = "mixed"
    detail_level: DetailLevel = "medium"

    @field_validator("selected_reference_ids")
    @classmethod
    def validate_reference_ids(cls, values: list[str]) -> list[str]:
        cleaned = [str(value).strip() for value in values]
        if any(not REFERENCE_ID_RE.fullmatch(value) for value in cleaned):
            raise ValueError("selected_reference_ids must contain stable 64-character lowercase hexadecimal IDs")
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("selected_reference_ids must be unique")
        return cleaned

    @field_validator("requirements")
    @classmethod
    def validate_requirements(cls, values: list[str]) -> list[str]:
        if any(len(str(value)) > 500 for value in values):
            raise ValueError("each requirement must be at most 500 characters")
        return values


class SupportedFact(BaseModel):
    field: str
    value: str
    support_id: str


class ReferenceFacts(BaseModel):
    reference_id: str
    reference_number: SupportedFact | None = None
    mission_title: SupportedFact | None = None
    client: SupportedFact | None = None
    country: SupportedFact | None = None
    period: SupportedFact | None = None
    sector: SupportedFact | None = None
    offering: SupportedFact | None = None
    business_unit: SupportedFact | None = None
    technologies: list[SupportedFact] = Field(default_factory=list)


class SourceSupportRecord(BaseModel):
    support_id: str
    reference_id: str
    support_types: list[SourceType]
    text: str
    source_label: str
    page: int | None = None


class ReferenceSourceBundle(BaseModel):
    reference_id: str
    facts: ReferenceFacts
    completed_work_evidence: list[SourceSupportRecord] = Field(default_factory=list)
    structured_metadata_scope: list[SourceSupportRecord] = Field(default_factory=list)
    proposal_scope: list[SourceSupportRecord] = Field(default_factory=list)
    display_evidence: list[SourceSupportRecord] = Field(default_factory=list)
    unavailable_fields: list[str] = Field(default_factory=list)


class ReferenceNarrativeDraft(BaseModel):
    """Prose-only model contract for one backend-selected reference."""

    model_config = ConfigDict(extra="forbid")

    headline: str = ""
    short_description: str = ""
    challenge: str = ""
    devoteam_contribution: str = ""
    realisations: list[str] = Field(default_factory=list)
    benefits: list[str] = Field(default_factory=list)
    why_relevant_to_opportunity: str = ""


class SectionNarrativeDraft(BaseModel):
    """Prose-only model contract for selected-reference section synthesis."""

    model_config = ConfigDict(extra="forbid")

    section_intro: str = ""
    overall_storyline: str = ""
    why_these_references: str = ""


class FieldSupportPlan(BaseModel):
    reference_id: str
    headline: list[str] = Field(default_factory=list)
    short_description: list[str] = Field(default_factory=list)
    challenge: list[str] = Field(default_factory=list)
    devoteam_contribution: list[str] = Field(default_factory=list)
    realisations: list[str] = Field(default_factory=list)
    benefits: list[str] = Field(default_factory=list)
    why_relevant_to_opportunity: list[str] = Field(default_factory=list)


class SectionSupportPlan(BaseModel):
    section_intro: list[str] = Field(default_factory=list)
    overall_storyline: list[str] = Field(default_factory=list)
    why_these_references: list[str] = Field(default_factory=list)


class NarrativeSupportPlan(BaseModel):
    references: list[FieldSupportPlan]
    section: SectionSupportPlan


class SafeReferenceCapsule(BaseModel):
    reference_id: str
    client: str = ""
    sector: str = ""
    country: str = ""
    period: str = ""
    offering: str = ""
    grounded_capabilities: list[str] = Field(default_factory=list)
    support_ids: list[str] = Field(default_factory=list)


class SupportedNarrativeText(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    support_ids: list[str] = Field(default_factory=list)


class SupportedDetailedRealisation(BaseModel):
    """One editable first-level delivery with optional editable child activities."""

    model_config = ConfigDict(extra="forbid")

    text: SupportedNarrativeText
    subitems: list[SupportedNarrativeText] = Field(default_factory=list)


class SupportedDetailedPresentationCopy(BaseModel):
    """Presentation-specific contract for the real Devoteam detailed-reference slide."""

    model_config = ConfigDict(extra="forbid")

    mission_title: SupportedNarrativeText
    challenges: list[SupportedNarrativeText] = Field(default_factory=list)
    realisations: list[SupportedDetailedRealisation] = Field(default_factory=list)
    benefits: list[SupportedNarrativeText] = Field(default_factory=list)


class ReferenceNarrative(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference_id: str
    headline: SupportedNarrativeText
    short_description: SupportedNarrativeText
    challenge: SupportedNarrativeText
    devoteam_contribution: SupportedNarrativeText
    realisations: list[SupportedNarrativeText] = Field(default_factory=list)
    benefits: list[SupportedNarrativeText] = Field(default_factory=list)
    why_relevant_to_opportunity: SupportedNarrativeText
    detailed_presentation: SupportedDetailedPresentationCopy | None = None
    warnings: list[str] = Field(default_factory=list)


class ReferenceSectionNarrative(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section_intro: SupportedNarrativeText
    overall_storyline: SupportedNarrativeText
    why_these_references: SupportedNarrativeText
    references: list[ReferenceNarrative] = Field(default_factory=list)


class EditableReferenceSectionNarrative(BaseModel):
    """Browser-editable prose contract with no identity or provenance fields."""

    model_config = ConfigDict(extra="forbid")

    section_intro: str = ""
    overall_storyline: str = ""
    why_these_references: str = ""
    references: list[ReferenceNarrativeDraft] = Field(default_factory=list, max_length=161)


class NarrativeEditValidationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generation_request: NarrativeGenerationRequest
    narrative: EditableReferenceSectionNarrative


class NarrativeRegenerationRequest(NarrativeEditValidationRequest):
    scope: Literal["section_intro", "reference"]
    reference_id: str | None = None

    @model_validator(mode="after")
    def validate_scope(self) -> "NarrativeRegenerationRequest":
        if self.scope == "reference":
            if not self.reference_id or not REFERENCE_ID_RE.fullmatch(self.reference_id):
                raise ValueError("reference_id is required for reference regeneration")
        elif self.reference_id is not None:
            raise ValueError("reference_id is only valid for reference regeneration")
        return self


class ValidationWarning(BaseModel):
    code: str
    message: str
    severity: ValidationSeverity | None = None
    blocking: bool | None = None
    field_path: str | None = None
    reference_id: str | None = None
    support_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def ensure_severity_consistency(self) -> "ValidationWarning":
        if self.severity is None and self.blocking is None:
            self.severity = ValidationSeverity.BLOCKING
            self.blocking = True
        elif self.severity is None:
            self.severity = ValidationSeverity.BLOCKING if self.blocking else ValidationSeverity.WARNING
        elif self.blocking is None:
            self.blocking = self.severity == ValidationSeverity.BLOCKING
        if self.blocking != (self.severity == ValidationSeverity.BLOCKING):
            raise ValueError("warning blocking status does not match severity")
        return self


class NarrativeValidationResult(BaseModel):
    valid: bool
    export_blocked: bool
    export_eligible: bool | None = None
    warnings: list[ValidationWarning] = Field(default_factory=list)

    @model_validator(mode="after")
    def ensure_consistency(self) -> "NarrativeValidationResult":
        has_blocking = any(warning.severity == ValidationSeverity.BLOCKING for warning in self.warnings)
        if self.valid == has_blocking or self.export_blocked != has_blocking:
            raise ValueError("validation status does not match blocking warnings")
        expected_export_eligible = not has_blocking
        if self.export_eligible is None:
            self.export_eligible = expected_export_eligible
        elif self.export_eligible != expected_export_eligible:
            raise ValueError("export eligibility does not match blocking warnings")
        return self


class SourceSupportSummary(BaseModel):
    support_id: str
    reference_id: str
    support_types: list[SourceType]
    source_label: str
    page: int | None = None


class NarrativeGenerationProvenance(BaseModel):
    generated_at_utc: datetime
    provider: str
    model: str
    prompt_version: str
    prompt_sha256: str
    selected_reference_ids: list[str]
    source_supports: list[SourceSupportSummary]
    structured_output_retry_count: int
    validation_warning_codes: list[str]


class NarrativeGenerationResponse(BaseModel):
    narrative: ReferenceSectionNarrative
    validation: NarrativeValidationResult
    warnings: list[ValidationWarning]
    source_supports: list[SourceSupportSummary]
    support_plan: NarrativeSupportPlan
    provenance: NarrativeGenerationProvenance


class NarrativeReferenceMetadata(BaseModel):
    reference_id: str
    mission_title: str = ""
    client: str = ""
    country: str = ""
    sector: str = ""
    period: str = ""
    offering: str = ""


class NarrativeReviewResponse(BaseModel):
    narrative: ReferenceSectionNarrative
    validation: NarrativeValidationResult
    warnings: list[ValidationWarning]
    support_plan: NarrativeSupportPlan
    reference_metadata: list[NarrativeReferenceMetadata]
