from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.api.dependencies import get_reference_narrative_service
from app.api.main import app
from reference_narrative.ollama_client import DisabledNarrativeProvider
from reference_narrative.service import ReferenceNarrativeService

from test_reference_narrative import (
    FakeProvider,
    FakeRepository,
    REF_A,
    _reference_draft,
    _prose_responses,
    _reference_a,
)


def _request_body() -> dict:
    return {
        "selected_reference_ids": [REF_A],
        "opportunity_title": "PCA opportunity",
        "opportunity_description": "A banking continuity requirement.",
        "requirements": [],
        "target_language": "en",
        "tone": "commercial",
        "audience": "executive",
        "detail_level": "short",
    }


def _repository() -> FakeRepository:
    reference, types = _reference_a()
    return FakeRepository([reference], types)


def _editable(body: dict) -> dict:
    narrative = body["narrative"]
    return {
        "section_intro": narrative["section_intro"]["text"],
        "overall_storyline": narrative["overall_storyline"]["text"],
        "why_these_references": narrative["why_these_references"]["text"],
        "references": [
            {
                "headline": reference["headline"]["text"],
                "short_description": reference["short_description"]["text"],
                "challenge": reference["challenge"]["text"],
                "devoteam_contribution": reference["devoteam_contribution"]["text"],
                "realisations": [item["text"] for item in reference["realisations"]],
                "benefits": [item["text"] for item in reference["benefits"]],
                "why_relevant_to_opportunity": reference["why_relevant_to_opportunity"]["text"],
            }
            for reference in narrative["references"]
        ],
    }


def test_generation_endpoint_returns_structured_response() -> None:
    repository = _repository()
    service = ReferenceNarrativeService(
        repository,
        FakeProvider(_prose_responses([REF_A])),
    )
    app.dependency_overrides[get_reference_narrative_service] = lambda: service
    try:
        response = TestClient(app).post("/api/reference-narrative/generate", json=_request_body())
    finally:
        app.dependency_overrides.pop(get_reference_narrative_service, None)
    assert response.status_code == 200
    body = response.json()
    assert body["narrative"]["references"][0]["reference_id"] == REF_A
    assert body["validation"]["valid"] is True
    assert body["source_supports"]
    assert all("text" not in summary for summary in body["source_supports"])


def test_generation_endpoint_reports_disabled_provider_without_breaking_app() -> None:
    service = ReferenceNarrativeService(_repository(), DisabledNarrativeProvider())
    app.dependency_overrides[get_reference_narrative_service] = lambda: service
    try:
        client = TestClient(app)
        response = client.post("/api/reference-narrative/generate", json=_request_body())
        health = client.get("/health")
    finally:
        app.dependency_overrides.pop(get_reference_narrative_service, None)
    assert response.status_code == 503
    assert response.json()["detail"]["reason"] == "REFERENCE_NARRATIVE_DISABLED"
    assert health.status_code == 200


def test_progressive_generation_endpoint_streams_section_reference_and_validation_events() -> None:
    service = ReferenceNarrativeService(_repository(), FakeProvider(_prose_responses([REF_A])))
    app.dependency_overrides[get_reference_narrative_service] = lambda: service
    try:
        response = TestClient(app).post("/api/reference-narrative/generate-stream", json=_request_body())
    finally:
        app.dependency_overrides.pop(get_reference_narrative_service, None)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    events = [json.loads(line) for line in response.text.splitlines()]
    assert [event["event"] for event in events] == [
        "started",
        "unit_started",
        "unit_completed",
        "unit_started",
        "unit_completed",
        "validation_started",
        "completed",
    ]
    assert events[1]["unit"] == "section"
    assert events[3]["reference_id"] == REF_A
    assert events[-1]["review"]["narrative"]["references"][0]["reference_id"] == REF_A


def test_validation_endpoint_rebuilds_identity_support_and_read_only_metadata() -> None:
    repository = _repository()
    generating = ReferenceNarrativeService(repository, FakeProvider(_prose_responses([REF_A])))
    app.dependency_overrides[get_reference_narrative_service] = lambda: generating
    client = TestClient(app)
    try:
        generated = client.post("/api/reference-narrative/generate", json=_request_body()).json()
        editable = _editable(generated)
        editable["references"][0]["devoteam_contribution"] = "The project delivered a positive ROI."
        response = client.post(
            "/api/reference-narrative/validate",
            json={"generation_request": _request_body(), "narrative": editable},
        )
    finally:
        app.dependency_overrides.pop(get_reference_narrative_service, None)

    assert response.status_code == 200
    body = response.json()
    assert body["narrative"]["references"][0]["reference_id"] == REF_A
    assert body["narrative"]["references"][0]["devoteam_contribution"]["support_ids"]
    assert body["reference_metadata"][0]["client"] == "Banque Centrale de Tunisie"
    assert body["validation"]["export_eligible"] is False
    assert "UNSUPPORTED_ROI" in {warning["code"] for warning in body["warnings"]}


def test_validation_endpoint_rejects_browser_identity_or_provenance_fields() -> None:
    service = ReferenceNarrativeService(_repository(), DisabledNarrativeProvider())
    payload = {
        "generation_request": _request_body(),
        "narrative": {
            "section_intro": "Grounded introduction",
            "overall_storyline": "Grounded storyline",
            "why_these_references": "Grounded relevance",
            "references": [
                {
                    "reference_id": REF_A,
                    "headline": "Browser-controlled identity",
                    "short_description": "",
                    "challenge": "",
                    "devoteam_contribution": "",
                    "realisations": [],
                    "benefits": [],
                    "why_relevant_to_opportunity": "",
                    "support_ids": ["S999"],
                }
            ],
        },
    }
    app.dependency_overrides[get_reference_narrative_service] = lambda: service
    try:
        response = TestClient(app).post("/api/reference-narrative/validate", json=payload)
    finally:
        app.dependency_overrides.pop(get_reference_narrative_service, None)

    assert response.status_code == 422


def test_reference_regeneration_changes_only_requested_reference_and_revalidates() -> None:
    repository = _repository()
    generating = ReferenceNarrativeService(repository, FakeProvider(_prose_responses([REF_A])))
    generated = generating.generate(generating_request := generating_request_model())
    provider = FakeProvider([json.dumps(_reference_draft(REF_A, headline="Regenerated grounded headline"))])
    service = ReferenceNarrativeService(repository, provider)
    app.dependency_overrides[get_reference_narrative_service] = lambda: service
    try:
        response = TestClient(app).post(
            "/api/reference-narrative/regenerate",
            json={
                "generation_request": _request_body(),
                "narrative": _editable(generated.model_dump(mode="json")),
                "scope": "reference",
                "reference_id": REF_A,
            },
        )
    finally:
        app.dependency_overrides.pop(get_reference_narrative_service, None)

    assert response.status_code == 200
    assert response.json()["narrative"]["references"][0]["headline"]["text"] == "Regenerated grounded headline"
    assert len(provider.calls) == 1


def generating_request_model():
    from reference_narrative.schemas import NarrativeGenerationRequest

    return NarrativeGenerationRequest.model_validate(_request_body())
