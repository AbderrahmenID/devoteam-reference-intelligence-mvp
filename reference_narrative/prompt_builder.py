from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from .content_sanitizer import sanitize_generation_text
from .field_policy import build_field_support_plan, field_material_records
from .schemas import (
    FieldSupportPlan,
    NarrativeGenerationRequest,
    ReferenceNarrativeDraft,
    ReferenceSourceBundle,
    SafeReferenceCapsule,
    SectionNarrativeDraft,
    SourceSupportRecord,
)


PROMPT_VERSION = "reference-narrative-phase2.1-prose-v1"

REFERENCE_SYSTEM_PROMPT = """You write proposal-ready prose for one selected Devoteam reference.

The backend owns reference identity, evidence ownership, support IDs and provenance. Generate prose only.
Use only the field-specific source material supplied for that field.
Never output reference IDs, support IDs, source IDs, filenames, pages, paths, retrieval scores or provenance metadata.
Never invent outcomes, percentages, ROI, technologies, people, certifications, dates, countries or client claims.
Do not present proposal, contractual, methodology or catalog scope as completed work.
Benefits require explicit outcome evidence. Successful-delivery wording requires explicit support.
When a field says NO ELIGIBLE SUPPORT, return an empty string or empty list for that field.
Return only valid JSON matching the supplied prose-only schema.
"""

SECTION_SYSTEM_PROMPT = """You write a concise portfolio introduction from safe capsules for selected references only.

The backend owns reference identity and provenance. Generate only section prose.
Use only the supplied capsule facts. Do not output IDs or provenance metadata.
Do not invent numbers, scale, outcomes, certifications, technologies, clients, countries or dates.
Do not use unsupported superlatives such as extensive experience, market leader or hundreds of projects.
Return only valid JSON matching the supplied prose-only schema.
"""


@dataclass(frozen=True)
class PromptPackage:
    messages: list[dict[str, str]]
    response_schema: dict[str, Any]
    prompt_sha256: str
    prompt_version: str = PROMPT_VERSION


def _sanitized_opportunity(request: NarrativeGenerationRequest) -> dict[str, Any]:
    return {
        "title": sanitize_generation_text(request.opportunity_title, maximum_characters=180),
        "description": sanitize_generation_text(request.opportunity_description, maximum_characters=4000),
        "requirements": [
            cleaned
            for value in request.requirements
            if (cleaned := sanitize_generation_text(value, maximum_characters=500))
        ],
        "target_language": request.target_language,
        "tone": request.tone,
        "audience": request.audience,
        "detail_level": request.detail_level,
    }


def _package(system_prompt: str, payload: dict[str, Any], schema: dict[str, Any]) -> PromptPackage:
    user_content = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_content}]
    canonical = json.dumps(messages, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return PromptPackage(
        messages=messages,
        response_schema=schema,
        prompt_sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    )


def _safe_material(record: SourceSupportRecord) -> dict[str, Any]:
    return {
        "source_types": [source_type.value for source_type in record.support_types],
        "safe_label": record.source_label,
        "text": record.text,
    }


def _constrain_empty_support_fields(schema: dict[str, Any], plan: FieldSupportPlan) -> dict[str, Any]:
    constrained = json.loads(json.dumps(schema))
    properties = constrained.get("properties", {})
    for field_name in (
        "headline",
        "short_description",
        "challenge",
        "devoteam_contribution",
        "realisations",
        "benefits",
        "why_relevant_to_opportunity",
    ):
        if getattr(plan, field_name):
            continue
        property_schema = properties.get(field_name, {})
        if field_name in {"realisations", "benefits"}:
            property_schema["maxItems"] = 0
        else:
            property_schema["const"] = ""
    return constrained


def build_reference_prompt(
    request: NarrativeGenerationRequest,
    bundle: ReferenceSourceBundle,
    plan: FieldSupportPlan,
    support_index: dict[str, SourceSupportRecord],
    *,
    repair_attempt: bool = False,
) -> PromptPackage:
    schema = _constrain_empty_support_fields(ReferenceNarrativeDraft.model_json_schema(), plan)
    field_material = {}
    for field_name in (
        "headline",
        "short_description",
        "challenge",
        "devoteam_contribution",
        "realisations",
        "benefits",
        "why_relevant_to_opportunity",
    ):
        records = field_material_records(plan, field_name, support_index)
        field_material[field_name] = [_safe_material(record) for record in records] or "NO ELIGIBLE SUPPORT"
    payload = {
        "task": "Generate prose for exactly one backend-selected reference.",
        "repair_instruction": (
            "The preceding response did not match the prose-only JSON schema. Return one corrected JSON object."
            if repair_attempt
            else None
        ),
        "field_source_material": field_material,
        "opportunity": _sanitized_opportunity(request),
        "required_output_schema": schema,
    }
    return _package(REFERENCE_SYSTEM_PROMPT, payload, schema)


def build_section_prompt(
    request: NarrativeGenerationRequest,
    capsules: list[SafeReferenceCapsule],
    *,
    repair_attempt: bool = False,
) -> PromptPackage:
    schema = SectionNarrativeDraft.model_json_schema()
    safe_capsules = [
        {
            "selected_reference": index,
            "client": capsule.client,
            "sector": capsule.sector,
            "country": capsule.country,
            "period": capsule.period,
            "offering": capsule.offering,
            "grounded_capabilities": list(capsule.grounded_capabilities),
        }
        for index, capsule in enumerate(capsules, start=1)
    ]
    payload = {
        "task": "Generate section-level prose from the selected safe reference capsules.",
        "repair_instruction": (
            "The preceding response did not match the section prose-only JSON schema. Return corrected JSON."
            if repair_attempt
            else None
        ),
        "safe_reference_capsules": safe_capsules,
        "opportunity": _sanitized_opportunity(request),
        "required_output_schema": schema,
    }
    return _package(SECTION_SYSTEM_PROMPT, payload, schema)


def build_prompt(
    request: NarrativeGenerationRequest,
    bundles: list[ReferenceSourceBundle],
    *,
    repair_attempt: bool = False,
) -> PromptPackage:
    """Compatibility helper returning the first per-reference prose prompt."""
    if not bundles:
        raise ValueError("at least one reference bundle is required")
    bundle = bundles[0]
    support_index: dict[str, SourceSupportRecord] = {}
    for fact_name in (
        "reference_number", "mission_title", "client", "country", "period", "sector", "offering", "business_unit",
    ):
        fact = getattr(bundle.facts, fact_name)
        if fact:
            support_index[fact.support_id] = SourceSupportRecord(
                support_id=fact.support_id,
                reference_id=bundle.reference_id,
                support_types=[],
                text=f"{fact.field}: {fact.value}",
                source_label=f"Trusted reference fact: {fact.field}",
            )
    for record in (
        bundle.structured_metadata_scope + bundle.display_evidence + bundle.completed_work_evidence + bundle.proposal_scope
    ):
        support_index[record.support_id] = record
    plan = build_field_support_plan(bundle, support_index)
    return build_reference_prompt(request, bundle, plan, support_index, repair_attempt=repair_attempt)
