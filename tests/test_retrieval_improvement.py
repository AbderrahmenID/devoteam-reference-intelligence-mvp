from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from app.api.settings import load_config
from retrieval.aggregation import aggregate_reference
from retrieval.bm25 import BM25Index
from retrieval.field_bm25 import FieldAwareBM25
from retrieval.evidence import derive_display_text
from retrieval.metadata import NormalizedReference
from retrieval.relevance import decide_relevance
from retrieval.terms import analyze_query_terms


TERM_SETTINGS = {
    "minimum_idf": 0.0,
    "maximum_document_frequency_ratio": 1.0,
    "exact_match_bonus_per_term": 0.04,
    "maximum_exact_match_bonus": 0.12,
}


def _reference(reference_id: str, title: str, technology: str = "") -> NormalizedReference:
    return NormalizedReference(
        reference_id=reference_id,
        row_number=1 if reference_id == "api" else 2,
        reference_number=None,
        project_title=title,
        mission_name=title,
        client="Generic client",
        country="Tunisie",
        country_code="TN",
        sector="Banque",
        offering="AMOA",
        service_nature=title,
        business_unit="Digital impulse",
        start_year=2022,
        end_year=2024,
        source_end_year=2024,
        period="2022–2024",
        status="completed",
        evidence_available=True,
        evidence_types=["ATTESTATION"],
        document_languages=["fr"],
        technologies=[technology] if technology else [],
        key_themes=[],
        data_quality_status="PASS",
        linked_chunk_indices=[0] if reference_id == "api" else [1],
    )


def test_field_aware_bm25_prioritizes_title_and_exact_technology() -> None:
    metadata = SimpleNamespace(
        by_id={
            "api": _reference("api", "Implementation API Gateway Kong", "API management"),
            "generic": _reference("generic", "Generic transformation programme"),
        }
    )
    chunks = pd.DataFrame(
        [
            {
                "approved_for_retrieval": True,
                "source_file_name": "api.pdf",
                "page_number_1_based": 1,
                "citation_uri": "https://example.test/api#page=1",
                "retrieval_text": "Services delivered include implementation of a Kong API Gateway.",
            },
            {
                "approved_for_retrieval": True,
                "source_file_name": "generic.pdf",
                "page_number_1_based": 1,
                "citation_uri": "https://example.test/generic#page=1",
                "retrieval_text": "A generic client metadata paragraph mentions API once.",
            },
        ]
    )
    settings = {
        "weights": {
            "title": 2.4,
            "mission_name": 2.0,
            "services_delivered": 2.2,
            "description": 1.5,
            "technologies": 2.8,
            "offerings": 1.0,
            "sector": 0.35,
            "client": 0.05,
            "evidence": 0.8,
        },
        "exact_match": {
            "per_term": 0.08,
            "maximum": 0.48,
            "technology_acronym_multiplier": 2.5,
            "field_multipliers": {field: 1.0 for field in (
                "title", "mission_name", "services_delivered", "description",
                "technologies", "offerings", "sector", "client", "evidence",
            )},
        },
    }
    field_index = FieldAwareBM25(metadata, chunks, settings, {"k1": 1.2, "b": 0.75})
    corpus = BM25Index.build(["API Gateway Kong implementation", "generic client paragraph"])
    terms = analyze_query_terms("API Gateway Kong", corpus, TERM_SETTINGS)
    scores = field_index.score(terms, {"api", "generic"})
    assert scores.combined[scores.reference_ids.index("api")] > scores.combined[
        scores.reference_ids.index("generic")
    ]
    assert "api" in scores.exact_matches["api"]["title"]


def test_reference_aggregation_rewards_coherent_second_support_without_requiring_it() -> None:
    def evidence(chunk_id: str, fused: float, coverage: float) -> dict:
        return {
            "chunk": {"chunk_id": chunk_id},
            "fused": fused,
            "dense": 0.8,
            "coverage": coverage,
            "selection_score": 0.9,
        }

    single = aggregate_reference(
        [evidence("one", 0.015, 1.0)], strategy="C_BEST_PLUS_SUPPORT"
    )
    multiple = aggregate_reference(
        [evidence("one", 0.015, 1.0), evidence("two", 0.014, 0.5)],
        strategy="C_BEST_PLUS_SUPPORT",
    )
    assert single.score > 0
    assert multiple.score > single.score
    assert multiple.supporting_chunk_id == "two"


def test_conservative_gate_rejects_single_accidental_semantic_neighbor() -> None:
    config = {
        "abstention": {"unsupported_scope_terms": []},
        "relevance_gate": {
            "minimum_field_lexical": 0.45,
            "minimum_evidence_coverage": 0.12,
            "minimum_agreement_coverage": 0.08,
            "strong_dense": 0.79,
            "minimum_dense_floor": 0.65,
            "technology_dense_floor": 0.65,
        },
    }
    features = {
        "meaningful_query_token_count": 3,
        "clean_evidence_passages": 1,
        "valid_lineage": True,
        "metadata_compatibility": True,
        "strong_exact_term_count": 0,
        "technology_acronym_match_count": 0,
        "best_term_coverage": 0.0,
        "best_bm25": 0.0,
        "best_dense": 0.7,
        "project_specific_evidence": True,
        "reference_retriever_agreement": 0,
        "capability_field_support": 0,
        "evidence_field_support": False,
    }
    decision = decide_relevance("unrelated specialist request", features, config)
    assert not decision.passed
    assert decision.reason in {
        "METADATA_ONLY_MATCH", "SINGLE_ACCIDENTAL_SEMANTIC_NEIGHBOR",
        "INSUFFICIENT_RELEVANCE_EVIDENCE",
    }


def test_default_application_runtime_loads_selected_v2_configuration() -> None:
    load_config.cache_clear()
    config = load_config()
    assert config["data"]["chunks"] == "data/versions/v2/chunks.parquet"
    assert config["field_bm25"]["enabled"] is True
    assert config["hybrid"] == {
        "lexical_weight": 0.75,
        "dense_weight": 0.25,
        "rrf_k": 60,
        "candidate_depth": 2000,
        "per_candidate_agreement_depth": 50,
        "evidence_chunks_per_reference": 3,
    }


def test_professional_display_strips_signature_contact_and_legal_tail() -> None:
    text = (
        "DEVOTEAM a réalisé la mise en place d'une API Gateway Kong et les services "
        "d'architecture associés. Cette attestation est délivrée à l'intéressé pour "
        "servir et valoir ce que de droit. Tél : [PHONE_LIKE]"
    )
    display = derive_display_text(text)
    assert "API Gateway Kong" in display
    assert "servir et valoir" not in display
    assert "PHONE_LIKE" not in display
