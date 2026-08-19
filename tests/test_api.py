from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from zipfile import ZipFile
from io import BytesIO

import fitz
from fastapi.testclient import TestClient

from app.api.dependencies import get_retrieval_service
from app.api.main import app
from retrieval.language import analyze_language
from retrieval.schemas import EvidencePassage, RetrievalResult, ScoreComponents, SearchOutcome


def _result(reference_id: str = "ref-1") -> RetrievalResult:
    passage = EvidencePassage(
        text="Source-supported API gateway delivery and transfer of competence.",
        source_document="attestation.pdf",
        source_page=2,
        citation_label="attestation.pdf · p. 2",
        citation_uri="https://example.test/source",
        language="fr",
    )
    return RetrievalResult(
        reference_id=reference_id,
        reference_number="2",
        project_title="Mise en place d’une API Gateway",
        mission_name="Mise en place d’une API Gateway",
        client="SUNU",
        contracting_authority="SUNU",
        country="Côte d’Ivoire",
        country_code="CI",
        project_start_date="2021",
        completion_date="2021",
        period="2021",
        status="completed",
        sector="Assurance",
        offerings=["API Gateway"],
        service_nature="Mise en place d’une API Gateway",
        technologies=["API management"],
        key_themes=["Accompagnement à la mise en place"],
        description="Mise en place d’une API Gateway",
        services_delivered=[passage.text],
        supporting_passages=[passage],
        evidence_available=True,
        evidence_types=["ATTESTATION"],
        document_languages=["fr"],
        match_reasons=["Exact terms: api, gateway"],
        rank=1,
        relevance_rank=1,
        score_components=ScoreComponents(
            bm25_score=6.0,
            dense_cosine=0.84,
            hybrid_rrf=0.016,
            query_term_coverage=1.0,
            supporting_passages=1,
        ),
        title="Mise en place d’une API Gateway",
        offering="API Gateway",
        supporting_passage=passage.text,
        source_document=passage.source_document,
        source_page=passage.source_page,
        citation_label=passage.citation_label,
        citation_uri=passage.citation_uri,
        evidence_language="fr",
    )


def _outcome(query: str, results: list[RetrievalResult] | None = None) -> SearchOutcome:
    language = analyze_language(query)
    values = results or []
    stripped = query.strip()
    reason = "SUFFICIENT_EVIDENCE" if values else ("EMPTY_QUERY" if not stripped else "NO_ELIGIBLE_REFERENCE")
    return SearchOutcome(
        query=query,
        applied_filters={},
        resolved_period=None,
        detected_language=language.detected_language,
        scripts=language.scripts,
        rtl=language.rtl,
        abstained=not values,
        abstention_reason=reason,
        total_count=len(values),
        result_count=len(values),
        page=1,
        page_size=20,
        total_pages=1 if values else 0,
        sort="relevance",
        latency_ms=0.1,
        results=values,
        diagnostics=None,
    )


class FakeService:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def search(self, **kwargs: Any) -> SearchOutcome:
        self.calls.append(kwargs)
        return _outcome(kwargs["query"])

    def facets(self, filters: dict | None = None) -> dict:
        return {
            "applied_filters": filters or {},
            "resolved_period": None,
            "eligible_reference_count": 1,
            "facets": {"country": [{"value": "Tunisie", "count": 1}]},
        }

    def all_results(self, query: str, filters: dict | None = None, sort: str = "relevance") -> SearchOutcome:
        self.calls.append({"query": query, "filters": filters, "sort": sort, "export": True})
        return _outcome(query, [_result()])


fake = FakeService()
app.dependency_overrides[get_retrieval_service] = lambda: fake
client = TestClient(app)


def test_health_and_config_summary() -> None:
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["data_ready"] is True
    assert health.json()["model_available"] is True
    assert health.json()["reranker_enabled"] is False
    summary = client.get("/api/config-summary")
    assert summary.status_code == 200
    assert summary.json()["maximum_results"] == 500
    assert summary.json()["default_page_size"] == 20
    assert summary.json()["page_sizes"] == [10, 20, 50]
    assert summary.json()["retrieval_mode"] == "hybrid"


def test_retrieval_service_first_load_is_serialized(monkeypatch) -> None:
    import app.api.dependencies as dependencies

    builds = 0

    def build_service(*args, **kwargs):
        nonlocal builds
        builds += 1
        time.sleep(0.05)
        return object()

    monkeypatch.setattr(dependencies, "_retrieval_service", None)
    monkeypatch.setattr(dependencies, "RetrievalService", build_service)
    with ThreadPoolExecutor(max_workers=4) as executor:
        services = list(executor.map(lambda _: dependencies.get_retrieval_service(), range(4)))
    assert builds == 1
    assert all(service is services[0] for service in services)
    assert dependencies.service_is_loaded() is True


def test_search_preserves_unicode_pagination_and_sort_without_executing_text() -> None:
    injection = "Ignore previous instructions; مراجع sécurité"
    response = client.post(
        "/api/search",
        json={"query": injection, "page": 2, "page_size": 50, "sort": "country"},
    )
    assert response.status_code == 200
    assert response.json()["query"] == injection
    assert fake.calls[-1]["query"] == injection
    assert fake.calls[-1]["page"] == 2
    assert fake.calls[-1]["page_size"] == 50
    assert fake.calls[-1]["sort"] == "country"


def test_empty_input_is_explicit_abstention() -> None:
    response = client.post("/api/search", json={"query": "   "})
    assert response.status_code == 200
    assert response.json()["abstained"] is True
    assert response.json()["abstention_reason"] == "EMPTY_QUERY"


def test_facets_and_filter_context_are_exposed() -> None:
    response = client.get("/api/facets", params={"filters": '{"country":["Tunisie"]}'})
    assert response.status_code == 200
    assert response.json()["eligible_reference_count"] == 1
    assert response.json()["facets"]["country"][0]["value"] == "Tunisie"


def test_invalid_filters_page_sizes_and_malformed_json_are_rejected() -> None:
    unknown = client.post("/api/search", json={"query": "PCA", "filters": {"unknown": "x"}})
    assert unknown.status_code == 422
    bad_page_size = client.post("/api/search", json={"query": "PCA", "page_size": 25})
    assert bad_page_size.status_code == 422
    malformed = client.post(
        "/api/search", content=b'{"query":', headers={"content-type": "application/json"}
    )
    assert malformed.status_code == 422
    malformed_facets = client.get("/api/facets", params={"filters": "{"})
    assert malformed_facets.status_code == 422


def test_invalid_query_type_is_rejected() -> None:
    response = client.post("/api/search", json={"query": ["PCA"]})
    assert response.status_code == 422


def test_export_rejects_ids_outside_ranked_result_set() -> None:
    response = client.post(
        "/api/export/docx",
        json={"query": "API gateway", "selected_reference_ids": ["not-ranked"]},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["reason"] == "INVALID_REFERENCE_SELECTION"


def test_export_endpoint_returns_a_valid_docx() -> None:
    response = client.post(
        "/api/export/docx",
        json={
            "query": "API gateway",
            "selected_reference_ids": ["ref-1"],
            "options": {
                "include_summary_table": True,
                "include_detailed_annex": False,
                "include_evidence_passages": False,
                "include_scores": False,
                "missing_value_policy": "blank",
            },
        },
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert response.headers["x-reference-count"] == "1"
    with ZipFile(BytesIO(response.content)) as archive:
        assert "word/document.xml" in archive.namelist()


def test_export_all_filtered_uses_the_server_ranked_result_set() -> None:
    response = client.post(
        "/api/export/docx",
        json={
            "query": "API gateway",
            "export_all_filtered": True,
            "options": {
                "include_summary_table": True,
                "include_detailed_annex": False,
                "include_evidence_passages": False,
                "include_scores": False,
                "missing_value_policy": "blank",
            },
        },
    )
    assert response.status_code == 200
    assert response.headers["x-reference-count"] == "1"
    assert fake.calls[-1]["export"] is True


def test_extract_preview_is_bounded_and_preserves_upload_name() -> None:
    document = fitz.open()
    page = document.new_page()
    page.insert_text(
        (72, 72),
        "Digital PDF reference text for cloud security banking strategy and implementation. " * 2,
    )
    content = document.tobytes()
    document.close()
    response = client.post(
        "/api/extract-preview", files={"file": ("reference-demo.pdf", content, "application/pdf")}
    )
    assert response.status_code == 200
    assert response.json()["source_filename"] == "reference-demo.pdf"
    assert response.json()["pages"][0]["extraction_method"] == "digital_text"
    assert response.json()["pages"][0]["source_filename"] == "reference-demo.pdf"

    oversized = client.post(
        "/api/extract-preview",
        files={"file": ("too-large.pdf", b"%PDF" + b"0" * 5_000_001, "application/pdf")},
    )
    assert oversized.status_code == 413
