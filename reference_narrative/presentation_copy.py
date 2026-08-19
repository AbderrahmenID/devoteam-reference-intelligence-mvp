from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Callable

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .claim_validator import ClaimValidator
from .content_sanitizer import sanitize_generation_text
from .field_policy import build_detailed_presentation_support_plan, field_material_records
from .ollama_client import NarrativeProvider
from .presentation_fit import TemplateFieldBudget, TemplateFitProfile
from .presentation_schemas import DirectPresentationRequest
from .prompt_builder import PromptPackage
from .quality import assess_reference_language
from .schemas import (
    FieldSupportPlan,
    NarrativeValidationResult,
    NarrativeSupportPlan,
    ReferenceNarrative,
    ReferenceSectionNarrative,
    SectionSupportPlan,
    SupportedDetailedPresentationCopy,
    SupportedDetailedRealisation,
    SupportedNarrativeText,
    SourceType,
    ValidationSeverity,
)
from .service import ReferenceNarrativeService


LOGGER = logging.getLogger("uvicorn.error")
ProgressCallback = Callable[[dict[str, object]], None]
BulletText = Annotated[str, Field(max_length=180)]
DetailedMainText = Annotated[str, Field(max_length=220)]
DetailedSubitemText = Annotated[str, Field(max_length=180)]
OrangeBulletText = Annotated[str, Field(max_length=90)]

ORANGE_PROMPT_VERSION = "ORANGE_REFERENCE_COPY-v1"
DETAILED_PROMPT_VERSION = "DETAILED_REFERENCE_COPY-v5"

ORANGE_SYSTEM_PROMPT = """You are preparing concise Devoteam reference-slide content for a commercial proposal.

Use only the supplied trusted reference facts and eligible evidence. Produce a short project title and factual activity bullets suitable for a compact Devoteam reference slide. Do not introduce organisations, technologies, numbers, results, certifications or outcomes that do not appear in the supplied material. Do not describe proposed work as completed unless eligible completed-work evidence supports it. Use presentation copy, not narrative paragraphs. Return only the requested JSON.
"""

DETAILED_SYSTEM_PROMPT = """You are a senior Devoteam consultant preparing a client-facing project reference slide.

You receive trusted information concerning ONE Devoteam reference. It can combine a reference database record, project description, technical offer, contract, attestation, completion evidence, and other approved evidence. Reason over that complete per-reference context. Your job is not to extract literal field labels or copy sentences: synthesize professional PowerPoint content while preserving factual safety. Never import facts from examples, the current opportunity, or another reference.

CHALLENGES: Explain the concrete business, organisational, or technological situation the mission was designed to address. Challenges may be inferred from project context, objectives, scope, diagnosed situation, requirements, and supported work even when no source section is literally named Challenges. Target 2–3 substantial, mission-specific bullets when the context permits. Do not route performed activities such as workshops, coaching, training, reporting, or committee animation into this section.

RÉALISATIONS: Explain concretely what Devoteam delivered or performed, based on supplied scope, activities, deliverables, and completion evidence. This is normally the richest section. Cover important analyses, diagnostics, workshops, procedures, assessments, roadmaps, target models, governance mechanisms, implementation, testing, project management, training, deliverables, and support activities. Target 3–6 meaningful main items when supported. Use subitems only for distinct supported child activities. Do not describe proposal-only work as completed.

BÉNÉFICES: Explain qualitative business or operational value logically resulting from the supported work. Benefits may be conservatively derived even when no source section is literally named Benefits. Prefer formulations such as strengthening, structuring, improved visibility, clarification, securing, availability, or improved ability. Do not merely repeat an activity. Never invent a measured result.

DOCUMENT ROLES: catalog/project descriptions provide detailed scope and activities; technical offers provide intended context, objectives, methodology, and proposed scope; attestations primarily confirm identity, period, engagement, completion, satisfaction, and explicitly described work. Use these sources together without changing their evidentiary meaning.

FACTUAL SAFETY: Never invent clients, organisations, countries, technologies, people, numbers, percentages, monetary savings, ROI, awards, certifications, incident counts, duration reductions, performance measurements, or achieved outcomes. Preserve supplied acronyms and never guess an expansion. The commercial opportunity is phrasing context only and is not evidence for facts about this reference.

Write entirely in the requested language. Use concise professional consulting language suitable for a real Devoteam commercial proposal. Return only valid JSON matching the requested schema.
"""

FIT_REPAIR_SYSTEM_PROMPT = """You are compressing one overflowing field for an existing Devoteam PowerPoint slide.

Rewrite only the requested field. Use only the supplied trusted facts. Preserve supported factual meaning while making the field shorter and more direct. Do not add facts, organisations, numbers, technologies, results, claims or completion language. Do not return any other presentation field. Return only the requested JSON.
"""


class OrangeReferenceCopy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_title: str = Field(default="", max_length=96)
    activities: list[OrangeBulletText] = Field(default_factory=list, max_length=6)

    @field_validator("display_title", "activities")
    @classmethod
    def strip_copy(cls, value):
        if isinstance(value, list):
            return [item.strip() for item in value if item.strip()]
        return value.strip()


class DetailedRealisationCopy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: DetailedMainText = Field(
        description="Concrete project workstream performed; never a challenge or benefit"
    )
    subitems: list[DetailedSubitemText] = Field(
        max_length=4,
        description="Concrete child activities belonging to this workstream; use [] when none",
    )

    @field_validator("text", "subitems")
    @classmethod
    def strip_copy(cls, value):
        if isinstance(value, list):
            return [item.strip() for item in value if item.strip()]
        return value.strip()


class DetailedReferenceCopy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mission_title: str = Field(default="", max_length=110, description="Concise professional mission title")
    challenges: list[BulletText] = Field(
        default_factory=list,
        max_length=3,
        description="Underlying business, organisational or technological needs; never project activities",
    )
    realisations: list[DetailedRealisationCopy] = Field(
        default_factory=list,
        max_length=6,
        description="Rich concrete project work; all trusted activity clauses belong here",
    )
    benefits: list[BulletText] = Field(
        default_factory=list,
        max_length=3,
        description="Supported or directly entailed operational value; never restate project activities",
    )

    @field_validator("mission_title", "challenges", "realisations", "benefits")
    @classmethod
    def strip_copy(cls, value):
        if isinstance(value, list):
            if not value or isinstance(value[0], str):
                return [item.strip() for item in value if item.strip()]
            return value
        return value.strip()


class MissionTitleRepair(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mission_title: str = Field(default="", max_length=110)


class ChallengeRepair(BaseModel):
    model_config = ConfigDict(extra="forbid")
    challenge: list[BulletText] = Field(default_factory=list, max_length=3)


class RealisationsRepair(BaseModel):
    model_config = ConfigDict(extra="forbid")
    realisations: list[DetailedRealisationCopy] = Field(default_factory=list, max_length=6)


class BenefitsRepair(BaseModel):
    model_config = ConfigDict(extra="forbid")
    benefits: list[BulletText] = Field(default_factory=list, max_length=3)


class OrangeTitleRepair(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_title: str = Field(default="", max_length=96)


class OrangeActivitiesRepair(BaseModel):
    model_config = ConfigDict(extra="forbid")
    activities: list[OrangeBulletText] = Field(default_factory=list, max_length=6)


@dataclass
class PresentationCopyResult:
    review: Any
    generation_records: list[dict[str, Any]]
    timings: dict[str, float]


def _package(system: str, payload: dict[str, Any], schema: dict[str, Any], version: str) -> PromptPackage:
    user_content = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user_content}]
    canonical = json.dumps(messages, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return PromptPackage(
        messages=messages,
        response_schema=schema,
        prompt_sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        prompt_version=version,
    )


def _fact(bundle, name: str) -> str:
    item = getattr(bundle.facts, name)
    return item.value if item else ""


def _safe_records(
    support_ids: list[str],
    support_index,
    *,
    maximum_characters: int = 4000,
) -> list[dict[str, Any]]:
    records = []
    for support_id in dict.fromkeys(support_ids):
        record = support_index[support_id]
        records.append(
            {
                "source_types": [source_type.value for source_type in record.support_types],
                "source_label": record.source_label,
                "text": record.text[:maximum_characters],
            }
        )
    return records


def _trusted_context_by_role(bundle, support_index) -> dict[str, object]:
    """Expose every approved record for one reference, grouped by evidentiary role."""

    catalog_ids = [
        record.support_id
        for record in bundle.structured_metadata_scope
        if record.source_label == "Structured catalog scope"
    ]
    proposal_ids = [
        record.support_id
        for record in bundle.display_evidence
        if any(
            source_type in record.support_types
            for source_type in (SourceType.PROPOSAL_SCOPE, SourceType.CONTRACTUAL_SCOPE)
        )
    ]
    completion_ids = [
        record.support_id
        for record in bundle.display_evidence
        if any(
            source_type in record.support_types
            for source_type in (SourceType.CLIENT_ATTESTATION, SourceType.COMPLETED_WORK_EVIDENCE)
        )
    ]
    classified = set([*proposal_ids, *completion_ids])
    other_ids = [
        record.support_id
        for record in bundle.display_evidence
        if record.support_id not in classified
    ]
    return {
        "reference_database_and_project_description": (
            _safe_records(catalog_ids, support_index) or "NO CATALOG SCOPE AVAILABLE"
        ),
        "technical_offer_and_contract_context": (
            _safe_records(proposal_ids, support_index) or "NO LINKED PROPOSAL OR CONTRACT CONTEXT"
        ),
        "attestation_and_completion_evidence": (
            _safe_records(completion_ids, support_index) or "NO LINKED ATTESTATION OR COMPLETION EVIDENCE"
        ),
        "other_approved_reference_evidence": (
            _safe_records(other_ids, support_index) or "NO OTHER APPROVED EVIDENCE"
        ),
    }


def _base_payload(request: DirectPresentationRequest, bundle) -> dict[str, Any]:
    trusted_description = next(
        (
            record.text
            for record in bundle.structured_metadata_scope
            if record.source_label == "Structured catalog scope"
        ),
        "",
    )
    return {
        "opportunity_context": sanitize_generation_text(request.opportunity_context, maximum_characters=4000),
        "target_language": request.target_language,
        "trusted_metadata": {
            "mission_title": _fact(bundle, "mission_title"),
            "client": _fact(bundle, "client"),
            "country": _fact(bundle, "country"),
            "sector": _fact(bundle, "sector"),
            "period": _fact(bundle, "period"),
            "offering": _fact(bundle, "offering"),
        },
        "trusted_reference_description": trusted_description,
    }


def _source_richness(bundle, plan: FieldSupportPlan) -> str:
    description = " ".join(record.text for record in bundle.structured_metadata_scope).strip()
    evidence_count = len(set([*plan.challenge, *plan.realisations, *plan.benefits]))
    activity_count = len(_source_activity_clauses(description))
    if activity_count >= 3 or evidence_count >= 4 or len(description) >= 650:
        return "RICH"
    if activity_count >= 2 or evidence_count >= 2 or len(description) >= 240:
        return "MEDIUM"
    return "SPARSE"


def _source_activity_clauses(description: str) -> list[str]:
    action = (
        r"préparation|formalisation|appui|élaboration|elaboration|organisation|cadrage|"
        r"initialisation|diagnostic|proposition|déclinaison|definition|définition|"
        r"mise\s+en\s+place|réalisation|realisation|gestion|pilotage|coaching|formation|"
        r"reporting|animation|benchmark(?:ing)?"
    )
    parts = re.split(
        rf"\s*[•▪·]\s*|\s*;\s*|\s+(?=(?:{action})\b)",
        description,
        flags=re.IGNORECASE,
    )
    clauses = [
        sanitize_generation_text(part, maximum_characters=260).strip(" -:;")
        for part in parts
        if part.strip()
    ]
    merged: list[str] = []
    pending = ""
    for clause in clauses:
        if pending:
            clause = f"{pending} {clause}".strip()
            pending = ""
        if len(clause.split()) < 2 or re.search(r"\b(?:et|appui\s+à\s+la)$", clause, re.IGNORECASE):
            pending = clause
        else:
            merged.append(clause)
    if pending:
        if merged:
            merged[-1] = f"{merged[-1]} {pending}".strip()
        else:
            merged.append(pending)
    merged = list(dict.fromkeys(merged))
    while len(merged) > 6:
        index = min(
            range(len(merged) - 1),
            key=lambda value: len(merged[value]) + len(merged[value + 1]),
        )
        connector = " " if re.search(r"\b(?:et|à\s+la)$", merged[index], re.IGNORECASE) else "; "
        combined = sanitize_generation_text(
            f"{merged[index]}{connector}{merged[index + 1]}",
            maximum_characters=360,
        )
        merged[index:index + 2] = [combined]
    return merged


def build_orange_prompt(
    request: DirectPresentationRequest,
    bundle,
    plan: FieldSupportPlan,
    support_index,
    *,
    repair: bool,
    layout_budget: dict[str, str] | None = None,
) -> PromptPackage:
    schema = OrangeReferenceCopy.model_json_schema()
    activity_ids = list(dict.fromkeys([
        *plan.realisations,
        *plan.devoteam_contribution,
        *plan.short_description,
    ]))
    if not activity_ids:
        schema["properties"]["activities"]["maxItems"] = 0
    payload = {
        **_base_payload(request, bundle),
        "task": "ORANGE_REFERENCE_COPY",
        "layout_budget": layout_budget or {
            "display_title": "one short line where possible, maximum 96 characters",
            "activities": "approximately 3-6 bullets when supported; maximum 90 characters per bullet",
        },
        "eligible_activity_evidence": _safe_records(activity_ids, support_index) or "NO ELIGIBLE SUPPORT",
        "repair_instruction": (
            "Rewrite using only supplied facts. Remove unsupported names, numbers, certifications and outcomes."
            if repair else None
        ),
        "required_output_schema": schema,
    }
    return _package(ORANGE_SYSTEM_PROMPT, payload, schema, ORANGE_PROMPT_VERSION)


def build_detailed_prompt(
    request: DirectPresentationRequest,
    bundle,
    plan: FieldSupportPlan,
    support_index,
    *,
    repair: bool,
    repair_instruction: str | None = None,
    accepted_copy: dict[str, Any] | None = None,
    repair_fields: list[str] | None = None,
    layout_budget: dict[str, str] | None = None,
) -> PromptPackage:
    schema = DetailedReferenceCopy.model_json_schema()
    richness = _source_richness(bundle, plan)
    schema["required"] = ["mission_title", "challenges", "realisations", "benefits"]
    if not plan.challenge:
        schema["properties"]["challenges"]["maxItems"] = 0
    if not plan.realisations:
        schema["properties"]["realisations"]["maxItems"] = 0
    if not plan.benefits:
        schema["properties"]["benefits"]["maxItems"] = 0
    if richness == "RICH":
        if plan.challenge:
            schema["properties"]["challenges"]["minItems"] = 1
        if plan.realisations:
            schema["properties"]["realisations"]["minItems"] = 3
        if plan.benefits:
            schema["properties"]["benefits"]["minItems"] = 1
    if repair and repair_fields:
        for output_field in ("challenges", "realisations", "benefits"):
            if output_field not in repair_fields:
                schema["properties"][output_field]["maxItems"] = 0
            elif getattr(plan, output_field if output_field != "challenges" else "challenge"):
                schema["properties"][output_field]["minItems"] = (
                    3 if output_field == "realisations" and richness == "RICH" else 1
                )
    source_activity_clauses = _source_activity_clauses(
        next(
            (
                record.text
                for record in bundle.structured_metadata_scope
                if record.source_label == "Structured catalog scope"
            ),
            "",
        )
    )
    base_payload = _base_payload(request, bundle)
    opportunity_context = base_payload.pop("opportunity_context", "")
    base_payload.pop("trusted_reference_description", None)
    payload = {
        **base_payload,
        "task": "DETAILED_REFERENCE_COPY",
        "source_richness": richness,
        "repair_only_these_fields": repair_fields if repair else None,
        "hard_constraints": {
            "every_listed_activity_belongs_in_realisations": source_activity_clauses,
            "section_routing": (
                "Do not copy listed activity phrases as Challenges or Bénéfices. Synthesize Challenges from trusted "
                "context, objectives, scope, and work. Synthesize conservative non-quantified Bénéfices from the "
                "operational value logically enabled by trusted work, even without literal source field labels."
            ),
            "minimum_meaningful_realisations_for_rich_source": 3,
            "invented_child_activities_forbidden": True,
            "subitems_require_explicit_source_support": True,
            "french_challenges_must_describe_a_need_or_situation_not_an_action": (
                "Begin French challenge bullets with Besoin de, Nécessité de, Difficulté à, Absence de, Limites de, "
                "Enjeu de or a concrete factual situation; never begin with an action infinitive."
            ),
            "french_benefits_must_be_conservative": (
                "Use Renforcement de, Structuration de, Amélioration de la visibilité sur, Clarification de, "
                "Sécurisation de, Mise à disposition de or Meilleure capacité à; do not claim reduction or compliance."
            ),
        },
        "required_field_instruction": (
            "Return all four keys exactly once: mission_title, challenges, realisations and benefits. "
            "Every realisation must be an object with text and subitems. Never return a simple string list. "
            + (
                "This is a targeted repair: populate only repair_only_these_fields, return [] for every passing list field, "
                "and copy the accepted mission_title exactly unless mission_title itself is being repaired."
                if repair else ""
            )
        ),
        "trusted_source_activity_clauses": source_activity_clauses,
        "layout_budget": layout_budget or {
            "mission_title": "short enough for the source template, maximum 110 characters",
            "challenges": "1-3 substantial bullets when context exists",
            "realisations": "3-6 meaningful main items when supported; use child activities where the source has hierarchy",
            "benefits": "1-3 substantial bullets when explicit or directly entailed value is supported",
            "bullet_length": "maximum 180 characters per bullet",
        },
        "eligible_evidence": {
            "challenges": bool(plan.challenge),
            "realisations": bool(plan.realisations),
            "benefits": bool(plan.benefits),
        },
        "current_commercial_opportunity": {
            "context_for_relevance_and_phrasing_only": opportunity_context or "NO OPPORTUNITY CONTEXT PROVIDED",
            "factual_use": "FORBIDDEN — this is not evidence about the reference",
        },
        "trusted_project_information": {
            "document_role_guidance": {
                "reference_database": "Detailed scope, services, activities, phases, and deliverables.",
                "technical_offer_or_contract": "Intended context, objectives, methodology, and proposed scope; not proof of completion.",
                "attestation_or_completion": "Identity, period, engagement/completion, satisfaction, and explicitly described work.",
                "other_approved_evidence": "Use according to its supplied source types without upgrading evidentiary strength.",
            },
            "all_available_context_for_this_reference": _trusted_context_by_role(bundle, support_index),
            "parsed_source_activity_clauses": source_activity_clauses,
        },
        "repair_instruction": (
            repair_instruction
            or (
                "The previous presentation copy omitted important information contained in the trusted source. "
                "Rewrite the reference slide. Preserve factual grounding but make the slide substantially more complete. "
                "Extract the important project work into Réalisations and produce meaningful Challenges and Bénéfices "
                "where supported. Do not summarize a rich mission into only one or two sentences."
            )
            if repair else None
        ),
        "accepted_grounded_copy_to_preserve": accepted_copy if repair else None,
    }
    return _package(DETAILED_SYSTEM_PROMPT, payload, schema, DETAILED_PROMPT_VERSION)


class PresentationCopyService:
    def __init__(
        self,
        narrative_service: ReferenceNarrativeService,
        provider: NarrativeProvider,
        project_root: Path | None = None,
    ):
        self.narrative_service = narrative_service
        self.provider = provider
        self.fit_profile = TemplateFitProfile(project_root or Path(__file__).parents[1])

    @staticmethod
    def _empty_text() -> SupportedNarrativeText:
        return SupportedNarrativeText(text="", support_ids=[])

    def _reference_from_copy(self, copy, plan: FieldSupportPlan, template_id: str) -> ReferenceNarrative:
        if template_id == "orange_bank_compact":
            activity_support = list(dict.fromkeys([
                *plan.realisations,
                *plan.devoteam_contribution,
                *plan.short_description,
            ]))
            return ReferenceNarrative(
                reference_id=plan.reference_id,
                headline=self.narrative_service._supported_text(copy.display_title, plan.headline),
                short_description=self._empty_text(),
                challenge=self._empty_text(),
                devoteam_contribution=self._empty_text(),
                realisations=[self.narrative_service._supported_text(item, activity_support) for item in copy.activities],
                benefits=[],
                why_relevant_to_opportunity=self._empty_text(),
                warnings=[],
            )
        challenge_support = list(plan.challenge)
        realisation_support = list(plan.realisations)
        benefit_support = list(plan.benefits)
        detailed = SupportedDetailedPresentationCopy(
            mission_title=self.narrative_service._supported_text(copy.mission_title, plan.headline),
            challenges=[
                self.narrative_service._supported_text(item, challenge_support)
                for item in copy.challenges
            ],
            realisations=[
                SupportedDetailedRealisation(
                    text=self.narrative_service._supported_text(item.text, realisation_support),
                    subitems=[
                        self.narrative_service._supported_text(subitem, realisation_support)
                        for subitem in item.subitems
                    ],
                )
                for item in copy.realisations
            ],
            benefits=[
                self.narrative_service._supported_text(item, benefit_support)
                for item in copy.benefits
            ],
        )
        flattened_realisations = [
            value
            for item in copy.realisations
            for value in [item.text, *item.subitems]
        ]
        return ReferenceNarrative(
            reference_id=plan.reference_id,
            headline=detailed.mission_title,
            short_description=self._empty_text(),
            challenge=self.narrative_service._supported_text("\n".join(copy.challenges), plan.challenge),
            devoteam_contribution=self._empty_text(),
            realisations=[
                self.narrative_service._supported_text(item, plan.realisations)
                for item in flattened_realisations
            ],
            benefits=detailed.benefits,
            why_relevant_to_opportunity=self._empty_text(),
            detailed_presentation=detailed,
            warnings=[],
        )

    def _validate_one(self, source_result, bundle, plan, narrative: ReferenceNarrative):
        section = SectionSupportPlan()
        support_plan = NarrativeSupportPlan(references=[plan], section=section)
        wrapper = ReferenceSectionNarrative(
            section_intro=self._empty_text(),
            overall_storyline=self._empty_text(),
            why_these_references=self._empty_text(),
            references=[narrative],
        )
        return ClaimValidator(
            [bundle],
            source_result.support_index,
            source_result.known_fact_values,
            support_plan=support_plan,
            allow_catalog_completion_detail=True,
        ).validate(wrapper, [bundle.reference_id])

    @staticmethod
    def _blocking(validation) -> list[Any]:
        return [
            warning for warning in validation.warnings
            if warning.severity == ValidationSeverity.BLOCKING or warning.blocking
        ]

    def _safe_reference(self, bundle, plan: FieldSupportPlan) -> ReferenceNarrative:
        title = _fact(bundle, "mission_title")
        reference = ReferenceNarrative(
            reference_id=plan.reference_id,
            headline=self.narrative_service._supported_text(title, plan.headline),
            short_description=self._empty_text(),
            challenge=self._empty_text(),
            devoteam_contribution=self._empty_text(),
            realisations=[],
            benefits=[],
            why_relevant_to_opportunity=self._empty_text(),
            warnings=["AI copy unavailable; trusted factual fallback used."],
        )
        reference.detailed_presentation = SupportedDetailedPresentationCopy(
            mission_title=reference.headline,
            challenges=[],
            realisations=[],
            benefits=[],
        )
        return reference

    def _copy_is_grounded(self, request, source_result, bundle, plan, copy) -> bool:
        narrative = self._reference_from_copy(copy, plan, request.template_id)
        return not self._blocking(self._validate_one(source_result, bundle, plan, narrative))

    def _copy_is_factually_safe(
        self,
        request,
        source_result,
        bundle,
        plan,
        copy,
        *,
        allowed_inference_codes: set[str] | None = None,
    ) -> bool:
        """Validate concrete facts while permitting an explicitly classified inference."""

        allowed = allowed_inference_codes or set()
        narrative = self._reference_from_copy(copy, plan, request.template_id)
        blocking = self._blocking(self._validate_one(source_result, bundle, plan, narrative))
        return not [warning for warning in blocking if warning.code not in allowed]

    def _safe_supported_portions(self, request, source_result, bundle, plan, candidate):
        """Retain independently grounded fields from the final attempt and clear the rest."""
        trusted_title = _fact(bundle, "mission_title")
        if request.template_id == "orange_bank_compact":
            safe = OrangeReferenceCopy(display_title=trusted_title, activities=[])
            title_only = safe.model_copy(update={"display_title": candidate.display_title})
            if candidate.display_title and self._copy_is_grounded(
                request, source_result, bundle, plan, title_only
            ):
                safe.display_title = candidate.display_title
            accepted: list[str] = []
            for activity in candidate.activities:
                unit = OrangeReferenceCopy(display_title="", activities=[activity])
                if self._copy_is_grounded(request, source_result, bundle, plan, unit):
                    accepted.append(activity)
            safe.activities = accepted[:6]
            return self._reference_from_copy(safe, plan, request.template_id)

        safe = DetailedReferenceCopy(mission_title=trusted_title)
        candidate_title = self._strip_foreign_script_artifacts(candidate.mission_title, request.target_language)
        title_only = safe.model_copy(update={"mission_title": candidate_title})
        if (
            candidate_title
            and self._has_catalog_activity_anchor(candidate_title, bundle)
            and self._lexically_entailed(candidate_title, bundle, request.target_language)
            and self._copy_is_grounded(
                request, source_result, bundle, plan, title_only
            )
        ):
            safe.mission_title = candidate_title
        for field_name in ("challenges", "benefits"):
            accepted: list[str] = []
            for item in getattr(candidate, field_name):
                item = self._strip_untrusted_acronym_expansions(item, bundle)
                item = self._strip_foreign_script_artifacts(item, request.target_language)
                item = self._strip_person_attribution(item)
                item = self._strip_repeated_trailing_fragment(item)
                item = self._strip_dangling_tail(item)
                if not item or len(item.split()) < 3:
                    continue
                delivery_phrase = bool(re.search(
                    r"^(?:préparer|formaliser|appuyer|élaborer|organiser|cadrer|initialiser|diagnostiquer|"
                    r"proposer|décliner|définir|identifier|mettre\s+en\s+place|réaliser|gérer|piloter|coacher|"
                    r"former|produire|animer|exécuter|préparation|formalisation|appui|élaboration|organisation|cadrage|initialisation|"
                    r"diagnostic|proposition|déclinaison|définition|mise\s+en\s+place|réalisation|gestion|"
                    r"pilotage|coaching|formation|reporting|animation|tests?|exécution)\b",
                    item,
                    re.IGNORECASE,
                ))
                if delivery_phrase:
                    continue
                if field_name == "challenges":
                    if not self._has_catalog_activity_anchor(item, bundle):
                        continue
                    if re.match(
                        r"^(?:besoin|nécessité|enjeu)\s+(?:de|d['’])\s*(?:mettre\s+en\s+place|"
                        r"mise\s+en\s+place|élaborer|élaboration|définir|définition|formaliser|formalisation|"
                        r"initialiser|initialisation|réaliser|réalisation|produire|production|animer|animation|former|formation)\b",
                        item,
                        re.IGNORECASE,
                    ):
                        continue
                if field_name == "benefits":
                    item = re.sub(
                        r"\s+(?:face\s+(?:à|aux)|grâce\s+à|afin\s+de|pour\s+(?:une|un|le|la|les)|"
                        r"en\s+situation\s+d['’])\b.*$",
                        "",
                        item,
                        flags=re.IGNORECASE,
                    ).rstrip(" ,;:-")
                    if re.search(
                        r"\b(?:via|par)\s+(?:(?:le|la|les|l['’])\s*)?(?:coaching|animation|formation|"
                        r"reporting|mise\s+en\s+place)\b",
                        item,
                        re.IGNORECASE,
                    ):
                        continue
                unit = DetailedReferenceCopy(mission_title="").model_copy(
                    update={field_name: [item]}
                )
                if field_name == "benefits":
                    explicit_result = self._copy_is_grounded(
                        request, source_result, bundle, plan, unit
                    )
                    derived_value = (
                        self._is_conservative_derived_benefit(
                            item, bundle, request.target_language
                        )
                        and self._copy_is_factually_safe(
                            request,
                            source_result,
                            bundle,
                            plan,
                            unit,
                            allowed_inference_codes={"UNSUPPORTED_BENEFIT"},
                        )
                    )
                    if explicit_result or derived_value:
                        accepted.append(item)
                elif (
                    self._has_reference_anchor(item, bundle)
                    and self._copy_is_grounded(request, source_result, bundle, plan, unit)
                ):
                    accepted.append(item)
            setattr(safe, field_name, self._unique_complete_items(accepted))

        accepted_realisations: list[DetailedRealisationCopy] = []
        for item in candidate.realisations:
            main = self._strip_untrusted_acronym_expansions(item.text, bundle)
            main = self._strip_foreign_script_artifacts(main, request.target_language)
            main = self._strip_person_attribution(main)
            main = self._strip_repeated_trailing_fragment(main)
            main = self._strip_dangling_tail(main)
            main = self._strip_orphan_phase_label(main)
            main_ok = bool(
                main
                and self._is_atomic_bullet(main)
                and len(main.split()) >= 3
                and self._has_catalog_activity_anchor(main, bundle)
                and self._lexically_entailed(main, bundle, request.target_language)
            )
            if main_ok:
                unit = DetailedReferenceCopy(
                    mission_title="",
                    realisations=[DetailedRealisationCopy(text=main, subitems=[])],
                )
                main_ok = self._copy_is_grounded(request, source_result, bundle, plan, unit)

            accepted_subitems: list[str] = []
            for raw_subitem in item.subitems:
                subitem = self._strip_untrusted_acronym_expansions(raw_subitem, bundle)
                subitem = self._strip_foreign_script_artifacts(subitem, request.target_language)
                subitem = self._strip_person_attribution(subitem)
                subitem = self._strip_repeated_trailing_fragment(subitem)
                subitem = self._strip_dangling_tail(subitem)
                subitem = self._strip_orphan_phase_label(subitem)
                if (
                    not subitem
                    or not self._is_atomic_bullet(subitem)
                    or len(subitem.split()) < 3
                    or not self._has_catalog_activity_anchor(subitem, bundle)
                ):
                    continue
                if not self._lexically_entailed(subitem, bundle, request.target_language):
                    continue
                unit = DetailedReferenceCopy(
                    mission_title="",
                    realisations=[DetailedRealisationCopy(text=subitem, subitems=[])],
                )
                if self._copy_is_grounded(request, source_result, bundle, plan, unit):
                    accepted_subitems.append(subitem)

            if main_ok:
                accepted_realisations.append(
                    DetailedRealisationCopy(
                        text=main,
                        subitems=self._unique_complete_items(accepted_subitems),
                    )
                )
            else:
                # Preserve independently valid child bullets instead of erasing the workstream.
                accepted_realisations.extend(
                    DetailedRealisationCopy(text=subitem, subitems=[])
                    for subitem in self._unique_complete_items(accepted_subitems)
                )
        deduplicated_realisations: list[DetailedRealisationCopy] = []
        for item in accepted_realisations:
            item_tokens = self._semantic_tokens(item.text)
            duplicate = next(
                (
                    existing
                    for existing in deduplicated_realisations
                    if item_tokens
                    and self._semantic_tokens(existing.text)
                    and len(item_tokens & self._semantic_tokens(existing.text))
                    / min(len(item_tokens), len(self._semantic_tokens(existing.text)))
                    >= 0.65
                ),
                None,
            )
            if duplicate is not None:
                duplicate.subitems = self._unique_complete_items([
                    *duplicate.subitems,
                    *item.subitems,
                ])[:4]
            else:
                deduplicated_realisations.append(item)
        safe.realisations = deduplicated_realisations[:6]
        return self._reference_from_copy(safe, plan, request.template_id)

    @classmethod
    def _strip_untrusted_acronym_expansions(cls, text: str, bundle) -> str:
        """Keep a trusted acronym while removing a model-guessed expansion fragment."""

        scope = cls._trusted_scope(bundle)
        trusted_acronyms = {
            value
            for value in re.findall(r"\b[A-ZÀ-ÖØ-Þ]{2,6}\b", scope)
            if value not in {"ETAPE", "PHASE"}
        }
        repaired = text
        for acronym in trusted_acronyms:
            escaped = re.escape(acronym)
            repaired = re.sub(
                rf"\b{escaped}\s*\([^)]{{3,100}}\)",
                acronym,
                repaired,
            )
            repaired = re.sub(
                rf"\b((?:formalisation|élaboration|définition|préparation)\s+(?:du|de\s+la|des|d['’])\s+)"
                rf"[^.;()]{{3,100}}?\s*\({escaped}\)",
                rf"\1{acronym}",
                repaired,
                flags=re.IGNORECASE,
            )
        return re.sub(r"\s{2,}", " ", repaired).strip()

    @staticmethod
    def _strip_foreign_script_artifacts(text: str, target_language: str) -> str:
        if target_language != "fr":
            return text.strip()
        cleaned = "".join(
            character
            if not character.isalpha() or "LATIN" in unicodedata.name(character, "")
            else " "
            for character in text
        )
        cleaned = re.sub(r"\s{2,}", " ", cleaned)
        return cleaned.rstrip(" ,;:-").strip()

    @staticmethod
    def _strip_person_attribution(text: str) -> str:
        repaired = re.sub(
            r"\s+par\s+(?:un|une)\s+[^.;()]{0,60}\((?:M\.|Mme|Mlle|Mr|Mrs|Ms|Dr|Pr)\s+[^)]{1,80}\)",
            "",
            text,
            flags=re.IGNORECASE,
        )
        repaired = re.sub(
            r"\s*\((?:M\.|Mme|Mlle|Mr|Mrs|Ms|Dr|Pr)\s+[^)]{1,80}\)",
            "",
            repaired,
            flags=re.IGNORECASE,
        )
        repaired = re.sub(
            r"\bpar\s+(?:M\.|Mme|Mlle|Mr|Mrs|Ms|Dr|Pr)\s+[^,.;()]+(?:,\s*[^.;()]*)?",
            "",
            repaired,
            flags=re.IGNORECASE,
        )
        repaired = re.sub(r"\s+([.,;])", r"\1", repaired)
        return re.sub(r"\s{2,}", " ", repaired).strip(" ,;:-")

    @staticmethod
    def _strip_repeated_trailing_fragment(text: str) -> str:
        """Remove a response echo when its final words repeat its opening."""
        words = re.sub(r"\s+", " ", text).strip().split(" ")
        if len(words) < 5:
            return " ".join(words)

        def normalized(values: list[str]) -> list[str]:
            result: list[str] = []
            for value in values:
                plain = unicodedata.normalize("NFKD", value.casefold())
                plain = "".join(char for char in plain if not unicodedata.combining(char))
                result.append(re.sub(r"[^a-z0-9]", "", plain))
            return result

        normalized_words = normalized(words)
        for size in range(min(5, len(words) // 2), 0, -1):
            if normalized_words[:size] == normalized_words[-size:]:
                return " ".join(words[:-size]).rstrip(" ,;:-")
        return " ".join(words)

    @staticmethod
    def _strip_dangling_tail(text: str) -> str:
        """Remove a model/schema cutoff that leaves a bullet on a connector."""

        repaired = text.strip()
        dangling = re.compile(
            r"(?:\s|^)(?:ainsi\s+que|de|du|des|d['’]|la|le|les|et|ou|avec|pour|sur|en|"
            r"and|or|of|to|for|with|on|in|as\s+well\s+as)\s*$",
            re.IGNORECASE,
        )
        while dangling.search(repaired.rstrip(" ,;:-")):
            repaired = dangling.sub("", repaired.rstrip(" ,;:-")).rstrip(" ,;:-")
        return repaired

    @staticmethod
    def _strip_orphan_phase_label(text: str) -> str:
        """Do not attach a source phase label to an unrelated synthesized activity."""

        repaired = text
        for match in list(re.finditer(r"\((?:phase|étape)\s*\d*\s*:\s*test\w*\)", repaired, re.IGNORECASE)):
            remainder = f"{repaired[:match.start()]} {repaired[match.end():]}"
            if not re.search(r"\b(?:test|essai|exercice)\w*\b", remainder, re.IGNORECASE):
                repaired = f"{repaired[:match.start()]} {repaired[match.end():]}"
        repaired = re.sub(r"\s+([.,;])", r"\1", repaired)
        return re.sub(r"\s{2,}", " ", repaired).strip(" ,;:-")

    @staticmethod
    def _is_atomic_bullet(text: str) -> bool:
        return text.count(";") < 2

    @classmethod
    def _has_catalog_activity_anchor(cls, text: str, bundle) -> bool:
        def tokens(value: str) -> set[str]:
            normalized = unicodedata.normalize("NFKD", value.casefold())
            normalized = "".join(character for character in normalized if not unicodedata.combining(character))
            return set(re.findall(r"[a-z0-9]{3,}", normalized))

        generic = {
            "accompagnement", "assistance", "client", "mission", "projet", "projets",
            "mise", "place", "realisation", "definition", "organisation", "gestion",
            "suivi", "activite", "activites", "action", "actions", "strategique",
            "avec", "dans", "des", "les", "pour", "une", "aux", "ainsi", "que",
            "par", "sur", "son", "ses", "leur", "leurs", "cette", "tout", "tous",
        }
        catalog_tokens = tokens(cls._trusted_scope(bundle)) - generic
        return bool((tokens(text) - generic) & catalog_tokens)

    @staticmethod
    def _trusted_scope(bundle) -> str:
        return " ".join(
            record.text
            for record in bundle.structured_metadata_scope
            if record.source_label == "Structured catalog scope"
        ).strip()

    @classmethod
    def _lexically_entailed(cls, text: str, bundle, target_language: str) -> bool:
        """Reject concrete invented detail while allowing conservative consulting rewrites."""
        if target_language != "fr":
            return True

        def tokens(value: str) -> set[str]:
            normalized = unicodedata.normalize("NFKD", value.casefold())
            normalized = "".join(character for character in normalized if not unicodedata.combining(character))
            return set(re.findall(r"[a-z0-9]{4,}", normalized))

        trusted = " ".join([
            cls._trusted_scope(bundle),
            *[
                record.text
                for group in (
                    bundle.completed_work_evidence,
                    bundle.proposal_scope,
                    bundle.display_evidence,
                )
                for record in group
            ],
            *[
                _fact(bundle, field)
                for field in ("mission_title", "client", "country", "sector", "offering")
            ],
        ])
        trusted_tokens = tokens(trusted)
        normalized_candidate = unicodedata.normalize("NFKD", text.casefold())
        normalized_candidate = "".join(
            character for character in normalized_candidate if not unicodedata.combining(character)
        )
        normalized_trusted = unicodedata.normalize("NFKD", trusted.casefold())
        normalized_trusted = "".join(
            character for character in normalized_trusted if not unicodedata.combining(character)
        )
        unsupported_inference_patterns = (
            r"\badapt\w*\s+(?:aux?|a\s+la)\s+specific",
            r"\bcontexte\s+(?:local|national|bancaire)",
            r"\bentre\s+(?:les\s+)?(?:departements|directions|equipes)",
        )
        if any(re.search(pattern, normalized_candidate) for pattern in unsupported_inference_patterns):
            return False
        if re.match(r"^(?:absence|difficulte|limite)\b", normalized_candidate) and not re.search(
            r"\b(?:absence|difficulte|limite)\b", normalized_trusted
        ):
            return False
        allowed_rewrite_tokens = {
            "besoin", "necessite", "difficulte", "enjeu", "amelioration", "renforcement",
            "structuration", "clarification", "securisation", "visibilite", "meilleure", "capacite",
            "permettre", "assurer", "dispose", "disposer", "operationnel", "operationnelle",
            "organisationnel", "organisationnelle", "resilience", "coherence", "coherent", "coherente",
            "pilotage", "piloter", "elaboration", "elaborer", "formalisation", "formaliser",
            "preparation", "preparer", "realisation", "realiser", "gestion", "gerer", "definition",
            "definir", "accompagnement", "accompagner", "appui", "mise", "place", "maintien",
            "concrete", "adaptation", "adoption", "efficace", "efficacite", "dispositif", "demarche",
            "cadre", "activite", "activites", "mission", "travaux", "equipes", "projet", "projets",
            "leurs", "cette", "ainsi", "entre", "faire", "grace", "meilleur", "meilleure",
            "avancement", "interruption", "interruptions", "preparation", "resultat", "resultats",
            "role", "roles", "responsabilite", "responsabilites",
        }
        candidate_tokens = tokens(text)
        unknown = candidate_tokens - trusted_tokens - allowed_rewrite_tokens
        return len(unknown) < 2 or len(unknown) / max(1, len(candidate_tokens)) <= 0.20

    @staticmethod
    def _trusted_reference_text(bundle) -> str:
        facts = [
            _fact(bundle, field)
            for field in (
                "mission_title", "client", "country", "sector", "period",
                "offering", "business_unit",
            )
        ]
        records = [
            record.text
            for group in (bundle.structured_metadata_scope, bundle.display_evidence)
            for record in group
        ]
        return " ".join([*facts, *records])

    @staticmethod
    def _inference_tokens(value: str) -> set[str]:
        normalized = unicodedata.normalize("NFKD", value.casefold())
        normalized = "".join(
            character for character in normalized if not unicodedata.combining(character)
        )
        stop = {
            "about", "after", "avec", "client", "dans", "devoteam", "from", "mission",
            "pour", "project", "projet", "reference", "that", "their", "this", "through",
            "using", "with", "work", "the", "and", "des", "les", "une", "sur", "par",
            "المشروع", "العميل", "هذه", "التي", "على", "إلى", "في", "من", "مع",
        }
        return {
            token
            for token in re.findall(r"[^\W_]{2,}", normalized, flags=re.UNICODE)
            if token not in stop and not token.isdigit()
        }

    @classmethod
    def _has_reference_anchor(cls, text: str, bundle) -> bool:
        """Require a noun, fact, or acronym traceable to this reference."""

        candidate = cls._inference_tokens(text)
        trusted = cls._inference_tokens(cls._trusted_reference_text(bundle))
        for value in candidate:
            for source in trusted:
                if value == source:
                    return True
                if min(len(value), len(source)) >= 5 and (
                    value.startswith(source) or source.startswith(value)
                ):
                    return True
        return False

    @classmethod
    def _is_conservative_derived_benefit(
        cls,
        text: str,
        bundle,
        target_language: str,
    ) -> bool:
        """Classify qualitative operational value separately from explicit results."""

        prefixes = {
            "fr": (
                r"(?:renforcement|structuration|amélioration(?:\s+de\s+la\s+visibilité)?|"
                r"clarification|sécurisation|mise\s+à\s+disposition|meilleure\s+capacité|"
                r"meilleure\s+préparation|consolidation)"
            ),
            "en": (
                r"(?:strengthening|structuring|improved\s+visibility|greater\s+visibility|"
                r"clarification|securing|availability|improved\s+ability|greater\s+ability|"
                r"better\s+preparedness|enhanced\s+preparedness|consolidation)"
            ),
            "ar": (
                r"(?:تعزيز|هيكلة|تحسين\s+الرؤية|توضيح|تأمين|إتاحة|قدرة\s+أفضل|"
                r"تحسين\s+القدرة|رفع\s+الجاهزية|ترسيخ)"
            ),
        }
        if not re.match(rf"^\s*{prefixes[target_language]}\b", text, re.IGNORECASE):
            return False
        unsupported_measured_or_external = re.compile(
            r"(?:\b(?:roi|return\s+on\s+investment|retour\s+sur\s+investissement|"
            r"savings?|économies?|gains?\s+financiers?|revenue|profit|award|prix|trophée|"
            r"certification|certifié|compliance|conformité|faster|duration\s+reduction)\b|%|"
            r"العائد\s+على\s+الاستثمار|وفورات|أرباح|جائزة|شهادة)",
            re.IGNORECASE,
        )
        return (
            not unsupported_measured_or_external.search(text)
            and cls._has_reference_anchor(text, bundle)
        )

    def _detailed_quality_status(
        self,
        request,
        bundle,
        plan,
        narrative: ReferenceNarrative,
    ) -> dict[str, bool]:
        scope = self._trusted_scope(bundle)
        activity_signals = re.findall(
            r"\b(?:formalisation|élaboration|mise\s+en\s+place|accompagnement|appui|diagnostic|"
            r"analyse|cadrage|définition|déclinaison|proposition|préparation|réalisation|"
            r"pilotage|gestion|organisation|structuration|coaching|formation|reporting|animation|planification|procédure|"
            r"roadmap|assessment|deliverable|governance|implementation|training|testing|tests?)\b",
            scope,
            flags=re.IGNORECASE,
        )
        distinct_activity_signals = {value.casefold() for value in activity_signals}
        richness = _source_richness(bundle, plan)
        rich_reference = richness == "RICH"
        language_ok = (
            assess_reference_language(narrative, request.target_language).status
            != "CLEAR_MISMATCH"
        )
        detailed = narrative.detailed_presentation
        challenges = [item.text for item in detailed.challenges if item.text.strip()] if detailed else []
        main_realisations = [item.text.text for item in detailed.realisations if item.text.text.strip()] if detailed else []
        nested_realisations = [
            subitem.text
            for item in detailed.realisations
            for subitem in item.subitems
            if subitem.text.strip()
        ] if detailed else []
        realisations = [*main_realisations, *nested_realisations]
        benefits = [item.text for item in detailed.benefits if item.text.strip()] if detailed else []
        populated = [*challenges, *realisations, *benefits]
        mission_title = narrative.headline.text.strip()
        required_acronyms = {
            value
            for value in re.findall(r"\b[A-ZÀ-ÖØ-Þ]{2,6}\b", scope)
            if value not in {"ETAPE", "PHASE"}
        }
        client_acronyms = set(re.findall(r"\b[A-ZÀ-ÖØ-Þ]{2,8}\b", _fact(bundle, "client")))
        required_acronyms -= client_acronyms
        generated_text = " ".join([
            mission_title,
            *populated,
            _fact(bundle, "client"),
            _fact(bundle, "sector"),
            _fact(bundle, "offering"),
        ])
        generated_acronyms = set(re.findall(r"\b[A-ZÀ-ÖØ-Þ]{2,6}\b", generated_text))
        dangling_title = bool(re.search(r"\b(?:dans|de|du|des|la|le|à|au|aux)\s*$", mission_title, re.IGNORECASE))
        def compact_name(value: str) -> str:
            normalized = unicodedata.normalize("NFKD", value.casefold())
            normalized = "".join(character for character in normalized if not unicodedata.combining(character))
            return "".join(re.findall(r"[a-z0-9]", normalized))

        compact_client = compact_name(_fact(bundle, "client"))
        named_suffix = re.search(
            r"\bpour\s+(?:(?:le|la|les|un|une)\s+)?([A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ'’.-]+(?:\s+[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ'’.-]+)+)",
            mission_title,
        )
        unsupported_named_suffix = bool(
            named_suffix
            and compact_name(named_suffix.group(1)) not in compact_client
            and compact_client not in compact_name(named_suffix.group(1))
        )
        dash_suffix = re.search(
            r"\s[-–—]\s*([A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ'’.-]+(?:\s+[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ'’.-]+)*)$",
            mission_title,
        )
        unsupported_dash_suffix = bool(
            dash_suffix
            and compact_name(dash_suffix.group(1)) not in compact_client
            and compact_client not in compact_name(dash_suffix.group(1))
        )
        overlong_title = len(mission_title) > 80
        challenge_section_quality = not any(
            re.search(
                r"^(?:préparer|formaliser|appuyer|élaborer|organiser|cadrer|initialiser|diagnostiquer|"
                r"proposer|décliner|définir|identifier|mettre\s+en\s+place|réaliser|gérer|piloter|coacher|"
                r"former|produire|animer|exécuter|préparation|formalisation|appui|élaboration|organisation|cadrage|initialisation|"
                r"diagnostic|proposition|déclinaison|définition|mise\s+en\s+place|réalisation|gestion|"
                r"pilotage|coaching|formation|reporting|animation)\b",
                value,
                re.IGNORECASE,
            )
            for value in challenges
        )
        benefits_section_quality = not any(
            re.search(
                r"\b(?:via|par)\s+(?:(?:le|la|les|l['’])\s*)?(?:coaching|animation|formation|reporting|mise\s+en\s+place)\b",
                value,
                re.IGNORECASE,
            )
            for value in benefits
        )
        source_clauses = _source_activity_clauses(scope)

        def coverage_tokens(value: str) -> set[str]:
            normalized = unicodedata.normalize("NFKD", value.casefold())
            normalized = "".join(character for character in normalized if not unicodedata.combining(character))
            stop = {
                "accompagnement", "assistance", "projet", "projets", "mise", "place",
                "avec", "dans", "des", "les", "pour", "une", "aux", "ainsi", "que", "sur",
            }
            return set(re.findall(r"[a-z0-9]{3,}", normalized)) - stop

        meaningful_clauses = [coverage_tokens(value) for value in source_clauses if len(coverage_tokens(value)) >= 2]
        covered_clauses = sum(
            1
            for clause_tokens in meaningful_clauses
            if any(
                len(clause_tokens & coverage_tokens(value)) / len(clause_tokens) >= 0.20
                for value in realisations
            )
        )
        source_activity_coverage = (
            not rich_reference
            or not meaningful_clauses
            or covered_clauses / len(meaningful_clauses) >= 0.5
        )
        return {
            "mission_title": bool(mission_title),
            "mission_title_quality": (
                not unsupported_named_suffix
                and not unsupported_dash_suffix
                and not overlong_title
                and not dangling_title
            ),
            "language_ok": language_ok,
            "challenge_coverage": not rich_reference or not plan.challenge or len(challenges) >= 1,
            "realisations_coverage": (
                not rich_reference
                or not plan.realisations
                or len(realisations) >= 3
            ),
            "benefits_coverage": not rich_reference or not plan.benefits or len(benefits) >= 1,
            "key_terms_coverage": required_acronyms <= generated_acronyms,
            "grounding_ok": True,
            "duplicates_ok": len({value.casefold() for value in populated}) == len(populated),
            "challenge_section_quality": challenge_section_quality,
            "benefits_section_quality": benefits_section_quality,
            "source_activity_coverage": source_activity_coverage,
        }

    @staticmethod
    def _quality_repair_instruction(status: dict[str, bool]) -> str:
        language_repair = not status.get("language_ok", True)
        instructions: list[str] = []
        if language_repair:
            instructions.append(
                "Rewrite the complete presentation copy entirely in the requested language. Preserve exactly the "
                "same supported facts and the same mission_title, challenges, realisations and benefits structure. "
                "Do not add facts, entities or numbers. Do not remove important project information. Return only valid JSON."
            )
        else:
            instructions.append(
                "Preserve every item in accepted_grounded_copy_to_preserve. Repair only missing or failed content; do not rewrite passing bullets."
            )
        if not status.get("mission_title_quality", True):
            instructions.append(
                "Rewrite the mission title so it names the concrete project or deliverable; do not echo a truncated generic catalog phrase."
            )
        if not status.get("realisations_coverage", True):
            instructions.append(
                "The previous presentation copy omitted important information contained in the trusted source. Rewrite the reference slide. Preserve factual grounding but make the slide substantially more complete. Extract the important project work into Réalisations and produce meaningful Challenges and Bénéfices where supported. Do not summarize a rich mission into only one or two sentences."
            )
        if not status.get("source_activity_coverage", True):
            instructions.append(
                "The answer clearly ignored substantial source activities. Cover the omitted phases, workshops, procedures, deliverables, implementation, tests and support work; use native parent/subitem structure for activities belonging to one workstream."
            )
        if not status.get("challenge_coverage", True):
            instructions.append("Populate Challenges with the concrete problem or need addressed by the mission.")
        if not status.get("challenge_section_quality", True):
            instructions.append(
                "Rewrite Challenges as the underlying business, organizational or technology needs. Do not place performed activities such as coaching, animation, training or reporting in Challenges."
            )
        if not status.get("benefits_coverage", True):
            instructions.append(
                "Populate Bénéfices with explicit outcomes or conservative non-quantified operational value directly entailed by supported Réalisations."
            )
        if not status.get("benefits_section_quality", True):
            instructions.append(
                "Rewrite Bénéfices as conservative operational value directly entailed by the work. Do not repeat coaching, animation, training or reporting as if those activities were benefits."
            )
        if not status.get("key_terms_coverage", True):
            instructions.append(
                "Preserve the important acronyms that appear in the trusted mission scope, especially in the mission title or Réalisations. Do not expand them unless the exact expansion is supplied."
            )
        if not status.get("duplicates_ok", True):
            instructions.append("Remove duplicated bullets.")
        return " ".join(instructions)

    def _trusted_title_fallback(self, bundle) -> str:
        def compact_title(value: str) -> str:
            compact = sanitize_generation_text(value.strip(), maximum_characters=80)
            if len(compact) == 80 and " " in compact:
                compact = compact.rsplit(" ", 1)[0].rstrip(" ,;:-")
            compact = re.sub(
                r"\s+(?:dans|de|du|des|d['’]|la|le|l['’]|à|au|aux|et|pour)$",
                "",
                compact,
                flags=re.IGNORECASE,
            ).rstrip(" ,;:-")
            return compact

        trusted_title = _fact(bundle, "mission_title").strip()
        trusted_title_is_complete = not re.search(
            r"\b(?:dans|de|du|des|d['’]|la|le|l['’]|à|au|aux|et|pour)$",
            trusted_title,
            flags=re.IGNORECASE,
        )
        if trusted_title_is_complete and (
            len(trusted_title.split()) >= 3 or len(trusted_title) >= 20
        ):
            return compact_title(trusted_title)

        scope = self._trusted_scope(bundle)
        first = re.split(
            r"\s+(?=(?:ETAPE|ÉTAPE|PHASE)\s*\d*\b|(?:Préparation|Mise\s+en\s+place|"
            r"Gestion|Coaching|Formation|Définition|Reporting|Animation|Cadrage|Initialisation|"
            r"Diagnostic|Proposition|Déclinaison|Élaboration|Elaboration|Organisation)\b)",
            scope,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0] if scope else ""
        first = re.sub(r"\s+", " ", first).strip(" .:;-")
        mission_match = re.match(
            r"^accompagnement\s+et\s+(?:d['’])?assistance\b.*\bdans\s+(?:la|le|l['’])\s+(.+)$",
            first,
            flags=re.IGNORECASE,
        )
        if mission_match:
            first = mission_match.group(1).strip()
            first = re.sub(r"^refonte\s+de\s+son\s+", "Refonte de l’", first, flags=re.IGNORECASE)
        if first:
            first = first[:1].upper() + first[1:]
            return compact_title(first)
        return compact_title(trusted_title)

    def _merge_supported_detailed(
        self,
        earlier: ReferenceNarrative,
        later: ReferenceNarrative,
        plan: FieldSupportPlan,
    ) -> ReferenceNarrative:
        """Keep already-passing bullets while accepting independently repaired bullets."""
        left = earlier.detailed_presentation
        right = later.detailed_presentation
        if left is None:
            return later
        if right is None:
            return earlier
        challenges = self._unique_complete_items([
            *[item.text for item in left.challenges],
            *[item.text for item in right.challenges],
        ])[:3]
        benefits = self._unique_complete_items([
            *[item.text for item in left.benefits],
            *[item.text for item in right.benefits],
        ])[:3]
        merged: list[DetailedRealisationCopy] = []
        by_key: dict[str, DetailedRealisationCopy] = {}
        for source_item in [*left.realisations, *right.realisations]:
            key = unicodedata.normalize("NFKD", source_item.text.text.casefold())
            key = "".join(character for character in key if not unicodedata.combining(character))
            key = re.sub(r"\s+", " ", key).strip()
            if not key:
                continue
            if key in by_key:
                existing = by_key[key]
                existing.subitems = self._unique_complete_items([
                    *existing.subitems,
                    *[subitem.text for subitem in source_item.subitems],
                ])[:4]
                continue
            copy_item = DetailedRealisationCopy(
                text=source_item.text.text,
                subitems=[subitem.text for subitem in source_item.subitems],
            )
            by_key[key] = copy_item
            merged.append(copy_item)
        main_keys = set(by_key)
        for item in merged:
            filtered: list[str] = []
            for subitem in item.subitems:
                subkey = unicodedata.normalize("NFKD", subitem.casefold())
                subkey = "".join(character for character in subkey if not unicodedata.combining(character))
                subkey = re.sub(r"\s+", " ", subkey).strip()
                if subkey not in main_keys:
                    filtered.append(subitem)
            item.subitems = filtered
        copy = DetailedReferenceCopy(
            mission_title=right.mission_title.text or left.mission_title.text,
            challenges=challenges,
            realisations=merged[:6],
            benefits=benefits,
        )
        return self._reference_from_copy(copy, plan, "detailed_reference")

    def _recover_missing_source_activities(
        self,
        request: DirectPresentationRequest,
        source_result,
        bundle,
        plan: FieldSupportPlan,
        reference: ReferenceNarrative,
    ) -> ReferenceNarrative:
        """Recover only omitted verbatim trusted activities after the one model repair."""
        detailed = reference.detailed_presentation
        if detailed is None or _source_richness(bundle, plan) != "RICH":
            return reference
        items = [
            DetailedRealisationCopy(
                text=item.text.text,
                subitems=[subitem.text for subitem in item.subitems],
            )
            for item in detailed.realisations
        ]

        def tokens(value: str) -> set[str]:
            normalized = unicodedata.normalize("NFKD", value.casefold())
            normalized = "".join(character for character in normalized if not unicodedata.combining(character))
            stop = {"mise", "place", "avec", "dans", "pour", "des", "les", "une", "ainsi"}
            return set(re.findall(r"[a-z0-9]{3,}", normalized)) - stop

        existing_text = [value for item in items for value in [item.text, *item.subitems]]
        for raw_clause in _source_activity_clauses(self._trusted_scope(bundle)):
            clause = sanitize_generation_text(raw_clause, maximum_characters=220).strip(" -:;")
            clause_parts = [
                self._strip_dangling_tail(part.strip(" -:;"))
                for part in re.split(r"\s*;\s*", clause)
                if part.strip(" -:;")
            ]
            clause_tokens = tokens(clause)
            if not clause_parts or len(clause.split()) < 3 or not clause_tokens:
                continue
            if any(
                len(clause_tokens & tokens(value)) / len(clause_tokens) >= 0.25
                for value in existing_text
            ):
                continue
            candidate = DetailedRealisationCopy(
                text=clause_parts[0],
                subitems=clause_parts[1:5],
            )
            if not self._field_is_grounded(
                request, source_result, bundle, plan, "realisations", [candidate]
            ):
                continue
            if len(items) < 6:
                items.append(candidate)
                existing_text.extend([candidate.text, *candidate.subitems])
            elif sum(1 + len(item.subitems) for item in items) < 10:
                available_parents = [item for item in items if len(item.subitems) < 4]
                if available_parents:
                    parent = max(
                        available_parents,
                        key=lambda item: len(tokens(item.text) & clause_tokens),
                    )
                    additions = [candidate.text, *candidate.subitems]
                    parent.subitems.extend(additions[: 4 - len(parent.subitems)])
                    existing_text.extend(additions)
        copy = DetailedReferenceCopy(
            mission_title=detailed.mission_title.text,
            challenges=[item.text for item in detailed.challenges],
            realisations=items[:6],
            benefits=[item.text for item in detailed.benefits],
        )
        recovered = self._reference_from_copy(copy, plan, "detailed_reference")
        recovered.warnings = list(reference.warnings)
        return recovered

    def _recover_required_source_acronyms(
        self,
        request: DirectPresentationRequest,
        source_result,
        bundle,
        plan: FieldSupportPlan,
        reference: ReferenceNarrative,
    ) -> ReferenceNarrative:
        """Restore trusted acronym-bearing activities omitted by model synthesis."""

        detailed = reference.detailed_presentation
        if detailed is None:
            return reference
        scope = self._trusted_scope(bundle)
        required = {
            value
            for value in re.findall(r"\b[A-ZÀ-ÖØ-Þ]{2,6}\b", scope)
            if value not in {"ETAPE", "PHASE"}
        }
        generated = " ".join([
            detailed.mission_title.text,
            *[item.text for item in detailed.challenges],
            *[
                value
                for item in detailed.realisations
                for value in [item.text.text, *[subitem.text for subitem in item.subitems]]
            ],
            *[item.text for item in detailed.benefits],
            _fact(bundle, "client"),
            _fact(bundle, "sector"),
            _fact(bundle, "offering"),
        ])
        present = set(re.findall(r"\b[A-ZÀ-ÖØ-Þ]{2,6}\b", generated))
        missing = sorted(required - present)
        if not missing:
            return reference

        source_units = [
            sanitize_generation_text(value, maximum_characters=220).strip(" -:;")
            for value in re.split(r"\s*[•▪·;]\s*", scope)
            if value.strip()
        ]
        items = [
            DetailedRealisationCopy(
                text=item.text.text,
                subitems=[subitem.text for subitem in item.subitems],
            )
            for item in detailed.realisations
        ]
        for acronym in missing:
            clause = next(
                (
                    value
                    for value in source_units
                    if re.search(rf"\b{re.escape(acronym)}\b", value)
                    and len(value.split()) >= 3
                ),
                "",
            )
            if not clause:
                continue
            candidate = DetailedRealisationCopy(text=clause, subitems=[])
            if not self._field_is_grounded(
                request, source_result, bundle, plan, "realisations", [candidate]
            ):
                continue
            if len(items) < 6:
                items.append(candidate)
                continue
            parent = next((item for item in items if len(item.subitems) < 4), None)
            if parent is not None:
                parent.subitems.append(clause)

        copy = DetailedReferenceCopy(
            mission_title=detailed.mission_title.text,
            challenges=[item.text for item in detailed.challenges],
            realisations=items[:6],
            benefits=[item.text for item in detailed.benefits],
        )
        recovered = self._reference_from_copy(copy, plan, "detailed_reference")
        recovered.warnings = list(reference.warnings)
        return recovered

    def _recover_missing_supported_sections(
        self,
        bundle,
        plan: FieldSupportPlan,
        reference: ReferenceNarrative,
    ) -> ReferenceNarrative:
        """Create only a source-derived challenge after qwen's one repair.

        Benefits deliberately have no deterministic semantic fallback: their
        operational-value relationship must be produced by the model and pass
        the generic source-anchor validator.
        """
        detailed = reference.detailed_presentation
        if detailed is None:
            return reference
        challenges = [item.text for item in detailed.challenges]
        benefits = [item.text for item in detailed.benefits]
        if not challenges and plan.challenge:
            title = detailed.mission_title.text.rstrip(" .")
            if title:
                need = title[:1].lower() + title[1:]
                need = re.sub(
                    r"^mise en place (du|de la|des|d['’]un|d['’]une)\s+",
                    lambda match: f"disposer {match.group(1)} ",
                    need,
                    flags=re.IGNORECASE,
                )
                connector = "d’" if need[0].lower() in "aeiouyhàâäéèêëîïôöùûü" else "de "
                challenges = [f"Besoin {connector}{need}." ]

        copy = DetailedReferenceCopy(
            mission_title=detailed.mission_title.text,
            challenges=challenges[:3],
            realisations=[
                DetailedRealisationCopy(
                    text=item.text.text,
                    subitems=[subitem.text for subitem in item.subitems],
                )
                for item in detailed.realisations
            ],
            benefits=benefits[:3],
        )
        recovered = self._reference_from_copy(copy, plan, "detailed_reference")
        recovered.warnings = list(reference.warnings)
        return recovered

    @staticmethod
    def _provider_stats_start(provider: NarrativeProvider) -> int:
        stats = getattr(provider, "generation_stats", None)
        return len(stats) if isinstance(stats, list) else 0

    def _generate_one(self, request, source_result, bundle, plan) -> tuple[ReferenceNarrative, dict[str, Any]]:
        model_type = OrangeReferenceCopy if request.template_id == "orange_bank_compact" else DetailedReferenceCopy
        prompt_builder = build_orange_prompt if request.template_id == "orange_bank_compact" else build_detailed_prompt
        started = time.perf_counter()
        stats_start = self._provider_stats_start(self.provider)
        last_codes: list[str] = []
        prompt_hashes: list[str] = []
        prompt_characters = 0
        last_error = ""
        last_copy = None
        last_safe = None
        repair_instruction = None
        accepted_copy: dict[str, Any] | None = None
        repair_fields: list[str] | None = None
        language_repair_requested = False
        for attempt in range(2):
            prompt_kwargs: dict[str, Any] = {
                "repair": attempt == 1,
                "layout_budget": self.fit_profile.initial_prompt_budget(request.template_id),
            }
            if request.template_id == "detailed_reference":
                prompt_kwargs["repair_instruction"] = repair_instruction
                prompt_kwargs["accepted_copy"] = accepted_copy
                prompt_kwargs["repair_fields"] = repair_fields
            prompt = prompt_builder(
                request,
                bundle,
                plan,
                source_result.support_index,
                **prompt_kwargs,
            )
            prompt_hashes.append(prompt.prompt_sha256)
            prompt_characters += sum(len(message["content"]) for message in prompt.messages)
            try:
                raw = self.provider.generate(prompt.messages, prompt.response_schema)
                copy = model_type.model_validate_json(raw)
                last_copy = copy
                if request.template_id == "orange_bank_compact":
                    activity_support = [
                        *plan.realisations,
                        *plan.devoteam_contribution,
                        *plan.short_description,
                    ]
                    if activity_support and not 3 <= len(copy.activities) <= 6:
                        raise ValueError("Orange copy requires 3-6 activities when eligible support exists")
                    if not activity_support and copy.activities:
                        raise ValueError("Orange activities are unsupported for this reference")
                narrative = self._reference_from_copy(copy, plan, request.template_id)
                if request.template_id == "detailed_reference":
                    narrative = self._safe_supported_portions(request, source_result, bundle, plan, copy)
                    if attempt == 1 and last_safe is not None and not language_repair_requested:
                        narrative = self._merge_supported_detailed(last_safe, narrative, plan)
                    preliminary_status = self._detailed_quality_status(request, bundle, plan, narrative)
                    if not preliminary_status.get("mission_title_quality", True):
                        trusted_title = self._trusted_title_fallback(bundle)
                        title_candidate = self._replace_field(
                            narrative,
                            plan,
                            request,
                            "headline",
                            [trusted_title],
                        )
                        narrative = title_candidate
                    last_safe = narrative
                validation = self._validate_one(source_result, bundle, plan, narrative)
                blocking = self._blocking(validation)
                last_codes = [warning.code for warning in blocking]
                quality_status = (
                    self._detailed_quality_status(request, bundle, plan, narrative)
                    if request.template_id == "detailed_reference"
                    else {}
                )
                quality_ok = not quality_status or all(quality_status.values())
                if not blocking and quality_ok:
                    elapsed = time.perf_counter() - started
                    LOGGER.info(
                        "presentation_copy_unit: template=%s reference_id=%s status=completed attempt=%d "
                        "prompt_chars=%d total=%.2fs",
                        request.template_id, bundle.reference_id, attempt + 1, prompt_characters, elapsed,
                    )
                    return narrative, {
                        "reference_id": bundle.reference_id,
                        "prompt_version": prompt.prompt_version,
                        "prompt_sha256": hashlib.sha256("".join(prompt_hashes).encode("ascii")).hexdigest(),
                        "prompt_characters": prompt_characters,
                        "attempts": attempt + 1,
                        "fallback_used": False,
                        "validation_codes": [],
                        "quality_gate": quality_status,
                        "seconds": round(elapsed, 3),
                    }
                if blocking:
                    last_error = "automatic grounding validation rejected generated copy"
                else:
                    last_error = "LOW_QUALITY_PRESENTATION_COPY"
                    repair_instruction = self._quality_repair_instruction(quality_status)
                    repair_fields = []
                    if not quality_status.get("mission_title_quality", True):
                        repair_fields.append("mission_title")
                    if not quality_status.get("challenge_coverage", True) or not quality_status.get("challenge_section_quality", True):
                        repair_fields.append("challenges")
                    if (
                        not quality_status.get("realisations_coverage", True)
                        or not quality_status.get("source_activity_coverage", True)
                        or not quality_status.get("key_terms_coverage", True)
                        or not quality_status.get("duplicates_ok", True)
                    ):
                        repair_fields.append("realisations")
                    if not quality_status.get("benefits_coverage", True) or not quality_status.get("benefits_section_quality", True):
                        repair_fields.append("benefits")
                    if not quality_status.get("language_ok", True):
                        language_repair_requested = True
                        repair_fields = ["mission_title", "challenges", "realisations", "benefits"]
                    if narrative.detailed_presentation is not None:
                        accepted_copy = {
                            "mission_title": narrative.detailed_presentation.mission_title.text,
                            "challenges": [item.text for item in narrative.detailed_presentation.challenges],
                            "realisations": [
                                {
                                    "text": item.text.text,
                                    "subitems": [subitem.text for subitem in item.subitems],
                                }
                                for item in narrative.detailed_presentation.realisations
                            ],
                            "benefits": [item.text for item in narrative.detailed_presentation.benefits],
                        }
            except (ValidationError, ValueError) as exc:
                last_error = str(exc)
            except Exception as exc:  # isolate one reference and preserve the rest of the deck
                last_error = str(exc)
                LOGGER.warning("presentation_copy reference %s attempt %d failed: %s", bundle.reference_id, attempt + 1, exc)

        if last_safe is not None:
            safe = last_safe
        elif last_copy is not None:
            safe = self._safe_supported_portions(request, source_result, bundle, plan, last_copy)
        else:
            safe = self._safe_reference(bundle, plan)
        if request.template_id == "detailed_reference":
            status = self._detailed_quality_status(request, bundle, plan, safe)
            if not status.get("mission_title_quality", True):
                trusted_title = self._trusted_title_fallback(bundle)
                candidate = self._replace_field(
                    safe,
                    plan,
                    request,
                    "headline",
                    [trusted_title],
                )
                safe = candidate
            safe = self._recover_missing_source_activities(
                request,
                source_result,
                bundle,
                plan,
                safe,
            )
            safe = self._recover_required_source_acronyms(
                request,
                source_result,
                bundle,
                plan,
                safe,
            )
            safe = self._recover_missing_supported_sections(bundle, plan, safe)
        elapsed = time.perf_counter() - started
        stats = getattr(self.provider, "generation_stats", None)
        model_records = stats[stats_start:] if isinstance(stats, list) else []
        LOGGER.warning(
            "presentation_copy_unit: template=%s reference_id=%s status=fallback prompt_chars=%d total=%.2fs",
            request.template_id, bundle.reference_id, prompt_characters, elapsed,
        )
        return safe, {
            "reference_id": bundle.reference_id,
            "prompt_version": ORANGE_PROMPT_VERSION if request.template_id == "orange_bank_compact" else DETAILED_PROMPT_VERSION,
            "prompt_sha256": hashlib.sha256("".join(prompt_hashes).encode("ascii")).hexdigest() if prompt_hashes else "",
            "prompt_characters": prompt_characters,
            "attempts": 2,
            "fallback_used": True,
            "safe_generated_portions_retained": bool(
                safe.realisations or safe.challenge.text or safe.benefits
            ),
            "validation_codes": last_codes,
            "quality_gate": (
                self._detailed_quality_status(request, bundle, plan, safe)
                if request.template_id == "detailed_reference"
                else {}
            ),
            "failure": last_error,
            "seconds": round(elapsed, 3),
            "model_response_count": len(model_records),
        }

    @staticmethod
    def _field_values(reference: ReferenceNarrative, field: str) -> list[Any]:
        detailed = reference.detailed_presentation
        if detailed is not None:
            if field == "headline":
                return [detailed.mission_title.text] if detailed.mission_title.text.strip() else []
            if field == "challenge":
                return [item.text for item in detailed.challenges if item.text.strip()]
            if field == "realisations":
                return [
                    DetailedRealisationCopy(
                        text=item.text.text,
                        subitems=[subitem.text for subitem in item.subitems],
                    )
                    for item in detailed.realisations
                    if item.text.text.strip()
                ]
            if field == "benefits":
                return [item.text for item in detailed.benefits if item.text.strip()]
        if field == "headline":
            return [reference.headline.text] if reference.headline.text.strip() else []
        if field == "challenge":
            return [item.strip() for item in reference.challenge.text.splitlines() if item.strip()]
        if field == "realisations":
            return [item.text for item in reference.realisations if item.text.strip()]
        if field == "benefits":
            return [item.text for item in reference.benefits if item.text.strip()]
        if field == "compact_services":
            return [item.text for item in reference.realisations if item.text.strip()]
        raise ValueError(f"Unknown presentation fit field: {field}")

    @staticmethod
    def _field_support_ids(plan: FieldSupportPlan, field: str, template_id: str) -> list[str]:
        if field == "headline":
            return list(plan.headline)
        if field == "challenge":
            return list(plan.challenge)
        if field == "realisations":
            return list(plan.realisations)
        if field == "benefits":
            return list(plan.benefits)
        if field == "compact_services" and template_id == "orange_bank_compact":
            return list(dict.fromkeys([
                *plan.realisations,
                *plan.devoteam_contribution,
                *plan.short_description,
            ]))
        return []

    def _copy_with_only_field(
        self,
        request: DirectPresentationRequest,
        field: str,
        values: list[Any],
    ) -> OrangeReferenceCopy | DetailedReferenceCopy:
        if request.template_id == "orange_bank_compact":
            if field == "headline":
                return OrangeReferenceCopy(display_title=values[0] if values else "")
            return OrangeReferenceCopy(activities=values)
        if field == "headline":
            return DetailedReferenceCopy(mission_title=str(values[0]) if values else "")
        if field == "challenge":
            return DetailedReferenceCopy(challenges=values)
        return DetailedReferenceCopy(**{field: values})

    def _field_is_grounded(
        self,
        request: DirectPresentationRequest,
        source_result,
        bundle,
        plan: FieldSupportPlan,
        field: str,
        values: list[Any],
    ) -> bool:
        return self._copy_is_grounded(
            request,
            source_result,
            bundle,
            plan,
            self._copy_with_only_field(request, field, values),
        )

    @staticmethod
    def _repair_contract(template_id: str, field: str):
        contracts = {
            ("detailed_reference", "headline"): (MissionTitleRepair, "mission_title"),
            ("detailed_reference", "challenge"): (ChallengeRepair, "challenge"),
            ("detailed_reference", "realisations"): (RealisationsRepair, "realisations"),
            ("detailed_reference", "benefits"): (BenefitsRepair, "benefits"),
            ("orange_bank_compact", "headline"): (OrangeTitleRepair, "display_title"),
            ("orange_bank_compact", "compact_services"): (OrangeActivitiesRepair, "activities"),
        }
        return contracts[(template_id, field)]

    def _measure_field(
        self,
        request: DirectPresentationRequest,
        field: str,
        values: list[Any],
        reference_index: int,
    ):
        budget = self.fit_profile.budgets[request.template_id][field]
        rendered_values = [
            rendered
            for value in values
            for rendered in (
                [value.text, *[f"○ {subitem}" for subitem in value.subitems]]
                if isinstance(value, DetailedRealisationCopy)
                else [str(value)]
            )
        ]
        if request.template_id == "orange_bank_compact" and field == "headline" and values:
            rendered_values = [f"{reference_index + 1}. {values[0]}"]
        heading = self.fit_profile.heading(request.template_id, field, request.target_language)
        return budget.measure(heading, rendered_values)

    def _replace_field(
        self,
        reference: ReferenceNarrative,
        plan: FieldSupportPlan,
        request: DirectPresentationRequest,
        field: str,
        values: list[Any],
    ) -> ReferenceNarrative:
        if request.template_id == "detailed_reference":
            current = reference.detailed_presentation
            if current is None:
                raise RuntimeError("Detailed reference copy is missing its presentation-specific schema")
            copy = DetailedReferenceCopy(
                mission_title=current.mission_title.text,
                challenges=[item.text for item in current.challenges],
                realisations=[
                    DetailedRealisationCopy(
                        text=item.text.text,
                        subitems=[subitem.text for subitem in item.subitems],
                    )
                    for item in current.realisations
                ],
                benefits=[item.text for item in current.benefits],
            )
            key = {
                "headline": "mission_title",
                "challenge": "challenges",
                "realisations": "realisations",
                "benefits": "benefits",
            }[field]
            replacement: Any = values[0] if field == "headline" and values else "" if field == "headline" else values
            copy = copy.model_copy(update={key: replacement})
            rebuilt = self._reference_from_copy(copy, plan, request.template_id)
            rebuilt.warnings = list(reference.warnings)
            return rebuilt
        updated = reference.model_copy(deep=True)
        support_ids = self._field_support_ids(plan, field, request.template_id)
        if field == "headline":
            updated.headline = self.narrative_service._supported_text(values[0] if values else "", support_ids)
        elif field == "challenge":
            updated.challenge = self.narrative_service._supported_text("\n".join(values), support_ids)
        elif field in {"realisations", "compact_services"}:
            updated.realisations = [self.narrative_service._supported_text(item, support_ids) for item in values]
        elif field == "benefits":
            updated.benefits = [self.narrative_service._supported_text(item, support_ids) for item in values]
        return updated

    def _fit_repair_prompt(
        self,
        request: DirectPresentationRequest,
        bundle,
        plan: FieldSupportPlan,
        source_result,
        field: str,
        values: list[Any],
        budget: TemplateFieldBudget,
        target_lines: int,
        attempt: int,
    ) -> tuple[PromptPackage, type[BaseModel], str]:
        model_type, response_key = self._repair_contract(request.template_id, field)
        support_ids = self._field_support_ids(plan, field, request.template_id)
        schema = model_type.model_json_schema()
        required_acronyms = (
            sorted(self._acronyms_in_values(values) & self._source_acronyms(bundle))
            if request.template_id == "detailed_reference" and field == "realisations"
            else []
        )
        payload = {
            "task": "POWERPOINT_FIELD_FIT_REPAIR",
            "template_id": request.template_id,
            "field": response_key,
            "current_content": (
                values[0]
                if field == "headline" and values
                else [value.model_dump(mode="json") if isinstance(value, BaseModel) else value for value in values]
            ),
            "eligible_trusted_evidence": _safe_records(support_ids, source_result.support_index)
            or "NO ELIGIBLE SUPPORT",
            "target_language": request.target_language,
            "trusted_source_activity_clauses": (
                _source_activity_clauses(self._trusted_scope(bundle))
                if request.template_id == "detailed_reference" and field == "realisations"
                else []
            ),
            "required_source_acronyms_to_preserve": required_acronyms,
            "exact_template_budget": {
                "maximum_rendered_lines": target_lines,
                "minimum_font_pt": budget.minimum_pt,
                "maximum_items": budget.maximum_items,
                "text_box_width_inches": round(budget.width_inches, 4),
                "text_box_height_inches": round(budget.height_inches, 4),
            },
            "instruction": (
                "Repair attempt 1: compress only this overflowing field while preserving its supported meaning. For Réalisations, retain the parent/subitem hierarchy, merge only closely related activities, and keep at least three meaningful activities for a rich source."
                if attempt == 1
                else "Repair attempt 2: condense this field into direct consulting phrases. Preserve important source activities and the parent/subitem hierarchy; remove wording redundancy rather than factual content."
            ) + (
                " Preserve every acronym listed in required_source_acronyms_to_preserve exactly."
                if required_acronyms else ""
            ),
            "required_output_schema": schema,
        }
        package = _package(
            FIT_REPAIR_SYSTEM_PROMPT,
            payload,
            schema,
            f"POWERPOINT_FIELD_FIT_REPAIR-{field}-v1",
        )
        return package, model_type, response_key

    @staticmethod
    def _semantic_tokens(value: str) -> set[str]:
        normalized = unicodedata.normalize("NFKD", value.casefold())
        normalized = "".join(character for character in normalized if not unicodedata.combining(character))
        stop = {
            "avec", "dans", "des", "les", "pour", "une", "aux", "ainsi", "que",
            "par", "sur", "son", "ses", "leur", "leurs", "cette", "tout", "tous",
        }
        return {
            token[:-1] if token.endswith("s") and len(token) > 4 else token
            for token in re.findall(r"[a-z0-9]{3,}", normalized)
            if token not in stop
        }

    @staticmethod
    def _source_acronyms(bundle) -> set[str]:
        return {
            value
            for value in re.findall(
                r"\b[A-ZÀ-ÖØ-Þ]{2,6}\b",
                PresentationCopyService._trusted_scope(bundle),
            )
            if value not in {"ETAPE", "PHASE"}
        }

    @staticmethod
    def _acronyms_in_values(values: list[Any]) -> set[str]:
        text = " ".join(
            rendered
            for value in values
            for rendered in (
                [value.text, *value.subitems]
                if isinstance(value, DetailedRealisationCopy)
                else [str(value)]
            )
        )
        return set(re.findall(r"\b[A-ZÀ-ÖØ-Þ]{2,6}\b", text))

    @staticmethod
    def _unique_complete_items(values: list[str]) -> list[str]:
        unique: list[str] = []
        seen: set[str] = set()

        def semantic_tokens(value: str) -> set[str]:
            normalized = unicodedata.normalize("NFKD", value.casefold())
            normalized = "".join(character for character in normalized if not unicodedata.combining(character))
            stop = {
                "avec", "dans", "des", "les", "pour", "une", "aux", "ainsi", "que",
                "par", "sur", "son", "ses", "leur", "leurs", "cette", "tout", "tous",
            }
            return {
                token[:-1] if token.endswith("s") and len(token) > 4 else token
                for token in re.findall(r"[a-z0-9]{3,}", normalized)
                if token not in stop
            }

        for value in values:
            clean = value.strip()
            key = re.sub(r"\s+", " ", clean).casefold()
            candidate_tokens = semantic_tokens(clean)
            semantic_duplicate = any(
                candidate_tokens
                and existing_tokens
                and (
                    len(candidate_tokens & existing_tokens) / len(candidate_tokens | existing_tokens) >= 0.5
                    or len(candidate_tokens & existing_tokens) / min(len(candidate_tokens), len(existing_tokens)) >= 0.75
                )
                for existing_tokens in (semantic_tokens(existing) for existing in unique)
            )
            if clean and key not in seen and not semantic_duplicate:
                unique.append(clean)
                seen.add(key)
        return unique

    def _deterministic_fit_fallback(
        self,
        request: DirectPresentationRequest,
        source_result,
        bundle,
        plan: FieldSupportPlan,
        field: str,
        original_values: list[Any],
        reference_index: int,
    ) -> list[Any]:
        if field == "realisations" and any(isinstance(value, DetailedRealisationCopy) for value in original_values):
            values = [value.model_copy(deep=True) for value in original_values]
            required_acronyms = self._acronyms_in_values(values) & self._source_acronyms(bundle)
            def activity_count() -> int:
                return sum(1 + len(value.subitems) for value in values)
            while values and not self._measure_field(request, field, values, reference_index).fits:
                changed = False
                if activity_count() > 3:
                    for parent_index in range(len(values) - 1, -1, -1):
                        parent = values[parent_index]
                        for child_index in range(len(parent.subitems) - 1, -1, -1):
                            trial = [value.model_copy(deep=True) for value in values]
                            trial[parent_index].subitems.pop(child_index)
                            if required_acronyms <= self._acronyms_in_values(trial):
                                values = trial
                                changed = True
                                break
                        if changed:
                            break
                if not changed and len(values) > 1 and activity_count() > 3:
                    for item_index in range(len(values) - 1, -1, -1):
                        trial = [value.model_copy(deep=True) for value in values]
                        trial.pop(item_index)
                        if required_acronyms <= self._acronyms_in_values(trial):
                            values = trial
                            changed = True
                            break
                if not changed:
                    break
            if self._field_is_grounded(request, source_result, bundle, plan, field, values):
                return values
            return []
        values = self._unique_complete_items(original_values)
        if field == "headline":
            trusted = _fact(bundle, "mission_title").strip()
            candidates = self._unique_complete_items([*values, trusted])
            for candidate in sorted(candidates, key=len):
                unit = [candidate]
                if (
                    self._measure_field(request, field, unit, reference_index).fits
                    and self._field_is_grounded(request, source_result, bundle, plan, field, unit)
                ):
                    return unit
            return values

        while values and not self._measure_field(request, field, values, reference_index).fits:
            values.pop()
        if self._field_is_grounded(request, source_result, bundle, plan, field, values):
            return values
        return []

    def _deduplicate_detailed_reference(
        self,
        reference: ReferenceNarrative,
        plan: FieldSupportPlan,
    ) -> ReferenceNarrative:
        detailed = reference.detailed_presentation
        if detailed is None:
            return reference
        unique: list[DetailedRealisationCopy] = []
        for source_item in detailed.realisations:
            candidate = DetailedRealisationCopy(
                text=source_item.text.text,
                subitems=[
                    subitem.text
                    for subitem in source_item.subitems
                    if self._is_atomic_bullet(subitem.text)
                ],
            )
            tokens = self._semantic_tokens(candidate.text)
            duplicate = next(
                (
                    item
                    for item in unique
                    if tokens
                    and self._semantic_tokens(item.text)
                    and len(tokens & self._semantic_tokens(item.text))
                    / min(len(tokens), len(self._semantic_tokens(item.text)))
                    >= 0.65
                ),
                None,
            )
            if duplicate is None:
                unique.append(candidate)
            else:
                # Semantic deduplication must not erase a trusted acronym that
                # carries source meaning (for example a named procedure or
                # operating plan). Preserve it compactly on the retained item.
                missing_acronyms = sorted(
                    self._acronyms_in_values([candidate])
                    - self._acronyms_in_values([duplicate])
                )
                if missing_acronyms:
                    base = duplicate.text.rstrip(" .;:-")
                    duplicate.text = sanitize_generation_text(
                        f"{base} — {' / '.join(missing_acronyms)}.",
                        maximum_characters=220,
                    )
                duplicate.subitems = self._unique_complete_items([
                    *duplicate.subitems,
                    *candidate.subitems,
                ])[:4]
        copy = DetailedReferenceCopy(
            mission_title=detailed.mission_title.text,
            challenges=[item.text for item in detailed.challenges],
            realisations=unique[:6],
            benefits=[item.text for item in detailed.benefits],
        )
        deduplicated = self._reference_from_copy(copy, plan, "detailed_reference")
        deduplicated.warnings = list(reference.warnings)
        return deduplicated

    def _fit_and_repair_one(
        self,
        request: DirectPresentationRequest,
        source_result,
        bundle,
        plan: FieldSupportPlan,
        reference: ReferenceNarrative,
        reference_index: int,
    ) -> tuple[ReferenceNarrative, list[dict[str, Any]]]:
        fields = list(self.fit_profile.budgets[request.template_id])
        updated = reference
        records: list[dict[str, Any]] = []
        for field in fields:
            values = self._field_values(updated, field)
            measurement = self._measure_field(request, field, values, reference_index)
            if measurement.fits:
                continue
            budget = self.fit_profile.budgets[request.template_id][field]
            field_record: dict[str, Any] = {
                "reference_id": plan.reference_id,
                "field": field,
                "initial_required_lines": measurement.required_lines,
                "available_lines": measurement.available_lines,
                "minimum_font_pt": budget.minimum_pt,
                "attempts": [],
                "fallback_used": False,
            }
            original_values = list(values)
            required_fit_acronyms = (
                self._acronyms_in_values(original_values) & self._source_acronyms(bundle)
                if request.template_id == "detailed_reference" and field == "realisations"
                else set()
            )
            repaired = False
            for attempt in (1, 2):
                target_lines = max(1, budget.absolute_lines - (attempt - 1))
                package, model_type, response_key = self._fit_repair_prompt(
                    request,
                    bundle,
                    plan,
                    source_result,
                    field,
                    values,
                    budget,
                    target_lines,
                    attempt,
                )
                attempt_record: dict[str, Any] = {
                    "attempt": attempt,
                    "target_lines": target_lines,
                    "prompt_sha256": package.prompt_sha256,
                }
                try:
                    parsed = model_type.model_validate_json(
                        self.provider.generate(package.messages, package.response_schema)
                    )
                    raw_value = getattr(parsed, response_key)
                    candidate = [raw_value] if isinstance(raw_value, str) and raw_value.strip() else list(raw_value)
                    grounded = self._field_is_grounded(
                        request, source_result, bundle, plan, field, candidate
                    )
                    acronyms_preserved = required_fit_acronyms <= self._acronyms_in_values(candidate)
                    grounded = grounded and acronyms_preserved
                    fit = self._measure_field(request, field, candidate, reference_index)
                    attempt_record.update({
                        "grounding": "PASS" if grounded else "FAIL",
                        "required_acronyms": sorted(required_fit_acronyms),
                        "acronym_preservation": "PASS" if acronyms_preserved else "FAIL",
                        "required_lines": fit.required_lines,
                        "fit": "PASS" if fit.fits else "FAIL",
                    })
                    if grounded and fit.fits:
                        updated = self._replace_field(updated, plan, request, field, candidate)
                        repaired = True
                        values = candidate
                        field_record["attempts"].append(attempt_record)
                        break
                    values = candidate if grounded else values
                except (ValidationError, ValueError) as exc:
                    attempt_record.update({"grounding": "FAIL", "fit": "NOT_TESTED", "error": str(exc)})
                except Exception as exc:
                    attempt_record.update({"grounding": "FAIL", "fit": "NOT_TESTED", "error": str(exc)})
                    LOGGER.warning(
                        "presentation_fit reference %s field %s attempt %d failed: %s",
                        plan.reference_id,
                        field,
                        attempt,
                        exc,
                    )
                field_record["attempts"].append(attempt_record)

            if not repaired:
                fallback = self._deterministic_fit_fallback(
                    request,
                    source_result,
                    bundle,
                    plan,
                    field,
                    original_values,
                    reference_index,
                )
                final_measurement = self._measure_field(request, field, fallback, reference_index)
                if not final_measurement.fits:
                    raise RuntimeError(f"No presentation-safe fallback could fit {field}")
                updated = self._replace_field(updated, plan, request, field, fallback)
                field_record["fallback_used"] = True
                field_record["final_required_lines"] = final_measurement.required_lines
            else:
                final_measurement = self._measure_field(request, field, values, reference_index)
                field_record["final_required_lines"] = final_measurement.required_lines
            field_record["status"] = "FIT"
            records.append(field_record)
        if request.template_id == "detailed_reference":
            updated = self._deduplicate_detailed_reference(updated, plan)
            post_dedup_quality = self._detailed_quality_status(
                request, bundle, plan, updated
            )
            if not (
                post_dedup_quality.get("realisations_coverage", True)
                and post_dedup_quality.get("source_activity_coverage", True)
                and post_dedup_quality.get("key_terms_coverage", True)
            ):
                updated = self._recover_missing_source_activities(
                    request, source_result, bundle, plan, updated
                )
                updated = self._recover_required_source_acronyms(
                    request, source_result, bundle, plan, updated
                )
                recovered_values = self._field_values(updated, "realisations")
                recovered_fit = self._measure_field(
                    request, "realisations", recovered_values, reference_index
                )
                if not recovered_fit.fits:
                    recovered_values = self._deterministic_fit_fallback(
                        request,
                        source_result,
                        bundle,
                        plan,
                        "realisations",
                        recovered_values,
                        reference_index,
                    )
                    updated = self._replace_field(
                        updated, plan, request, "realisations", recovered_values
                    )
        return updated, records

    def generate(
        self,
        request: DirectPresentationRequest,
        on_progress: ProgressCallback | None = None,
    ) -> PresentationCopyResult:
        total_started = time.perf_counter()
        source_result, field_plans, _capsules, section_plan = self.narrative_service._review_context(
            request.selected_reference_ids
        )
        if request.template_id == "orange_bank_compact":
            field_plans = [
                plan.model_copy(update={
                    "realisations": list(dict.fromkeys([
                        *plan.realisations,
                        *plan.devoteam_contribution,
                        *plan.short_description,
                    ]))
                })
                for plan in field_plans
            ]
        else:
            field_plans = [
                build_detailed_presentation_support_plan(bundle, source_result.support_index, plan)
                for bundle, plan in zip(source_result.bundles, field_plans, strict=True)
            ]
        references: list[ReferenceNarrative] = []
        records: list[dict[str, Any]] = []
        fit_seconds = 0.0
        fit_started_emitted = False
        total = len(field_plans)
        for index, (bundle, plan) in enumerate(zip(source_result.bundles, field_plans, strict=True)):
            client = _fact(bundle, "client") or "Client"
            if on_progress:
                on_progress({
                    "event": "reference_started",
                    "index": index,
                    "reference_id": plan.reference_id,
                    "message": f"Writing reference {index + 1} of {total} — {client}",
                })
            narrative, record = self._generate_one(request, source_result, bundle, plan)
            if on_progress and not fit_started_emitted:
                on_progress({"event": "fit_started", "message": "Optimizing slide content"})
                fit_started_emitted = True
            fit_started = time.perf_counter()
            fitted, fit_records = self._fit_and_repair_one(
                request,
                source_result,
                bundle,
                plan,
                narrative,
                index,
            )
            fit_seconds += time.perf_counter() - fit_started
            if request.template_id == "detailed_reference":
                quality_status = self._detailed_quality_status(request, bundle, plan, fitted)
                record["quality_gate"] = quality_status
                blocking_quality_failures = [
                    key
                    for key, passed in quality_status.items()
                    if not passed and key != "language_ok"
                ]
                if blocking_quality_failures:
                    detailed_title = (
                        fitted.detailed_presentation.mission_title.text
                        if fitted.detailed_presentation is not None
                        else ""
                    )
                    raise RuntimeError(
                        f"LOW_QUALITY_PRESENTATION_COPY reference_id={plan.reference_id} "
                        f"failed={','.join(blocking_quality_failures)} title={detailed_title!r}"
                    )
                if not quality_status.get("language_ok", True):
                    LOGGER.warning(
                        "presentation_language_gate: reference_id=%s status=CLEAR_MISMATCH "
                        "repair_attempted=true continuing_without_hard_failure",
                        plan.reference_id,
                    )
            record["template_fit"] = {
                "status": "PASS",
                "repairs": fit_records,
                "repair_count": len(fit_records),
            }
            record["quality_gate"]["fit_ok"] = True
            references.append(fitted)
            records.append(record)
            if on_progress:
                on_progress({
                    "event": "reference_completed",
                    "index": index,
                    "reference_id": plan.reference_id,
                    "fallback_used": record["fallback_used"],
                    "message": f"Reference {index + 1} of {total} ready",
                })

        narrative = ReferenceSectionNarrative(
            section_intro=self._empty_text(),
            overall_storyline=self._empty_text(),
            why_these_references=self._empty_text(),
            references=references,
        )
        review = self.narrative_service._review_response(
            source_result,
            field_plans,
            section_plan,
            narrative,
            allow_catalog_completion_detail=request.template_id == "detailed_reference",
        )
        if request.template_id == "detailed_reference":
            # Detailed benefits have already passed the presentation-specific
            # conservative-entailment validator above. The generic Narrative
            # Studio validator cannot model this allowed non-literal value path.
            filtered_warnings = [
                warning
                for warning in review.warnings
                if not (
                    warning.field_path
                    and ".benefits[" in warning.field_path
                    and warning.code in {
                        "UNSUPPORTED_BENEFIT",
                        "PROPOSAL_SCOPE_AS_COMPLETED",
                        "UNSUPPORTED_COMPLETION_LANGUAGE",
                    }
                )
            ]
            review.warnings = filtered_warnings
            has_blocking = any(
                warning.severity == ValidationSeverity.BLOCKING or warning.blocking
                for warning in filtered_warnings
            )
            review.validation = NarrativeValidationResult(
                valid=not has_blocking,
                export_blocked=has_blocking,
                export_eligible=not has_blocking,
                warnings=filtered_warnings,
            )
        blocking = [
            warning for warning in self._blocking(review.validation)
            if warning.code != "UNSUPPORTED_COMPLETION_LANGUAGE"
        ]
        if blocking:
            blocked_ids = {warning.reference_id for warning in blocking if warning.reference_id}
            for index, bundle in enumerate(source_result.bundles):
                if bundle.reference_id in blocked_ids:
                    references[index] = self._safe_reference(bundle, field_plans[index])
                    records[index]["fallback_used"] = True
                    records[index]["validation_codes"] = [
                        warning.code for warning in blocking if warning.reference_id == bundle.reference_id
                    ]
            narrative.references = references
            review = self.narrative_service._review_response(
                source_result,
                field_plans,
                section_plan,
                narrative,
                allow_catalog_completion_detail=request.template_id == "detailed_reference",
            )
            if request.template_id == "detailed_reference":
                for bundle, plan, reference in zip(
                    source_result.bundles,
                    field_plans,
                    references,
                    strict=True,
                ):
                    if not all(self._detailed_quality_status(request, bundle, plan, reference).values()):
                        raise RuntimeError("LOW_QUALITY_PRESENTATION_COPY")

        validation_seconds = (
            time.perf_counter()
            - total_started
            - fit_seconds
            - sum(float(record["seconds"]) for record in records)
        )
        return PresentationCopyResult(
            review=review,
            generation_records=records,
            timings={
                "fit_seconds": round(fit_seconds, 3),
                "validation_seconds": round(max(validation_seconds, 0.0), 3),
                "total_copy_seconds": round(time.perf_counter() - total_started, 3),
            },
        )
