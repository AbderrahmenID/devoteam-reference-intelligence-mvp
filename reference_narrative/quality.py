from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from typing import Iterable, Literal

from .schemas import (
    NarrativeSupportPlan,
    NarrativeValidationResult,
    ReferenceSectionNarrative,
    SourceSupportRecord,
    SupportedNarrativeText,
)


PROVENANCE_WARNING_CODES = {
    "UNSELECTED_REFERENCE",
    "DUPLICATE_REFERENCE",
    "MISSING_SELECTED_REFERENCE",
    "REFERENCE_ORDER_CHANGED",
    "MISSING_SUPPORT",
    "UNKNOWN_SUPPORT_ID",
    "UNSELECTED_REFERENCE_SUPPORT",
    "WRONG_REFERENCE_SUPPORT",
    "EMPTY_SUPPORT_PLAN_VIOLATION",
    "PROVENANCE_PLAN_MISMATCH",
}


@dataclass(frozen=True)
class NarrativeQualityMetrics:
    """Legacy structural coverage view retained for API compatibility."""

    populated_field_count: int
    supported_populated_field_count: int
    support_coverage: float


@dataclass(frozen=True)
class BackendGuaranteeMetrics:
    reference_identity_count: int
    expected_reference_count: int
    reference_identity_coverage: float
    eligible_populated_field_count: int
    deterministically_supported_field_count: int
    deterministic_support_coverage: float
    unknown_support_id_count: int
    unselected_support_count: int
    empty_support_field_violation_count: int
    blocking_provenance_count: int


@dataclass(frozen=True)
class ModelQualityMetrics:
    populated_field_count: int
    total_word_count: int
    maximum_field_word_count: int
    duplicate_text_count: int
    conciseness_indicator: str
    narrative_usefulness: str
    repetition_review: str
    language_review: str
    target_language: str
    latency_ms: float


@dataclass(frozen=True)
class LanguageComplianceResult:
    target_language: str
    detected_language: str
    status: Literal["PASS", "CLEAR_MISMATCH", "UNCERTAIN"]
    compliant: bool
    target_language_ratio: float
    analyzed_letter_count: int
    reason: str


@dataclass(frozen=True)
class NarrativeCompletenessMetrics:
    eligible_field_count: int
    populated_eligible_field_count: int
    usable_eligible_field_count: int
    empty_eligible_field_count: int
    unusable_eligible_field_count: int
    eligible_field_population_rate: float


FRENCH_MARKERS = {
    "au", "aux", "avec", "ce", "ces", "cette", "dans", "de", "des", "du", "elle", "en", "est",
    "et", "la", "le", "les", "leur", "mission", "notre", "pour", "qui", "référence", "sur", "une",
}
ENGLISH_MARKERS = {
    "a", "an", "and", "are", "as", "at", "by", "for", "from", "in", "is", "of", "on", "our", "that",
    "the", "their", "this", "to", "with",
}
FACTUAL_DRIFT_CODES = {
    "UNSUPPORTED_CLIENT",
    "UNSUPPORTED_COUNTRY",
    "UNSUPPORTED_SECTOR",
    "UNSUPPORTED_OFFERING",
    "UNSUPPORTED_YEAR",
    "UNSUPPORTED_NUMBER",
    "UNSUPPORTED_PERCENTAGE",
    "UNSUPPORTED_ROI",
    "UNSUPPORTED_FINANCIAL_OUTCOME",
    "UNSUPPORTED_AWARD",
    "FABRICATED_TECHNOLOGY",
    "UNSUPPORTED_NAMED_ENTITY",
    "UNSUPPORTED_ACRONYM_EXPANSION",
    "UNSUPPORTED_CERTIFICATION",
    "UNSUPPORTED_CLIENT_OUTCOME",
    "UNSUPPORTED_SUCCESS_CLAIM",
    "PROPOSAL_SCOPE_AS_COMPLETED",
    "UNSUPPORTED_COMPLETION_LANGUAGE",
    "COMPLETION_DETAIL_NOT_ATTESTED",
    "UNSUPPORTED_BENEFIT",
    "UNSUPPORTED_PORTFOLIO_SUPERLATIVE",
}


def iter_narrative_fields(
    narrative: ReferenceSectionNarrative,
) -> Iterable[tuple[str, SupportedNarrativeText, str | None]]:
    yield "section_intro", narrative.section_intro, None
    yield "overall_storyline", narrative.overall_storyline, None
    yield "why_these_references", narrative.why_these_references, None
    for index, reference in enumerate(narrative.references):
        root = f"references[{index}]"
        yield f"{root}.headline", reference.headline, reference.reference_id
        yield f"{root}.short_description", reference.short_description, reference.reference_id
        yield f"{root}.challenge", reference.challenge, reference.reference_id
        yield f"{root}.devoteam_contribution", reference.devoteam_contribution, reference.reference_id
        for bullet_index, bullet in enumerate(reference.realisations):
            yield f"{root}.realisations[{bullet_index}]", bullet, reference.reference_id
        for bullet_index, bullet in enumerate(reference.benefits):
            yield f"{root}.benefits[{bullet_index}]", bullet, reference.reference_id
        yield f"{root}.why_relevant_to_opportunity", reference.why_relevant_to_opportunity, reference.reference_id


def _planned_support_ids(
    path: str,
    reference_id: str | None,
    support_plan: NarrativeSupportPlan,
) -> list[str]:
    if reference_id is None:
        return list(getattr(support_plan.section, path))
    plans = {plan.reference_id: plan for plan in support_plan.references}
    plan = plans.get(reference_id)
    if plan is None:
        return []
    field_name = path.rsplit(".", 1)[-1].split("[", 1)[0]
    return list(getattr(plan, field_name))


def calculate_support_coverage(
    narrative: ReferenceSectionNarrative,
    support_index: dict[str, SourceSupportRecord],
    selected_reference_ids: list[str],
) -> NarrativeQualityMetrics:
    selected = set(selected_reference_ids)
    populated = 0
    supported = 0
    for _, field, reference_id in iter_narrative_fields(narrative):
        if not field.text.strip():
            continue
        populated += 1
        valid_support = any(
            (record := support_index.get(support_id)) is not None
            and record.reference_id in selected
            and (reference_id is None or record.reference_id == reference_id)
            for support_id in field.support_ids
        )
        if valid_support:
            supported += 1
    coverage = supported / populated if populated else 1.0
    return NarrativeQualityMetrics(populated, supported, coverage)


def calculate_backend_guarantees(
    narrative: ReferenceSectionNarrative,
    support_index: dict[str, SourceSupportRecord],
    selected_reference_ids: list[str],
    support_plan: NarrativeSupportPlan,
    validation: NarrativeValidationResult,
) -> BackendGuaranteeMetrics:
    generated_ids = [reference.reference_id for reference in narrative.references]
    identity_count = sum(
        generated == expected for generated, expected in zip(generated_ids, selected_reference_ids, strict=False)
    )
    expected_count = len(selected_reference_ids)
    eligible_populated = 0
    deterministic_supported = 0
    unknown = 0
    unselected = 0
    empty_plan_violations = 0
    selected = set(selected_reference_ids)
    for path, field, reference_id in iter_narrative_fields(narrative):
        expected_supports = _planned_support_ids(path, reference_id, support_plan)
        for support_id in field.support_ids:
            record = support_index.get(support_id)
            if record is None:
                unknown += 1
            elif record.reference_id not in selected:
                unselected += 1
        if not field.text.strip():
            continue
        if not expected_supports:
            empty_plan_violations += 1
            continue
        eligible_populated += 1
        if field.support_ids == expected_supports:
            deterministic_supported += 1
    blocking_provenance = sum(
        warning.code in PROVENANCE_WARNING_CODES and bool(warning.blocking)
        for warning in validation.warnings
    )
    return BackendGuaranteeMetrics(
        reference_identity_count=identity_count,
        expected_reference_count=expected_count,
        reference_identity_coverage=identity_count / expected_count if expected_count else 1.0,
        eligible_populated_field_count=eligible_populated,
        deterministically_supported_field_count=deterministic_supported,
        deterministic_support_coverage=(
            deterministic_supported / eligible_populated if eligible_populated else 1.0
        ),
        unknown_support_id_count=unknown,
        unselected_support_count=unselected,
        empty_support_field_violation_count=empty_plan_violations,
        blocking_provenance_count=blocking_provenance,
    )


def calculate_model_quality(
    narrative: ReferenceSectionNarrative,
    target_language: str,
    latency_ms: float,
) -> ModelQualityMetrics:
    texts = [field.text.strip() for _, field, _ in iter_narrative_fields(narrative) if field.text.strip()]
    word_counts = [len(text.split()) for text in texts]
    duplicate_count = len(texts) - len({text.casefold() for text in texts})
    maximum = max(word_counts, default=0)
    conciseness = "CONCISE" if maximum <= 80 else "VERBOSE_REVIEW_REQUIRED"
    return ModelQualityMetrics(
        populated_field_count=len(texts),
        total_word_count=sum(word_counts),
        maximum_field_word_count=maximum,
        duplicate_text_count=duplicate_count,
        conciseness_indicator=conciseness,
        narrative_usefulness="HUMAN_REVIEW_REQUIRED",
        repetition_review="HUMAN_REVIEW_REQUIRED" if duplicate_count else "NO_EXACT_DUPLICATION_DETECTED",
        language_review="HUMAN_REVIEW_REQUIRED",
        target_language=target_language,
        latency_ms=latency_ms,
    )


def assess_target_language(
    narrative: ReferenceSectionNarrative,
    target_language: str,
) -> LanguageComplianceResult:
    text = " ".join(field.text for _, field, _ in iter_narrative_fields(narrative) if field.text.strip())
    return _assess_language_text(text, target_language)


def assess_reference_language(
    reference: ReferenceNarrative,
    target_language: str,
) -> LanguageComplianceResult:
    """Assess one complete generated reference, never an isolated title or bullet."""

    detailed = reference.detailed_presentation
    if detailed is not None:
        text = " ".join([
            detailed.mission_title.text,
            *[item.text for item in detailed.challenges],
            *[
                value
                for item in detailed.realisations
                for value in [item.text.text, *[subitem.text for subitem in item.subitems]]
            ],
            *[item.text for item in detailed.benefits],
        ])
    else:
        text = " ".join([
            reference.headline.text,
            reference.short_description.text,
            reference.challenge.text,
            reference.devoteam_contribution.text,
            *[item.text for item in reference.realisations],
            *[item.text for item in reference.benefits],
            reference.why_relevant_to_opportunity.text,
        ])
    return _assess_language_text(text, target_language)


def _assess_language_text(text: str, target_language: str) -> LanguageComplianceResult:
    """Return a conservative tri-state language decision for combined prose.

    Acronyms, names, dates, codes, numbers, and product names do not contribute
    to the decision because scoring uses language-specific function words only.
    Low evidence is UNCERTAIN and is intentionally accepted by callers.
    """

    letters = [character for character in text if character.isalpha()]
    arabic_count = sum("\u0600" <= character <= "\u06ff" for character in letters)
    latin_count = sum("LATIN" in unicodedata.name(character, "") for character in letters)
    total_script_letters = arabic_count + latin_count
    arabic_ratio = arabic_count / total_script_letters if total_script_letters else 0.0
    if target_language == "ar":
        detected = "ar" if arabic_ratio >= 0.60 else "latin" if latin_count else "undetermined"
        if arabic_count >= 20 and arabic_ratio >= 0.60:
            status = "PASS"
            reason = "Arabic prose is dominant in the combined reference."
        elif latin_count >= 40 and arabic_ratio < 0.20:
            status = "CLEAR_MISMATCH"
            reason = "Substantial Latin-script prose was found in an Arabic presentation."
        else:
            status = "UNCERTAIN"
            reason = "The combined reference does not contain enough decisive language evidence."
        return LanguageComplianceResult(
            target_language="ar",
            detected_language=detected,
            status=status,
            compliant=status != "CLEAR_MISMATCH",
            target_language_ratio=arabic_ratio,
            analyzed_letter_count=len(letters),
            reason=reason,
        )

    normalized = unicodedata.normalize("NFKC", text).casefold()
    tokens = re.findall(r"[a-zà-öø-ÿ']+", normalized)
    french_score = sum(token in FRENCH_MARKERS for token in tokens)
    english_score = sum(token in ENGLISH_MARKERS for token in tokens)
    marker_total = french_score + english_score
    target_score = french_score if target_language == "fr" else english_score
    other_score = english_score if target_language == "fr" else french_score
    target_ratio = target_score / marker_total if marker_total else 0.0
    detected = (
        "fr" if french_score > english_score else "en" if english_score > french_score else "undetermined"
    )

    sentence_mismatch = False
    for segment in re.split(r"[.!?;:\n]+", normalized):
        segment_tokens = re.findall(r"[a-zà-öø-ÿ']+", segment)
        if len(segment_tokens) < 7:
            continue
        segment_french = sum(token in FRENCH_MARKERS for token in segment_tokens)
        segment_english = sum(token in ENGLISH_MARKERS for token in segment_tokens)
        segment_total = segment_french + segment_english
        segment_other = segment_english if target_language == "fr" else segment_french
        if segment_other >= 3 and segment_total and segment_other / segment_total >= 0.70:
            sentence_mismatch = True
            break

    if arabic_count >= 20 and arabic_ratio >= 0.60:
        status = "CLEAR_MISMATCH"
        reason = "Substantial Arabic prose was found in a Latin-language presentation."
    elif sentence_mismatch or (other_score >= 4 and marker_total >= 6 and target_ratio < 0.40):
        status = "CLEAR_MISMATCH"
        reason = "Substantial prose in another language was found in the combined reference."
    elif marker_total >= 3 and target_ratio >= 0.60 and arabic_ratio < 0.20:
        status = "PASS"
        reason = "The combined reference is clearly written in the target language."
    else:
        status = "UNCERTAIN"
        reason = "The combined reference is short, technical, mixed, or has weak language evidence."

    return LanguageComplianceResult(
        target_language=target_language,
        detected_language=detected,
        status=status,
        compliant=status != "CLEAR_MISMATCH",
        target_language_ratio=target_ratio,
        analyzed_letter_count=len(letters),
        reason=reason,
    )


def calculate_narrative_completeness(
    narrative: ReferenceSectionNarrative,
    support_plan: NarrativeSupportPlan,
    validation: NarrativeValidationResult,
) -> NarrativeCompletenessMetrics:
    plan_by_reference = {plan.reference_id: plan for plan in support_plan.references}
    blocking_paths = {
        warning.field_path
        for warning in validation.warnings
        if warning.blocking and warning.field_path
    }
    eligible = 0
    populated = 0
    usable = 0
    unusable = 0
    for index, reference in enumerate(narrative.references):
        plan = plan_by_reference[reference.reference_id]
        for field_name in (
            "headline",
            "short_description",
            "challenge",
            "devoteam_contribution",
            "realisations",
            "benefits",
            "why_relevant_to_opportunity",
        ):
            if not getattr(plan, field_name):
                continue
            eligible += 1
            value = getattr(reference, field_name)
            is_populated = bool(value) if isinstance(value, list) else bool(value.text.strip())
            if not is_populated:
                continue
            populated += 1
            root = f"references[{index}].{field_name}"
            has_blocking = any(path == root or path.startswith(f"{root}[") for path in blocking_paths)
            if has_blocking:
                unusable += 1
            else:
                usable += 1
    return NarrativeCompletenessMetrics(
        eligible_field_count=eligible,
        populated_eligible_field_count=populated,
        usable_eligible_field_count=usable,
        empty_eligible_field_count=eligible - populated,
        unusable_eligible_field_count=unusable,
        eligible_field_population_rate=populated / eligible if eligible else 1.0,
    )


def count_factual_drift(validation: NarrativeValidationResult) -> int:
    return sum(bool(warning.blocking) and warning.code in FACTUAL_DRIFT_CODES for warning in validation.warnings)
