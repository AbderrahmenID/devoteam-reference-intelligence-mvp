from retrieval.abstention import decide_abstention, invalid_query_decision


CONFIG = {
    "abstention": {
        "minimum_best_bm25": 1.2,
        "minimum_best_dense": 0.70,
        "strong_dense_score": 0.82,
        "minimum_semantic_only_dense": 0.76,
        "minimum_query_term_coverage": 0.18,
        "minimum_mean_top_dense": 0.64,
        "minimum_rrf_agreement": 1,
        "exact_term_override_bm25": 4.0,
        "minimum_independent_passages": 1,
        "unsupported_scope_terms": ["recette de cuisine"],
    }
}


def test_invalid_queries_have_explicit_reasons() -> None:
    assert invalid_query_decision("   ", 100).reason == "EMPTY_QUERY"
    assert invalid_query_decision("x" * 101, 100).reason == "QUERY_TOO_LONG"
    assert invalid_query_decision("valid", 100) is None


def test_accepts_supported_evidence_and_can_return_zero() -> None:
    supported = {
        "eligible_chunks": 10, "candidate_references": 3, "best_bm25": 6.0,
        "best_dense": 0.83, "mean_top_dense": 0.80, "best_term_coverage": 0.5,
        "retriever_agreement": 2, "independent_passages": 2,
    }
    decision = decide_abstention("PCA banque", supported, CONFIG)
    assert not decision.abstained and decision.reason == "SUFFICIENT_EVIDENCE"

    unsupported = supported | {"best_bm25": 0.0, "best_dense": 0.65, "best_term_coverage": 0.0}
    decision = decide_abstention("quantum particles", unsupported, CONFIG)
    assert decision.abstained and decision.reason == "INSUFFICIENT_SEMANTIC_EVIDENCE"


def test_unsupported_scope_has_deterministic_gate() -> None:
    features = {"eligible_chunks": 10, "candidate_references": 2}
    decision = decide_abstention("recette de cuisine au chocolat", features, CONFIG)
    assert decision.abstained and decision.reason == "UNSUPPORTED_PORTFOLIO_SCOPE"

