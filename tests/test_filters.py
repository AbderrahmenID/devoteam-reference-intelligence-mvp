from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import yaml

from retrieval.metadata import ReferenceMetadataIndex, normalize_search_text
from retrieval.service import RetrievalService


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def metadata() -> ReferenceMetadataIndex:
    return ReferenceMetadataIndex(
        pd.read_parquet(ROOT / "data/reference_catalog.parquet"),
        pd.read_parquet(ROOT / "data/chunks.parquet"),
        current_year=2026,
    )


@pytest.fixture(scope="module")
def service() -> RetrievalService:
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    return RetrievalService(ROOT, config)


def test_facets_are_source_derived_and_country_aliases_are_canonical(metadata: ReferenceMetadataIndex) -> None:
    facets = metadata.facets()
    countries = {item["value"]: item["count"] for item in facets["country"]}
    assert len(metadata.all_ids) == 138
    assert "Côte d’Ivoire" in countries
    assert "COTE D’IVOIRE" not in countries
    assert "tunisie" not in countries and "Tunisie" in countries
    assert facets["period"]["min_year"] == 2011
    assert facets["period"]["max_year"] == 2022
    ids, applied, _ = metadata.resolve_filters({"country": ["Cote d'Ivoire"]})
    assert ids and applied["country"] == ["Côte d’Ivoire"]


def test_filters_use_or_within_category_and_and_across_categories(metadata: ReferenceMetadataIndex) -> None:
    ids, applied, _ = metadata.resolve_filters(
        {"country": ["Tunisie", "Maroc"], "offering": ["PCA/PCI"]}
    )
    assert ids
    assert applied["country"] == ["Tunisie", "Maroc"]
    for reference_id in ids:
        reference = metadata.by_id[reference_id]
        assert reference.country in {"Tunisie", "Maroc"}
        assert reference.offering == "PCA/PCI"


def test_unknown_filter_values_are_rejected(metadata: ReferenceMetadataIndex) -> None:
    with pytest.raises(ValueError, match="Unknown country"):
        metadata.resolve_filters({"country": ["Atlantis"]})
    with pytest.raises(ValueError, match="Unknown technology"):
        metadata.resolve_filters({"technology": ["Imaginary Mainframe"]})


def test_period_uses_closed_interval_overlap(metadata: ReferenceMetadataIndex) -> None:
    ids, _, resolved = metadata.resolve_filters({"period": {"start_year": 2020, "end_year": 2020}})
    assert resolved == {"start_year": 2020, "end_year": 2020}
    assert ids
    assert all(
        metadata.by_id[reference_id].start_year <= 2020 <= metadata.by_id[reference_id].end_year
        for reference_id in ids
    )
    spanning = [
        metadata.by_id[reference_id]
        for reference_id in ids
        if metadata.by_id[reference_id].start_year < 2020 < metadata.by_id[reference_id].end_year
    ]
    assert spanning, "A spanning project must match at the interval boundary"


def test_relative_period_presets_resolve_against_local_current_year(metadata: ReferenceMetadataIndex) -> None:
    ids, applied, resolved = metadata.resolve_filters({"period": {"preset": "last_3_years"}})
    assert resolved == {"start_year": 2024, "end_year": 2026}
    assert applied["period"] == resolved
    assert ids == set()


def test_last_five_years_includes_boundary_overlap(metadata: ReferenceMetadataIndex) -> None:
    ids, _, resolved = metadata.resolve_filters({"period": {"preset": "last_5_years"}})
    assert resolved == {"start_year": 2022, "end_year": 2026}
    assert ids
    assert any(metadata.by_id[reference_id].end_year == 2022 for reference_id in ids)


def test_ongoing_and_completed_status_use_explicit_interval_semantics() -> None:
    references = pd.DataFrame([
        {
            "reference_id": "ongoing-ref", "row_number": 1,
            "document_retrieval_eligible": True, "evidence_available": True,
            "reference_number": "1", "service_nature": "Ongoing cloud mission",
            "offering": "Cloud", "client": "Client A", "country": "Tunisie",
            "sector": "Banque", "business_unit": "Digital impulse",
            "project_year": "2022-Présent", "attestation_available": "Contrat",
            "data_quality_status": "PASS",
        },
        {
            "reference_id": "completed-ref", "row_number": 2,
            "document_retrieval_eligible": True, "evidence_available": True,
            "reference_number": "2", "service_nature": "Completed cloud mission",
            "offering": "Cloud", "client": "Client B", "country": "Maroc",
            "sector": "Banque", "business_unit": "Digital impulse",
            "project_year": "2023, 2024", "attestation_available": "PV",
            "data_quality_status": "PASS",
        },
    ])
    chunks = pd.DataFrame([
        {"reference_rows_json": "[1]", "document_language": "fr", "document_type": "CONTRACT", "chunk_text": "ongoing cloud source"},
        {"reference_rows_json": "[2]", "document_language": "fr", "document_type": "MINUTES", "chunk_text": "completed cloud source"},
    ])
    index = ReferenceMetadataIndex(references, chunks, current_year=2026)
    ongoing = index.by_id["ongoing-ref"]
    assert ongoing.status == "ongoing" and ongoing.start_year == 2022 and ongoing.end_year == 2026
    assert index.by_id["completed-ref"].status == "completed"
    ongoing_ids, _, _ = index.resolve_filters({"status": ["ongoing"]})
    completed_ids, _, _ = index.resolve_filters({"status": ["completed"]})
    assert ongoing_ids == {"ongoing-ref"}
    assert completed_ids == {"completed-ref"}
    recent_ids, _, _ = index.resolve_filters({"period": {"preset": "last_3_years"}})
    assert recent_ids == {"ongoing-ref", "completed-ref"}


def test_derived_status_and_technology_are_auditable(metadata: ReferenceMetadataIndex) -> None:
    assert {reference.status for reference in metadata.by_id.values()} <= {"completed", None}
    api_ids, _, _ = metadata.resolve_filters({"technology": ["API management"]})
    assert api_ids
    for reference_id in api_ids:
        reference = metadata.by_id[reference_id]
        assert "API management" in reference.technologies


def test_source_supported_sector_client_offering_theme_and_evidence_filters(metadata: ReferenceMetadataIndex) -> None:
    target = next(
        reference
        for reference in metadata.by_id.values()
        if reference.sector and reference.client and reference.offering
        and reference.key_themes and reference.evidence_types
    )
    checks = {
        "sector": target.sector,
        "client": target.client,
        "offering": target.offering,
        "themes": target.key_themes[0],
        "evidence_type": target.evidence_types[0],
    }
    for category, value in checks.items():
        ids, _, _ = metadata.resolve_filters({category: [value]})
        assert target.reference_id in ids, category


def test_zero_eligible_set_is_a_valid_explicit_abstention(service: RetrievalService) -> None:
    outcome = service.search(
        "PCA banque",
        filters={"period": {"start_year": 2099, "end_year": 2099}},
        page=1,
        page_size=20,
    )
    assert outcome.abstained
    assert outcome.abstention_reason == "NO_ELIGIBLE_REFERENCE"
    assert outcome.total_count == 0 and outcome.results == []


def test_complete_gated_results_are_paginated_without_a_three_result_cap(service: RetrievalService) -> None:
    first = service.search("PCA banque", page=1, page_size=10)
    second = service.search("PCA banque", page=2, page_size=10)
    assert not first.abstained
    assert first.total_count > 3
    assert first.result_count == 10
    assert second.result_count > 0
    assert {result.reference_id for result in first.results}.isdisjoint(
        {result.reference_id for result in second.results}
    )
    assert [result.rank for result in first.results] == list(range(1, 11))
    assert second.results[0].rank == 11


def test_hard_filter_cannot_leak_disallowed_references(service: RetrievalService) -> None:
    outcome = service.search(
        "PCA banque",
        filters={"country": ["Tunisie"], "offering": ["PCA/PCI"]},
        page=1,
        page_size=50,
    )
    assert outcome.total_count > 0
    assert all(result.country == "Tunisie" for result in outcome.results)
    assert all(result.offerings == ["PCA/PCI"] for result in outcome.results)


def test_all_pages_have_stable_totals_ranks_citations_and_no_duplicates(service: RetrievalService) -> None:
    first = service.search("PCA banque", page=1, page_size=10)
    collected = []
    totals = set()
    for page in range(1, first.total_pages + 1):
        outcome = service.search("PCA banque", page=page, page_size=10)
        totals.add(outcome.total_count)
        collected.extend(outcome.results)
    ids = [result.reference_id for result in collected]
    assert totals == {first.total_count}
    assert len(ids) == len(set(ids)) == first.total_count
    assert [result.rank for result in collected] == list(range(1, first.total_count + 1))
    assert all(
        result.supporting_passages
        and result.source_document
        and result.source_page > 0
        and result.citation_uri
        for result in collected
    )


def test_sort_modes_are_deterministic_and_gating_remains_active(service: RetrievalService) -> None:
    for sort in ("relevance", "newest", "oldest", "project_title", "client", "country"):
        first = service.search("PCA banque", page=1, page_size=50, sort=sort)
        second = service.search("PCA banque", page=1, page_size=50, sort=sort)
        assert [result.reference_id for result in first.results] == [
            result.reference_id for result in second.results
        ]
    eligible_ids, _, _ = service.metadata.resolve_filters({"country": ["Tunisie"]})
    outcome = service.search("API gateway Kong", filters={"country": ["Tunisie"]}, page_size=50)
    assert outcome.total_count < len(eligible_ids)


def test_stopword_explanations_and_corrupt_baseline_passage_are_removed(service: RetrievalService) -> None:
    outcome = service.search("Références PCA pour une banque", page=1, page_size=50)
    assert outcome.results
    assert all("Exact terms:" not in reason for result in outcome.results for reason in result.match_reasons)
    assert all(reason.casefold() not in {"pour", "une"} for result in outcome.results for reason in result.match_reasons)
    assert all(
        value.casefold() not in {"pour", "une"}
        for result in outcome.results
        for detail in result.match_details
        for value in detail.values
    )
    biat = next(result for result in outcome.results if result.source_document == "BIAT_MCO.pdf")
    assert "ARTICLE 1 : OBJET" in biat.supporting_passage
    assert not biat.supporting_passage.startswith("( RE ee")
    assert all(result.supporting_passages and result.match_details for result in outcome.results)


def test_stopword_only_query_cannot_pass_relevance_or_evidence_gates(service: RetrievalService) -> None:
    outcome = service.search(
        "pour une de la",
        filters={"country": ["Tunisie"]},
        page=1,
        page_size=20,
    )
    assert outcome.abstained
    assert outcome.total_count == 0 and outcome.results == []
