from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .normalization import normalize_search_text, tokenize_multilingual


@dataclass(frozen=True)
class AbstentionDecision:
    abstained: bool
    reason: str
    features: dict[str, Any]


def invalid_query_decision(query: object, maximum_length: int) -> AbstentionDecision | None:
    if not isinstance(query, str):
        return AbstentionDecision(True, "MALFORMED_QUERY", {"query_type": type(query).__name__})
    stripped = query.strip()
    if not stripped:
        return AbstentionDecision(True, "EMPTY_QUERY", {"query_length": len(query)})
    if len(stripped) > maximum_length:
        return AbstentionDecision(
            True, "QUERY_TOO_LONG", {"query_length": len(stripped), "maximum_length": maximum_length}
        )
    if any(ord(character) < 32 and character not in "\t\n\r" for character in stripped):
        return AbstentionDecision(True, "MALFORMED_QUERY", {"contains_control_characters": True})
    return None


def decide_abstention(query: str, features: dict[str, Any], config: dict) -> AbstentionDecision:
    settings = config["abstention"]
    tokens = tokenize_multilingual(query)
    diagnostics = dict(features)
    diagnostics["query_token_count"] = len(tokens)
    normalized_query = normalize_search_text(query)
    if any(normalize_search_text(term) in normalized_query for term in settings["unsupported_scope_terms"]):
        return AbstentionDecision(True, "UNSUPPORTED_PORTFOLIO_SCOPE", diagnostics)
    if features.get("eligible_chunks", 0) == 0 or features.get("candidate_references", 0) == 0:
        return AbstentionDecision(True, "NO_ELIGIBLE_REFERENCE", diagnostics)

    bm25 = float(features.get("best_bm25", 0.0))
    dense = float(features.get("best_dense", -1.0))
    mean_dense = float(features.get("mean_top_dense", -1.0))
    coverage = float(features.get("best_term_coverage", 0.0))
    agreement = int(features.get("retriever_agreement", 0))
    exact_override = bm25 >= float(settings["exact_term_override_bm25"]) and coverage > 0
    semantic_override = (
        dense >= float(settings["strong_dense_score"])
        and mean_dense >= float(settings["minimum_mean_top_dense"])
    )
    lexical_ok = bm25 >= float(settings["minimum_best_bm25"]) and coverage >= float(
        settings["minimum_query_term_coverage"]
    )
    semantic_ok = dense >= float(settings["minimum_semantic_only_dense"])

    if not lexical_ok and not semantic_ok and not exact_override and not semantic_override:
        reason = "INSUFFICIENT_LEXICAL_EVIDENCE" if dense >= float(settings["minimum_best_dense"]) else "INSUFFICIENT_SEMANTIC_EVIDENCE"
        return AbstentionDecision(True, reason, diagnostics)
    if not (exact_override or semantic_override) and agreement < int(settings["minimum_rrf_agreement"]):
        return AbstentionDecision(True, "LOW_RETRIEVER_AGREEMENT", diagnostics)
    if int(features.get("independent_passages", 0)) < int(settings["minimum_independent_passages"]):
        return AbstentionDecision(True, "NO_ELIGIBLE_REFERENCE", diagnostics)
    return AbstentionDecision(False, "SUFFICIENT_EVIDENCE", diagnostics)

