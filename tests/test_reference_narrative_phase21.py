from __future__ import annotations

import json

import pytest

from reference_narrative.field_policy import (
    FIELD_POLICIES,
    build_field_support_plan,
    build_reference_capsule,
    build_section_support_plan,
)
from reference_narrative.prompt_builder import build_reference_prompt, build_section_prompt
from reference_narrative.quality import calculate_backend_guarantees
from reference_narrative.schemas import SourceType
from reference_narrative.service import ReferenceNarrativeService
from test_reference_narrative import (
    REF_A,
    REF_B,
    FakeProvider,
    FakeRepository,
    _build,
    _prose_responses,
    _reference_a,
    _reference_b,
    _reference_draft,
    _request,
    _section_draft,
)


def _repository(document_type: str = "ATTESTATION") -> FakeRepository:
    reference_a, types_a = _reference_a(document_type=document_type)
    reference_b, types_b = _reference_b()
    return FakeRepository([reference_a, reference_b], {**types_a, **types_b})


def test_backend_inserts_reference_identity_and_support_ids() -> None:
    repository = _repository()
    provider = FakeProvider(_prose_responses([REF_A]))
    response = ReferenceNarrativeService(repository, provider).generate(_request())
    reference = response.narrative.references[0]
    plan = response.support_plan.references[0]
    assert reference.reference_id == REF_A
    assert reference.headline.support_ids == plan.headline
    assert reference.short_description.support_ids == plan.short_description
    assert reference.devoteam_contribution.support_ids == plan.devoteam_contribution
    assert reference.why_relevant_to_opportunity.support_ids == plan.why_relevant_to_opportunity
    assert len(provider.calls) == 2  # one reference call plus one section-capsule call


@pytest.mark.parametrize("injected_key", ["reference_id", "support_ids"])
def test_model_cannot_override_identity_or_invent_support_ids(injected_key: str) -> None:
    repository = _repository()
    invalid = _reference_draft(REF_A)
    invalid[injected_key] = REF_B if injected_key == "reference_id" else ["S999"]
    provider = FakeProvider(
        [
            json.dumps(_section_draft()),
            json.dumps(invalid),
            json.dumps(_reference_draft(REF_A)),
        ]
    )
    response = ReferenceNarrativeService(repository, provider).generate(_request())
    assert response.narrative.references[0].reference_id == REF_A
    assert all("S999" not in field.support_ids for field in (
        response.narrative.references[0].headline,
        response.narrative.references[0].short_description,
        response.narrative.references[0].challenge,
        response.narrative.references[0].devoteam_contribution,
        response.narrative.references[0].why_relevant_to_opportunity,
    ))
    assert response.provenance.structured_output_retry_count == 1


def test_model_contract_and_prompt_exclude_provenance_identifiers() -> None:
    repository = _repository()
    build = _build(repository, [REF_A])
    bundle = build.bundles[0]
    plan = build_field_support_plan(bundle, build.support_index)
    prompt = build_reference_prompt(_request(), bundle, plan, build.support_index)
    schema_text = json.dumps(prompt.response_schema)
    prompt_text = json.dumps(prompt.messages, ensure_ascii=False)
    assert "reference_id" not in schema_text
    assert "support_ids" not in schema_text
    assert REF_A not in prompt_text
    assert '"support_id"' not in prompt_text
    assert prompt.response_schema["properties"]["challenge"]["const"] == ""
    assert prompt.response_schema["properties"]["benefits"]["maxItems"] == 0


@pytest.mark.parametrize(
    ("field_name", "model_value", "expected_value"),
    [("benefits", [], []), ("challenge", "", "")],
)
def test_empty_support_plan_preserves_empty_model_output(field_name, model_value, expected_value) -> None:
    repository = _repository()
    response = ReferenceNarrativeService(repository, FakeProvider(_prose_responses([REF_A]))).generate(_request())
    plan = response.support_plan.references[0]
    assert getattr(plan, field_name) == []
    actual = getattr(response.narrative.references[0], field_name)
    assert (actual.text if field_name == "challenge" else actual) == expected_value
    assert "EMPTY_SUPPORT_PLAN_VIOLATION" not in {warning.code for warning in response.warnings}


@pytest.mark.parametrize(
    ("field_name", "model_value"),
    [("benefits", ["An unsupported client outcome"]), ("challenge", "An unsupported challenge")],
)
def test_populated_field_with_empty_support_plan_is_blocking(field_name: str, model_value) -> None:
    repository = _repository()
    draft = _reference_draft(REF_A, **{field_name: model_value})
    response = ReferenceNarrativeService(
        repository,
        FakeProvider(_prose_responses([REF_A], drafts={REF_A: draft})),
    ).generate(_request())
    assert "EMPTY_SUPPORT_PLAN_VIOLATION" in {warning.code for warning in response.warnings}
    assert response.validation.export_eligible is False


def test_field_policy_types_and_smallest_support_sets() -> None:
    repository = _repository()
    build = _build(repository, [REF_A])
    bundle = build.bundles[0]
    plan = build_field_support_plan(bundle, build.support_index)
    all_reference_supports = [
        record for record in build.support_index.values() if record.reference_id == REF_A
    ]
    for field_name, policy in FIELD_POLICIES.items():
        selected_ids = getattr(plan, field_name)
        assert len(selected_ids) <= policy.max_supports
        assert len(selected_ids) < len(all_reference_supports)
        for support_id in selected_ids:
            record = build.support_index[support_id]
            assert any(source_type in policy.allowed_types for source_type in record.support_types)


def test_proposal_only_evidence_cannot_enter_realisations_plan() -> None:
    repository = _repository(document_type="PROPOSAL")
    build = _build(repository, [REF_A])
    plan = build_field_support_plan(build.bundles[0], build.support_index)
    proposal_ids = {
        record.support_id
        for record in build.support_index.values()
        if SourceType.PROPOSAL_SCOPE in record.support_types
    }
    assert proposal_ids
    assert plan.realisations == []
    assert proposal_ids.isdisjoint(plan.realisations)


def test_section_capsules_and_prompt_contain_selected_references_only() -> None:
    repository = _repository()
    build = _build(repository, [REF_A])
    capsules = [build_reference_capsule(build.bundles[0], build.support_index)]
    section_plan = build_section_support_plan(capsules)
    prompt = build_section_prompt(_request(), capsules)
    serialized = json.dumps(prompt.messages, ensure_ascii=False)
    assert [capsule.reference_id for capsule in capsules] == [REF_A]
    assert REF_A not in serialized
    assert REF_B not in serialized
    assert section_plan.section_intro
    assert all(build.support_index[support_id].reference_id == REF_A for support_id in section_plan.section_intro)


def test_section_provenance_is_assigned_by_backend() -> None:
    repository = _repository()
    response = ReferenceNarrativeService(repository, FakeProvider(_prose_responses([REF_A]))).generate(_request())
    section_plan = response.support_plan.section
    assert response.narrative.section_intro.support_ids == section_plan.section_intro
    assert response.narrative.overall_storyline.support_ids == section_plan.overall_storyline
    assert response.narrative.why_these_references.support_ids == section_plan.why_these_references


def test_backend_guarantees_are_separate_and_complete_for_safe_fake_output() -> None:
    repository = _repository()
    response = ReferenceNarrativeService(repository, FakeProvider(_prose_responses([REF_A]))).generate(_request())
    support_index = {support.support_id: support for support in response.source_supports}
    metrics = calculate_backend_guarantees(
        response.narrative,
        support_index,
        [REF_A],
        response.support_plan,
        response.validation,
    )
    assert metrics.reference_identity_coverage == 1.0
    assert metrics.deterministic_support_coverage == 1.0
    assert metrics.unknown_support_id_count == 0
    assert metrics.unselected_support_count == 0
    assert metrics.empty_support_field_violation_count == 0
    assert metrics.blocking_provenance_count == 0
