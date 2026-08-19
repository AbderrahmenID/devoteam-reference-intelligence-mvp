from __future__ import annotations

from pathlib import Path

import pytest

from reference_narrative.claim_validator import ClaimValidator
from reference_narrative.quality import calculate_support_coverage
from reference_narrative.schemas import (
    ReferenceSectionNarrative,
    SourceSupportRecord,
    SourceType,
    SupportedNarrativeText,
    ValidationSeverity,
)
from reference_narrative.source_bundle import ReferenceSourceBundleBuilder
from scripts.evaluate_reference_narrative import CLASSIFICATION, load_cases
from test_reference_narrative import (
    REF_A,
    REF_B,
    FakeRepository,
    _attestation_support,
    _build,
    _metadata_scope_support,
    _narrative,
    _reference_a,
    _reference_b,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _repository(document_type: str = "ATTESTATION") -> FakeRepository:
    reference_a, types_a = _reference_a(document_type=document_type)
    reference_b, types_b = _reference_b()
    return FakeRepository([reference_a, reference_b], {**types_a, **types_b})


def _validated_narrative(
    text: str,
    *,
    document_type: str = "ATTESTATION",
    use_metadata: bool = False,
):
    repository = _repository(document_type=document_type)
    build = _build(repository, [REF_A])
    if use_metadata:
        support = _metadata_scope_support(build, REF_A)
    elif document_type == "ATTESTATION":
        support = _attestation_support(build, REF_A)
    else:
        support = next(
            record.support_id
            for record in build.support_index.values()
            if record.reference_id == REF_A and SourceType.PROPOSAL_SCOPE in record.support_types
        )
    payload = _narrative([REF_A], {REF_A: support})
    payload["references"][0]["devoteam_contribution"] = {"text": text, "support_ids": [support]}
    narrative = ReferenceSectionNarrative.model_validate(payload)
    result = ClaimValidator(build.bundles, build.support_index, build.known_fact_values).validate(narrative, [REF_A])
    return result


@pytest.mark.parametrize(
    ("text", "expected_code"),
    [
        ("The project delivered a positive ROI.", "UNSUPPORTED_ROI"),
        ("Performance improved by 73%.", "UNSUPPORTED_PERCENTAGE"),
        ("Devoteam used Kubernetes for delivery.", "FABRICATED_TECHNOLOGY"),
        ("The client achieved faster decisions.", "UNSUPPORTED_CLIENT_OUTCOME"),
        ("John Doe joined the delivery team.", "UNSUPPORTED_NAMED_ENTITY"),
        ("Devoteam achieved ISO 9001 certification.", "UNSUPPORTED_CERTIFICATION"),
        ("The engagement generated major cost savings.", "UNSUPPORTED_FINANCIAL_OUTCOME"),
        ("The project received an industry award.", "UNSUPPORTED_AWARD"),
        ("Devoteam delivered the work in 2042.", "UNSUPPORTED_YEAR"),
        ("The work was delivered in Canada.", "UNSUPPORTED_COUNTRY"),
        ("Devoteam successfully delivered the project.", "UNSUPPORTED_SUCCESS_CLAIM"),
    ],
)
def test_fake_provider_hallucination_stress_cases_are_blocking(text: str, expected_code: str) -> None:
    result = _validated_narrative(text)
    matching = [warning for warning in result.warnings if warning.code == expected_code]
    assert matching
    assert all(warning.severity == ValidationSeverity.BLOCKING for warning in matching)
    assert result.export_eligible is False


def test_technical_offer_cannot_be_described_as_complete() -> None:
    result = _validated_narrative(
        "The technical offer was completed and delivered.",
        document_type="PROPOSAL",
        use_metadata=False,
    )
    assert "PROPOSAL_SCOPE_AS_COMPLETED" in {warning.code for warning in result.warnings}
    assert result.export_eligible is False


@pytest.mark.parametrize(
    "text",
    ["Extensive experience in banking.", "Market leader in continuity.", "Hundreds of projects delivered."],
)
def test_unsupported_section_superlatives_are_blocking(text: str) -> None:
    repository = _repository()
    build = _build(repository, [REF_A])
    support = _attestation_support(build, REF_A)
    payload = _narrative([REF_A], {REF_A: support})
    payload["section_intro"] = {"text": text, "support_ids": [support]}
    narrative = ReferenceSectionNarrative.model_validate(payload)
    result = ClaimValidator(build.bundles, build.support_index, build.known_fact_values).validate(narrative, [REF_A])
    assert "UNSUPPORTED_PORTFOLIO_SUPERLATIVE" in {warning.code for warning in result.warnings}
    assert result.export_eligible is False


def test_generic_supported_portfolio_claim_is_allowed() -> None:
    repository = _repository()
    build = _build(repository, [REF_A])
    support = _attestation_support(build, REF_A)
    narrative = ReferenceSectionNarrative.model_validate(_narrative([REF_A], {REF_A: support}))
    result = ClaimValidator(build.bundles, build.support_index, build.known_fact_values).validate(narrative, [REF_A])
    assert "UNSUPPORTED_PORTFOLIO_SUPERLATIVE" not in {warning.code for warning in result.warnings}
    assert result.export_eligible is True


def test_unselected_reference_support_is_blocking_even_for_section_text() -> None:
    repository = _repository()
    build = _build(repository, [REF_A, REF_B])
    support_a = _attestation_support(build, REF_A)
    support_b = _attestation_support(build, REF_B)
    payload = _narrative([REF_A], {REF_A: support_a})
    payload["section_intro"]["support_ids"] = [support_b]
    narrative = ReferenceSectionNarrative.model_validate(payload)
    result = ClaimValidator(build.bundles, build.support_index, build.known_fact_values).validate(narrative, [REF_A])
    assert "UNSELECTED_REFERENCE_SUPPORT" in {warning.code for warning in result.warnings}
    assert result.export_eligible is False


def test_synthesis_fields_are_not_marked_unavailable_when_literal_labels_are_absent() -> None:
    repository = _repository()
    build = _build(repository, [REF_A])
    support = _attestation_support(build, REF_A)
    narrative = ReferenceSectionNarrative.model_validate(_narrative([REF_A], {REF_A: support}))
    result = ClaimValidator(build.bundles, build.support_index, build.known_fact_values).validate(narrative, [REF_A])
    assert "challenge" not in build.bundles[0].unavailable_fields
    assert "benefits" not in build.bundles[0].unavailable_fields
    info = [warning for warning in result.warnings if warning.code == "UNAVAILABLE_FIELD_LEFT_EMPTY"]
    assert info == []
    assert result.valid is True
    assert result.export_eligible is True


def test_metadata_only_support_is_warning_not_blocking() -> None:
    repository = _repository()
    build = _build(repository, [REF_A])
    support = _metadata_scope_support(build, REF_A)
    payload = _narrative([REF_A], {REF_A: support})
    narrative = ReferenceSectionNarrative.model_validate(payload)
    result = ClaimValidator(build.bundles, build.support_index, build.known_fact_values).validate(narrative, [REF_A])
    weak = [warning for warning in result.warnings if warning.code == "WEAK_SOURCE_SUPPORT"]
    assert weak
    assert all(warning.severity == ValidationSeverity.WARNING and not warning.blocking for warning in weak)
    assert result.export_eligible is True


def test_support_coverage_counts_populated_fields_and_valid_multi_reference_support() -> None:
    repository = _repository()
    build = _build(repository, [REF_A, REF_B])
    supports = {reference_id: _attestation_support(build, reference_id) for reference_id in (REF_A, REF_B)}
    narrative = ReferenceSectionNarrative.model_validate(_narrative([REF_A, REF_B], supports))
    metrics = calculate_support_coverage(narrative, build.support_index, [REF_A, REF_B])
    assert metrics.populated_field_count == 11
    assert metrics.supported_populated_field_count == 11
    assert metrics.support_coverage == 1.0

    narrative.references[0].headline.support_ids = []
    metrics = calculate_support_coverage(narrative, build.support_index, [REF_A, REF_B])
    assert metrics.populated_field_count == 11
    assert metrics.supported_populated_field_count == 10
    assert metrics.support_coverage == pytest.approx(10 / 11)


def test_support_coverage_rejects_foreign_and_unknown_support_ids() -> None:
    repository = _repository()
    build = _build(repository, [REF_A, REF_B])
    support_a = _attestation_support(build, REF_A)
    support_b = _attestation_support(build, REF_B)
    narrative = ReferenceSectionNarrative.model_validate(_narrative([REF_A], {REF_A: support_a}))
    narrative.references[0].headline.support_ids = [support_b, "S999"]
    metrics = calculate_support_coverage(narrative, build.support_index, [REF_A])
    assert metrics.supported_populated_field_count == metrics.populated_field_count - 1


def test_fixture_harness_parses_eight_real_id_cases() -> None:
    suite = load_cases(PROJECT_ROOT / "evaluation" / "reference_narrative" / "cases.json")
    assert suite.classification == CLASSIFICATION
    assert len(suite.cases) == 8
    assert {case.request.target_language for case in suite.cases} == {"fr", "en", "ar"}
    assert any(len(case.request.selected_reference_ids) > 1 for case in suite.cases)
    assert all(len(reference_id) == 64 for case in suite.cases for reference_id in case.request.selected_reference_ids)


def test_extra_support_record_for_unselected_reference_is_rejected() -> None:
    repository = _repository()
    build = ReferenceSourceBundleBuilder(repository).build([REF_A])
    support = _attestation_support(build, REF_A)
    unselected_support = SourceSupportRecord(
        support_id="S999",
        reference_id=REF_B,
        support_types=[SourceType.CLIENT_ATTESTATION, SourceType.COMPLETED_WORK_EVIDENCE],
        text="Orange Bank confirms an assessment.",
        source_label="Safe attestation",
    )
    support_index = {**build.support_index, unselected_support.support_id: unselected_support}
    payload = _narrative([REF_A], {REF_A: support})
    payload["section_intro"] = {"text": "Relevant experience", "support_ids": ["S999"]}
    narrative = ReferenceSectionNarrative.model_validate(payload)
    result = ClaimValidator(build.bundles, support_index, build.known_fact_values).validate(narrative, [REF_A])
    assert "UNSELECTED_REFERENCE_SUPPORT" in {warning.code for warning in result.warnings}
