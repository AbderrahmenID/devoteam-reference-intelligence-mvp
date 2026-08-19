from __future__ import annotations

import re
from dataclasses import dataclass

from .schemas import (
    FieldSupportPlan,
    ReferenceSourceBundle,
    SafeReferenceCapsule,
    SectionSupportPlan,
    SourceSupportRecord,
    SourceType,
)


REFERENCE_FIELDS = (
    "headline",
    "short_description",
    "challenge",
    "devoteam_contribution",
    "realisations",
    "benefits",
    "why_relevant_to_opportunity",
)

CHALLENGE_RE = re.compile(
    r"\b(?:challenge|problem|issue|risk|constraint|enjeu|défi|problème|risque|contrainte|تحد|مشكلة|مخاطر)\w*\b",
    re.IGNORECASE,
)
OUTCOME_RE = re.compile(
    r"\b(?:benefit|outcome|result|gain|improv|reduc|increas|bénéf|résultat|amélior|réduct|augment|"
    r"فائدة|نتيجة|تحسين|خفض|زيادة)\w*\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class FieldSourcePolicy:
    allowed_types: frozenset[SourceType]
    preferred_types: tuple[SourceType, ...]
    max_supports: int
    fact_fields: tuple[str, ...] = ()
    unavailable_field: str | None = None
    content_pattern: re.Pattern[str] | None = None


FIELD_POLICIES: dict[str, FieldSourcePolicy] = {
    "headline": FieldSourcePolicy(
        frozenset({SourceType.FACT, SourceType.STRUCTURED_METADATA, SourceType.COMPLETED_WORK_EVIDENCE}),
        (SourceType.FACT, SourceType.COMPLETED_WORK_EVIDENCE, SourceType.STRUCTURED_METADATA),
        2,
        fact_fields=("mission_title", "client"),
    ),
    "short_description": FieldSourcePolicy(
        frozenset({SourceType.FACT, SourceType.STRUCTURED_METADATA, SourceType.COMPLETED_WORK_EVIDENCE}),
        (SourceType.FACT, SourceType.COMPLETED_WORK_EVIDENCE, SourceType.STRUCTURED_METADATA),
        3,
        fact_fields=("mission_title", "client"),
    ),
    "challenge": FieldSourcePolicy(
        frozenset({SourceType.STRUCTURED_METADATA, SourceType.PROPOSAL_SCOPE, SourceType.CONTRACTUAL_SCOPE}),
        (SourceType.CONTRACTUAL_SCOPE, SourceType.PROPOSAL_SCOPE, SourceType.STRUCTURED_METADATA),
        1,
        unavailable_field="challenge",
        content_pattern=CHALLENGE_RE,
    ),
    "devoteam_contribution": FieldSourcePolicy(
        frozenset(
            {
                SourceType.COMPLETED_WORK_EVIDENCE,
                SourceType.CLIENT_ATTESTATION,
                SourceType.CONTRACTUAL_SCOPE,
                SourceType.STRUCTURED_METADATA,
            }
        ),
        (
            SourceType.COMPLETED_WORK_EVIDENCE,
            SourceType.CLIENT_ATTESTATION,
            SourceType.CONTRACTUAL_SCOPE,
            SourceType.STRUCTURED_METADATA,
        ),
        1,
    ),
    "realisations": FieldSourcePolicy(
        frozenset({SourceType.COMPLETED_WORK_EVIDENCE, SourceType.CLIENT_ATTESTATION}),
        (SourceType.COMPLETED_WORK_EVIDENCE, SourceType.CLIENT_ATTESTATION),
        1,
        unavailable_field="completed_work_details",
    ),
    "benefits": FieldSourcePolicy(
        frozenset({SourceType.COMPLETED_WORK_EVIDENCE, SourceType.CLIENT_ATTESTATION}),
        (SourceType.COMPLETED_WORK_EVIDENCE, SourceType.CLIENT_ATTESTATION),
        1,
        unavailable_field="benefits",
        content_pattern=OUTCOME_RE,
    ),
    "why_relevant_to_opportunity": FieldSourcePolicy(
        frozenset({SourceType.FACT, SourceType.STRUCTURED_METADATA, SourceType.COMPLETED_WORK_EVIDENCE}),
        (SourceType.FACT, SourceType.STRUCTURED_METADATA, SourceType.COMPLETED_WORK_EVIDENCE),
        2,
        fact_fields=("mission_title", "offering", "sector"),
    ),
}


def _fact_support_ids(bundle: ReferenceSourceBundle, fact_fields: tuple[str, ...]) -> list[str]:
    support_ids: list[str] = []
    for field_name in fact_fields:
        fact = getattr(bundle.facts, field_name)
        if fact is not None:
            support_ids.append(fact.support_id)
    return support_ids


def _type_rank(record: SourceSupportRecord, preferred: tuple[SourceType, ...]) -> int:
    ranks = [preferred.index(source_type) for source_type in record.support_types if source_type in preferred]
    return min(ranks) if ranks else len(preferred)


def _eligible_records(
    bundle: ReferenceSourceBundle,
    support_index: dict[str, SourceSupportRecord],
    policy: FieldSourcePolicy,
) -> list[SourceSupportRecord]:
    records = [
        record
        for record in support_index.values()
        if record.reference_id == bundle.reference_id
        and any(source_type in policy.allowed_types for source_type in record.support_types)
        and SourceType.FACT not in record.support_types
    ]
    if policy.content_pattern is not None:
        records = [record for record in records if policy.content_pattern.search(record.text)]
    return sorted(records, key=lambda record: (_type_rank(record, policy.preferred_types), record.support_id))


def build_field_support_plan(
    bundle: ReferenceSourceBundle,
    support_index: dict[str, SourceSupportRecord],
) -> FieldSupportPlan:
    values: dict[str, object] = {"reference_id": bundle.reference_id}
    for field_name in REFERENCE_FIELDS:
        policy = FIELD_POLICIES[field_name]
        if policy.unavailable_field and policy.unavailable_field in bundle.unavailable_fields:
            values[field_name] = []
            continue
        selected = _fact_support_ids(bundle, policy.fact_fields)
        for record in _eligible_records(bundle, support_index, policy):
            if record.support_id not in selected:
                selected.append(record.support_id)
            if len(selected) >= policy.max_supports:
                break
        values[field_name] = selected[: policy.max_supports]
    return FieldSupportPlan.model_validate(values)


def build_detailed_presentation_support_plan(
    bundle: ReferenceSourceBundle,
    support_index: dict[str, SourceSupportRecord],
    base_plan: FieldSupportPlan,
) -> FieldSupportPlan:
    """Build a rich, bounded support plan only for the detailed slide writer."""

    catalog_records = [
        record
        for record in bundle.structured_metadata_scope
        if record.source_label == "Structured catalog scope" and record.text.strip()
    ]
    catalog_text = " ".join(record.text for record in catalog_records)
    catalog_tokens = {
        token
        for token in re.findall(r"[a-zA-ZÀ-ÖØ-öø-ÿ]{4,}", catalog_text.casefold())
        if token not in {"avec", "dans", "pour", "cette", "mission", "projet", "service"}
    }

    def evidence_rank(record: SourceSupportRecord) -> tuple[int, int, str]:
        record_tokens = set(re.findall(r"[a-zA-ZÀ-ÖØ-öø-ÿ]{4,}", record.text.casefold()))
        overlap = len(catalog_tokens & record_tokens)
        strong = int(
            SourceType.COMPLETED_WORK_EVIDENCE in record.support_types
            or SourceType.CLIENT_ATTESTATION in record.support_types
        )
        return (-strong, -overlap, record.support_id)

    evidence_records = sorted(bundle.display_evidence, key=evidence_rank)
    # Detailed synthesis uses the complete approved evidence context for this
    # one reference. Source roles remain attached to every support record.
    selected_records = [*catalog_records, *evidence_records]
    rich_ids = list(dict.fromkeys(record.support_id for record in selected_records))
    if not rich_ids:
        return base_plan
    headline_ids = list(base_plan.headline)
    if bundle.facts.offering is not None:
        headline_ids.append(bundle.facts.offering.support_id)
    headline_ids.extend(rich_ids)
    return base_plan.model_copy(
        update={
            "headline": list(dict.fromkeys(headline_ids)),
            "challenge": rich_ids,
            "realisations": rich_ids,
            "benefits": rich_ids,
        }
    )


def build_reference_capsule(
    bundle: ReferenceSourceBundle,
    support_index: dict[str, SourceSupportRecord],
) -> SafeReferenceCapsule:
    del support_index
    values: dict[str, str] = {}
    support_ids: list[str] = []
    for field_name in ("client", "sector", "country", "period", "offering"):
        fact = getattr(bundle.facts, field_name)
        values[field_name] = fact.value if fact else ""
        if fact:
            support_ids.append(fact.support_id)
    capabilities: list[str] = []
    if bundle.facts.business_unit:
        capabilities.append(bundle.facts.business_unit.value)
        support_ids.append(bundle.facts.business_unit.support_id)
    for technology in bundle.facts.technologies[:2]:
        capabilities.append(technology.value)
        support_ids.append(technology.support_id)
    return SafeReferenceCapsule(
        reference_id=bundle.reference_id,
        grounded_capabilities=capabilities,
        support_ids=list(dict.fromkeys(support_ids)),
        **values,
    )


def build_section_support_plan(capsules: list[SafeReferenceCapsule]) -> SectionSupportPlan:
    support_ids = list(dict.fromkeys(support_id for capsule in capsules for support_id in capsule.support_ids))
    return SectionSupportPlan(
        section_intro=support_ids,
        overall_storyline=support_ids,
        why_these_references=support_ids,
    )


def field_material_records(
    plan: FieldSupportPlan,
    field_name: str,
    support_index: dict[str, SourceSupportRecord],
) -> list[SourceSupportRecord]:
    return [support_index[support_id] for support_id in getattr(plan, field_name) if support_id in support_index]
