from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import pandas as pd
import pytest

from app.api.settings import PROJECT_ROOT, load_config
from reference_narrative.claim_validator import ClaimValidator
from reference_narrative.ollama_client import DisabledNarrativeProvider, NarrativeProviderDisabledError
from reference_narrative.ollama_client import NarrativeProviderResponseError
from reference_narrative.prompt_builder import build_prompt
from reference_narrative.presentation_copy import PresentationCopyService
from reference_narrative.presentation_schemas import DirectPresentationRequest
from reference_narrative.schemas import (
    NarrativeGenerationRequest,
    ReferenceNarrative,
    ReferenceSectionNarrative,
    SupportedNarrativeText,
)
from reference_narrative.service import NarrativeStructuredOutputError, ReferenceNarrativeService
from reference_narrative.source_bundle import ReferenceSourceBundleBuilder
from reference_pack.schemas import TrustedEvidence, TrustedReference
from reference_pack.validation import ReferenceValidationError, TrustedV2Repository


REF_A = "a" * 64
REF_B = "b" * 64
UNKNOWN_REF = "f" * 64


def _evidence(
    chunk_id: str,
    filename: str,
    text: str,
    *,
    page: int = 1,
) -> TrustedEvidence:
    return TrustedEvidence(
        chunk_id=chunk_id,
        document_id=f"doc-{chunk_id}",
        source_file_name=filename,
        source_sha256="1" * 64,
        source_page=page,
        citation_label=f"{filename} - page {page}",
        citation_uri="https://example.test/source",
        language="fr",
        display_text=text,
        source_relative_path=r"raw\evidence\private\source.pdf",
    )


def _reference_a(document_type: str = "ATTESTATION") -> tuple[TrustedReference, dict[str, str]]:
    evidence_text = (
        "Devoteam performed the operationalisation of the PCA project for Banque Centrale de Tunisie in 2022."
        if document_type == "ATTESTATION"
        else "The contract scope includes workshops and procedures for five critical applications."
    )
    reference = TrustedReference(
        reference_id=REF_A,
        row_number=107,
        mission_title="Operationalisation du PCA de la BCT",
        client="Banque Centrale de Tunisie",
        country="Tunisie",
        period="2022",
        sector="Banque",
        offering="PCA/PCI",
        business_unit="Trust & Cyber Security",
        description=(
            "Detailed structured catalog scope: workshops for business procedures, five critical applications, "
            "a crisis communication plan and a global test plan."
        ),
        services_delivered=[],
        technologies=[],
        capabilities=[],
        evidence=[_evidence("chunk-a", "BCT attestation.pdf", evidence_text)],
    )
    return reference, {"chunk-a": document_type}


def _reference_b() -> tuple[TrustedReference, dict[str, str]]:
    reference = TrustedReference(
        reference_id=REF_B,
        row_number=108,
        mission_title="Cloud governance assessment",
        client="Orange Bank",
        country="France",
        period="2023",
        sector="Banque",
        offering="Cloud",
        business_unit="Cloud",
        description="Structured catalog scope for a cloud governance assessment.",
        services_delivered=[],
        technologies=["Cloud"],
        capabilities=[],
        evidence=[
            _evidence(
                "chunk-b",
                "Orange Bank attestation.pdf",
                "Orange Bank confirms that Devoteam performed a cloud governance assessment in 2023.",
            )
        ],
    )
    return reference, {"chunk-b": "ATTESTATION"}


class FakeRepository:
    def __init__(self, references: list[TrustedReference], document_types: dict[str, str]):
        self.by_id = {reference.reference_id: reference for reference in references}
        self.chunks = pd.DataFrame(
            [{"chunk_id": chunk_id, "document_type": value} for chunk_id, value in document_types.items()]
        )
        self.references = pd.DataFrame(
            [
                {
                    "client": reference.client,
                    "country": reference.country,
                    "sector": reference.sector,
                    "offering": reference.offering,
                    "project_year": reference.period,
                }
                for reference in references
            ]
        )

    def load_selected(self, reference_ids: list[str]) -> list[TrustedReference]:
        unknown = [reference_id for reference_id in reference_ids if reference_id not in self.by_id]
        if unknown:
            raise ReferenceValidationError("UNKNOWN_REFERENCE_ID", unknown, "Unknown selected reference")
        return [self.by_id[reference_id] for reference_id in reference_ids]


@dataclass
class FakeProvider:
    responses: list[str]
    provider_name: str = "fake"
    model_name: str = "fake-model"

    def __post_init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def generate(self, messages: list[dict[str, str]], response_schema: dict[str, Any]) -> str:
        self.calls.append({"messages": messages, "response_schema": response_schema})
        return self.responses.pop(0)


def _direct_request(reference_ids: list[str], template_id: str = "detailed_reference") -> DirectPresentationRequest:
    return DirectPresentationRequest(
        selected_reference_ids=reference_ids,
        opportunity_context="Banking continuity opportunity",
        target_language="en",
        template_id=template_id,
        output_format="both",
    )


def test_presentation_copy_generates_one_reference_per_call_without_cross_reference_context() -> None:
    reference_a, types_a = _reference_a()
    reference_b, types_b = _reference_b()
    provider = FakeProvider([
        json.dumps({"mission_title": reference_a.mission_title, "challenges": [], "realisations": [], "benefits": []}),
        json.dumps({"mission_title": reference_b.mission_title, "challenges": [], "realisations": [], "benefits": []}),
    ])
    service = ReferenceNarrativeService(
        FakeRepository([reference_a, reference_b], {**types_a, **types_b}),
        provider,
    )
    progress: list[dict[str, object]] = []

    result = PresentationCopyService(service, provider).generate(
        _direct_request([REF_A, REF_B]), progress.append
    )

    assert len(provider.calls) == 2
    first_payload = json.loads(provider.calls[0]["messages"][1]["content"])
    second_payload = json.loads(provider.calls[1]["messages"][1]["content"])
    assert first_payload["task"] == second_payload["task"] == "DETAILED_REFERENCE_COPY"
    assert first_payload["trusted_metadata"]["client"] == reference_a.client
    assert second_payload["trusted_metadata"]["client"] == reference_b.client
    assert reference_b.client not in provider.calls[0]["messages"][1]["content"]
    assert reference_a.client not in provider.calls[1]["messages"][1]["content"]
    assert [item.reference_id for item in result.review.narrative.references] == [REF_A, REF_B]
    assert [event["event"] for event in progress] == [
        "reference_started", "fit_started", "reference_completed",
        "reference_started", "reference_completed",
    ]


def test_presentation_copy_retries_one_reference_then_uses_safe_fallback_and_continues() -> None:
    reference_a, types_a = _reference_a()
    reference_b, types_b = _reference_b()
    provider = FakeProvider([
        "not-json",
        "still-not-json",
        json.dumps({"mission_title": reference_b.mission_title, "challenges": [], "realisations": [], "benefits": []}),
    ])
    service = ReferenceNarrativeService(
        FakeRepository([reference_a, reference_b], {**types_a, **types_b}),
        provider,
    )

    result = PresentationCopyService(service, provider).generate(_direct_request([REF_A, REF_B]))

    assert len(provider.calls) == 3
    assert result.generation_records[0]["attempts"] == 2
    assert result.generation_records[0]["fallback_used"] is True
    assert result.generation_records[1]["attempts"] == 1
    assert result.review.narrative.references[0].headline.text == reference_a.mission_title
    assert result.review.narrative.references[0].challenge.text.startswith("Besoin d’")
    assert result.review.narrative.references[0].benefits == []


def test_presentation_copy_retains_only_independently_grounded_safe_portions() -> None:
    reference, document_types = _reference_a()
    exact = "Devoteam performed the operationalisation of the PCA project"
    mixed = json.dumps({
        "display_title": reference.mission_title,
        "activities": [exact, "The project delivered a positive ROI.", exact],
    })
    provider = FakeProvider([mixed, mixed])
    service = ReferenceNarrativeService(FakeRepository([reference], document_types), provider)

    result = PresentationCopyService(service, provider).generate(
        _direct_request([REF_A], "orange_bank_compact")
    )

    assert len(provider.calls) == 2
    assert result.generation_records[0]["fallback_used"] is True
    assert result.generation_records[0]["safe_generated_portions_retained"] is True
    retained = [item.text for item in result.review.narrative.references[0].realisations]
    assert retained == [exact, exact]
    assert all("ROI" not in item for item in retained)


def test_template_aware_prompt_uses_real_detailed_field_capacities() -> None:
    reference, document_types = _reference_a()
    provider = FakeProvider([
        json.dumps({
            "mission_title": reference.mission_title,
            "challenges": [],
            "realisations": [],
            "benefits": [],
        })
    ])
    service = ReferenceNarrativeService(FakeRepository([reference], document_types), provider)

    PresentationCopyService(service, provider).generate(_direct_request([REF_A]))

    payload = json.loads(provider.calls[0]["messages"][1]["content"])
    assert "8 rendered lines" in payload["layout_budget"]["challenges"]
    assert "11 rendered lines" in payload["layout_budget"]["realisations"]
    assert "7 rendered lines" in payload["layout_budget"]["benefits"]
    assert "9 pt" in payload["layout_budget"]["challenges"]


def test_content_within_actual_challenge_capacity_needs_no_fit_repair() -> None:
    reference, document_types = _reference_a()
    long_supported = [
        "The challenge required continuity workshops for business procedures across critical banking operations and coordination with operational stakeholders.",
        "The risk concerned five critical applications, crisis communication responsibilities and dependencies between technical and business response teams.",
        "The constraint was to define a global test plan covering governance, escalation, recovery exercises and documented continuity procedures.",
    ]
    reference = reference.model_copy(update={"description": " ".join(long_supported)})
    provider = FakeProvider([
        json.dumps({
            "mission_title": reference.mission_title,
            "challenges": long_supported,
            "realisations": [],
            "benefits": [],
        }),
        json.dumps({"challenge": ["workshops for business procedures"]}),
    ])
    service = ReferenceNarrativeService(FakeRepository([reference], document_types), provider)

    result = PresentationCopyService(service, provider).generate(_direct_request([REF_A]))

    assert len(provider.calls) == 1
    assert result.generation_records[0]["template_fit"]["repairs"] == []
    assert result.generation_records[0]["template_fit"]["status"] == "PASS"


def test_unused_fit_responses_are_not_consumed_when_copy_already_fits() -> None:
    reference, document_types = _reference_a()
    long_supported = [
        "The challenge required continuity workshops for business procedures across critical banking operations and coordination with operational stakeholders.",
        "The risk concerned five critical applications, crisis communication responsibilities and dependencies between technical and business response teams.",
        "The constraint was to define a global test plan covering governance, escalation, recovery exercises and documented continuity procedures.",
    ]
    reference = reference.model_copy(update={"description": " ".join(long_supported)})
    initial = {
        "mission_title": reference.mission_title,
        "challenges": long_supported,
        "realisations": [],
        "benefits": [],
    }
    still_long = {"challenge": long_supported}
    provider = FakeProvider([json.dumps(initial), json.dumps(still_long), json.dumps(still_long)])
    service = ReferenceNarrativeService(FakeRepository([reference], document_types), provider)

    result = PresentationCopyService(service, provider).generate(_direct_request([REF_A]))

    assert len(provider.calls) == 1
    assert len(provider.responses) == 2
    assert result.generation_records[0]["template_fit"]["repairs"] == []


def test_orange_copy_budget_is_template_specific_and_needs_no_extra_call_when_fit() -> None:
    reference, document_types = _reference_a()
    activity = "Devoteam performed the operationalisation of the PCA project"
    provider = FakeProvider([
        json.dumps({
            "display_title": reference.mission_title,
            "activities": [activity, activity, activity],
        })
    ])
    service = ReferenceNarrativeService(FakeRepository([reference], document_types), provider)

    result = PresentationCopyService(service, provider).generate(
        _direct_request([REF_A], "orange_bank_compact")
    )

    assert len(provider.calls) == 1
    payload = json.loads(provider.calls[0]["messages"][1]["content"])
    assert "12 rendered lines" in payload["layout_budget"]["activities"]
    assert result.generation_records[0]["template_fit"]["repair_count"] == 0


def _request(reference_ids: list[str] | None = None, language: str = "en") -> NarrativeGenerationRequest:
    return NarrativeGenerationRequest(
        selected_reference_ids=reference_ids or [REF_A],
        opportunity_title="Banking continuity opportunity",
        opportunity_description="A banking institution needs a grounded PCA reference section.",
        requirements=["Use only completed-work evidence for delivery claims."],
        target_language=language,
        tone="commercial",
        audience="executive",
        detail_level="medium",
    )


def _empty() -> SupportedNarrativeText:
    return SupportedNarrativeText(text="", support_ids=[])


def _attestation_support(build_result, reference_id: str) -> str:
    for record in build_result.support_index.values():
        if record.reference_id == reference_id and "COMPLETED_WORK_EVIDENCE" in {
            source_type.value for source_type in record.support_types
        }:
            return record.support_id
    raise AssertionError("attestation support not found")


def _metadata_scope_support(build_result, reference_id: str) -> str:
    for record in build_result.support_index.values():
        if record.reference_id == reference_id and record.source_label == "Structured catalog scope":
            return record.support_id
    raise AssertionError("metadata support not found")


def _narrative(reference_ids: list[str], support_ids: dict[str, str], *, language: str = "en") -> dict[str, Any]:
    labels = {
        "en": ("Relevant experience", "PCA experience is relevant"),
        "fr": ("Expérience pertinente", "Une expérience PCA pertinente"),
        "ar": ("خبرة ذات صلة", "خبرة ذات صلة باستمرارية الأعمال"),
    }
    intro, relevance = labels[language]
    section_support = [support_ids[reference_id] for reference_id in reference_ids]
    references = []
    for reference_id in reference_ids:
        support_id = support_ids[reference_id]
        references.append(
            {
                "reference_id": reference_id,
                "headline": {"text": relevance, "support_ids": [support_id]},
                "short_description": {"text": relevance, "support_ids": [support_id]},
                "challenge": {"text": "", "support_ids": []},
                "devoteam_contribution": {"text": relevance, "support_ids": [support_id]},
                "realisations": [],
                "benefits": [],
                "why_relevant_to_opportunity": {"text": relevance, "support_ids": [support_id]},
                "warnings": [],
            }
        )
    return {
        "section_intro": {"text": intro, "support_ids": section_support},
        "overall_storyline": {"text": intro, "support_ids": section_support},
        "why_these_references": {"text": intro, "support_ids": section_support},
        "references": references,
    }


def _reference_draft(reference_id: str, **overrides: Any) -> dict[str, Any]:
    base_text = (
        "PCA operationalisation for Banque Centrale de Tunisie"
        if reference_id == REF_A
        else "Cloud governance assessment for Orange Bank"
    )
    payload: dict[str, Any] = {
        "headline": base_text,
        "short_description": base_text,
        "challenge": "",
        "devoteam_contribution": base_text,
        "realisations": [],
        "benefits": [],
        "why_relevant_to_opportunity": base_text,
    }
    payload.update(overrides)
    return payload


def _section_draft(**overrides: Any) -> dict[str, str]:
    payload = {
        "section_intro": "Selected banking references",
        "overall_storyline": "Grounded banking experience",
        "why_these_references": "Relevant banking missions",
    }
    payload.update(overrides)
    return payload


def _prose_responses(reference_ids: list[str], *, drafts: dict[str, dict[str, Any]] | None = None, section=None):
    draft_values = drafts or {}
    return [json.dumps(section or _section_draft(), ensure_ascii=False)] + [
        json.dumps(draft_values.get(reference_id, _reference_draft(reference_id)), ensure_ascii=False)
        for reference_id in reference_ids
    ]


@pytest.fixture
def repository() -> FakeRepository:
    reference_a, types_a = _reference_a()
    reference_b, types_b = _reference_b()
    return FakeRepository([reference_a, reference_b], {**types_a, **types_b})


def _build(repository: FakeRepository, reference_ids: list[str]):
    return ReferenceSourceBundleBuilder(repository).build(reference_ids)


def test_disabled_provider_does_not_contact_ollama(repository: FakeRepository) -> None:
    service = ReferenceNarrativeService(repository, DisabledNarrativeProvider())
    with pytest.raises(NarrativeProviderDisabledError):
        service.generate(_request())


def test_invalid_selected_id_is_rejected_before_generation(repository: FakeRepository) -> None:
    provider = FakeProvider([])
    service = ReferenceNarrativeService(repository, provider)
    with pytest.raises(ReferenceValidationError):
        service.generate(_request([UNKNOWN_REF]))
    assert provider.calls == []


def test_malformed_json_is_retried_once_and_then_fails(repository: FakeRepository) -> None:
    provider = FakeProvider(["not-json", '{"still":"invalid"}'])
    service = ReferenceNarrativeService(repository, provider)
    with pytest.raises(NarrativeStructuredOutputError):
        service.generate(_request())
    assert len(provider.calls) == 2


def test_generation_logs_internal_stage_timings(repository: FakeRepository, caplog) -> None:
    provider = FakeProvider(_prose_responses([REF_A]))
    service = ReferenceNarrativeService(repository, provider)
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        service.generate(_request())
    timing_messages = [record.getMessage() for record in caplog.records if "reference_narrative:" in record.getMessage()]
    assert len(timing_messages) == 1
    for field in ("bundle=", "prompt=", "ollama=", "parsing=", "validation=", "total="):
        assert field in timing_messages[0]


def test_generation_is_section_first_then_one_call_per_reference(repository: FakeRepository) -> None:
    provider = FakeProvider(_prose_responses([REF_A, REF_B]))
    ReferenceNarrativeService(repository, provider).generate(_request([REF_A, REF_B]))
    assert [call["response_schema"]["title"] for call in provider.calls] == [
        "SectionNarrativeDraft",
        "ReferenceNarrativeDraft",
        "ReferenceNarrativeDraft",
    ]


def test_progressive_generation_isolates_one_failed_reference_and_keeps_completed_units(repository: FakeRepository) -> None:
    class FailFirstReferenceProvider(FakeProvider):
        def generate(self, messages, response_schema):
            self.calls.append({"messages": messages, "response_schema": response_schema})
            value = self.responses.pop(0)
            if value == "FAIL":
                raise NarrativeProviderResponseError("isolated reference failure")
            return value

    provider = FailFirstReferenceProvider([
        json.dumps(_section_draft()),
        "FAIL",
        json.dumps(_reference_draft(REF_B)),
    ])
    events: list[dict[str, object]] = []
    result = ReferenceNarrativeService(repository, provider).generate_progressive(
        _request([REF_A, REF_B]),
        events.append,
    )
    assert [event["event"] for event in events if event["event"] == "unit_completed"] == [
        "unit_completed",
        "unit_completed",
    ]
    assert events[1]["unit"] == "section"
    assert any(event["event"] == "unit_failed" and event["reference_id"] == REF_A for event in events)
    assert events[-1]["event"] == "partial"
    assert result["response"] is None
    review = result["review"]
    assert review.narrative.section_intro.text
    assert review.narrative.references[0].headline.text == ""
    assert review.narrative.references[1].headline.text


def test_unknown_support_id_is_blocking(repository: FakeRepository) -> None:
    build = _build(repository, [REF_A])
    support = _attestation_support(build, REF_A)
    payload = _narrative([REF_A], {REF_A: support})
    payload["references"][0]["headline"]["support_ids"] = ["S999"]
    narrative = ReferenceSectionNarrative.model_validate(payload)
    result = ClaimValidator(build.bundles, build.support_index, build.known_fact_values).validate(narrative, [REF_A])
    assert "UNKNOWN_SUPPORT_ID" in {warning.code for warning in result.warnings}
    assert result.export_blocked is True


def test_wrong_reference_support_is_blocking(repository: FakeRepository) -> None:
    build = _build(repository, [REF_A, REF_B])
    supports = {reference_id: _attestation_support(build, reference_id) for reference_id in (REF_A, REF_B)}
    payload = _narrative([REF_A, REF_B], supports)
    payload["references"][0]["headline"]["support_ids"] = [supports[REF_B]]
    narrative = ReferenceSectionNarrative.model_validate(payload)
    result = ClaimValidator(build.bundles, build.support_index, build.known_fact_values).validate(
        narrative, [REF_A, REF_B]
    )
    assert "WRONG_REFERENCE_SUPPORT" in {warning.code for warning in result.warnings}


def test_unsupported_percentage_is_blocking(repository: FakeRepository) -> None:
    draft = _reference_draft(REF_A, benefits=["Improved performance by 80%."])
    response = ReferenceNarrativeService(
        repository,
        FakeProvider(_prose_responses([REF_A], drafts={REF_A: draft})),
    ).generate(_request())
    assert "UNSUPPORTED_PERCENTAGE" in {warning.code for warning in response.warnings}


def test_unsupported_completion_wording_is_blocking(repository: FakeRepository) -> None:
    build = _build(repository, [REF_A])
    metadata = _metadata_scope_support(build, REF_A)
    payload = _narrative([REF_A], {REF_A: metadata})
    payload["references"][0]["devoteam_contribution"] = {
        "text": "Devoteam delivered workshops for critical applications.",
        "support_ids": [metadata],
    }
    narrative = ReferenceSectionNarrative.model_validate(payload)
    result = ClaimValidator(build.bundles, build.support_index, build.known_fact_values).validate(narrative, [REF_A])
    assert "UNSUPPORTED_COMPLETION_LANGUAGE" in {warning.code for warning in result.warnings}


def test_contractual_scope_cannot_be_represented_as_completed_work() -> None:
    reference, types = _reference_a(document_type="CONTRACT")
    repository = FakeRepository([reference], types)
    build = _build(repository, [REF_A])
    contract = next(
        record.support_id
        for record in build.support_index.values()
        if "CONTRACTUAL_SCOPE" in {source_type.value for source_type in record.support_types}
    )
    draft = _reference_draft(REF_A, devoteam_contribution="Devoteam delivered workshops and procedures.")
    response = ReferenceNarrativeService(
        repository,
        FakeProvider(_prose_responses([REF_A], drafts={REF_A: draft})),
    ).generate(_request())
    assert "PROPOSAL_SCOPE_AS_COMPLETED" in {warning.code for warning in response.warnings}


@pytest.mark.parametrize("language", ["fr", "en", "ar"])
def test_languages_and_empty_challenge_benefits_are_allowed(repository: FakeRepository, language: str) -> None:
    response = ReferenceNarrativeService(repository, FakeProvider(_prose_responses([REF_A]))).generate(
        _request(language=language)
    )
    assert response.narrative.references[0].challenge.text == ""
    assert response.narrative.references[0].benefits == []
    assert response.validation.valid is True


def test_multiple_references_and_section_synthesis(repository: FakeRepository) -> None:
    response = ReferenceNarrativeService(repository, FakeProvider(_prose_responses([REF_A, REF_B]))).generate(
        _request([REF_A, REF_B])
    )
    assert [item.reference_id for item in response.narrative.references] == [REF_A, REF_B]
    assert response.narrative.section_intro.support_ids == response.support_plan.section.section_intro
    assert all(response.narrative.section_intro.support_ids)
    assert response.validation.valid is True


def test_internal_paths_chunk_ids_and_retrieval_scores_are_blocking(repository: FakeRepository) -> None:
    section = _section_draft(section_intro=r"C:\private\source.pdf has BM25 score 4.2 and chunk_id data.")
    response = ReferenceNarrativeService(
        repository,
        FakeProvider(_prose_responses([REF_A], section=section)),
    ).generate(_request())
    codes = {warning.code for warning in response.warnings}
    assert {"INTERNAL_PATH", "RETRIEVAL_SCORE", "INTERNAL_CHUNK_ID"} <= codes


def test_prompt_excludes_paths_chunk_ids_and_retrieval_scores(repository: FakeRepository) -> None:
    build = _build(repository, [REF_A])
    prompt = build_prompt(_request(), build.bundles)
    serialized = json.dumps(prompt.messages, ensure_ascii=False)
    assert "chunk-a" not in serialized
    assert r"raw\evidence\private" not in serialized
    assert "bm25_score" not in serialized.casefold()
    assert "dense_score" not in serialized.casefold()


def test_bct_catalog_details_do_not_inherit_attestation_completion(repository: FakeRepository) -> None:
    build = _build(repository, [REF_A])
    bundle = build.bundles[0]
    assert bundle.structured_metadata_scope
    assert bundle.completed_work_evidence
    metadata = _metadata_scope_support(build, REF_A)
    attestation = _attestation_support(build, REF_A)
    assert metadata != attestation

    narrative = ReferenceSectionNarrative.model_validate(_narrative([REF_A], {REF_A: attestation}))
    narrative.references[0].realisations = [
        SupportedNarrativeText(
            text="Devoteam completed workshops for five critical applications and delivered a crisis plan.",
            support_ids=[metadata, attestation],
        )
    ]
    result = ClaimValidator(build.bundles, build.support_index, build.known_fact_values).validate(
        narrative,
        [REF_A],
    )
    assert "COMPLETION_DETAIL_NOT_ATTESTED" in {warning.code for warning in result.warnings}


def test_fabricated_fact_technology_and_named_person_are_blocking(repository: FakeRepository) -> None:
    build = _build(repository, [REF_A])
    attestation = _attestation_support(build, REF_A)
    narrative = ReferenceSectionNarrative.model_validate(_narrative([REF_A], {REF_A: attestation}))
    narrative.references[0].short_description = SupportedNarrativeText(
        text="John Doe used Kubernetes for delivery in France.",
        support_ids=[attestation],
    )
    result = ClaimValidator(build.bundles, build.support_index, build.known_fact_values).validate(
        narrative,
        [REF_A],
    )
    codes = {warning.code for warning in result.warnings}
    assert {"UNSUPPORTED_NAMED_ENTITY", "FABRICATED_TECHNOLOGY", "UNSUPPORTED_COUNTRY"} <= codes


def test_live_v2_bct_provenance_keeps_catalog_scope_separate_from_attestation() -> None:
    bct_reference_id = "38f6543c913e6155ed935bc93b2eb9adb740b8d292f9afd40065032ca7b62b82"
    repository = TrustedV2Repository(PROJECT_ROOT, load_config())
    build = ReferenceSourceBundleBuilder(repository).build([bct_reference_id])
    bundle = build.bundles[0]
    catalog_text = " ".join(record.text for record in bundle.structured_metadata_scope)
    attestation_text = " ".join(record.text for record in bundle.completed_work_evidence)
    assert "5 applications critiques" in catalog_text
    assert "5 applications critiques" not in attestation_text
    assert bundle.completed_work_evidence
    assert all(
        "COMPLETED_WORK_EVIDENCE" not in {source_type.value for source_type in record.support_types}
        for record in bundle.structured_metadata_scope
        if record.source_label == "Structured catalog scope"
    )
