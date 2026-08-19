from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .normalization import normalize_search_text, tokenize_multilingual


@dataclass(frozen=True)
class RelevanceDecision:
    passed: bool
    reason: str
    patterns: list[str]
    features: dict[str, Any]


def decide_relevance(query: str, features: dict[str, Any], config: dict) -> RelevanceDecision:
    settings = config["relevance_gate"]
    diagnostics = dict(features)
    normalized_query = normalize_search_text(query)
    query_tokens = tokenize_multilingual(normalized_query)
    if any(
        (lambda wanted: any(
            query_tokens[index : index + len(wanted)] == wanted
            for index in range(len(query_tokens) - len(wanted) + 1)
        ))(tokenize_multilingual(term))
        for term in config["abstention"]["unsupported_scope_terms"]
    ):
        return RelevanceDecision(False, "UNSUPPORTED_PORTFOLIO_SCOPE", [], diagnostics)
    if int(features.get("meaningful_query_token_count", 0)) == 0:
        return RelevanceDecision(False, "NO_MEANINGFUL_QUERY_TERMS", [], diagnostics)
    if int(features.get("clean_evidence_passages", 0)) == 0:
        return RelevanceDecision(False, "NO_USABLE_EVIDENCE", [], diagnostics)
    if not bool(features.get("valid_lineage", False)):
        return RelevanceDecision(False, "INVALID_SOURCE_LINEAGE", [], diagnostics)
    if features.get("query_concepts") and not bool(features.get("metadata_compatibility")):
        return RelevanceDecision(False, "CAPABILITY_CONTRADICTION", [], diagnostics)

    strong_exact = int(features.get("strong_exact_term_count", 0))
    technology_exact = int(features.get("technology_acronym_match_count", 0))
    evidence_coverage = float(features.get("best_term_coverage", 0.0))
    lexical = float(features.get("best_bm25", 0.0))
    dense = float(features.get("best_dense", -1.0))
    clean_count = int(features.get("clean_evidence_passages", 0))
    project_specific = bool(features.get("project_specific_evidence", False))
    agreement = int(features.get("reference_retriever_agreement", 0))
    capability_field_support = int(features.get("capability_field_support", 0))
    evidence_field_support = bool(features.get("evidence_field_support", False))

    patterns: list[str] = []
    if (
        strong_exact >= 1
        and lexical >= float(settings["minimum_field_lexical"])
        and evidence_coverage >= float(settings["minimum_evidence_coverage"])
        and project_specific
    ):
        patterns.append("PATTERN_A_STRONG_LEXICAL")
    if (
        dense >= float(settings["strong_dense"])
        and bool(features.get("metadata_compatibility", True))
        and (capability_field_support >= 1 or clean_count >= 2)
        and project_specific
    ):
        patterns.append("PATTERN_B_STRONG_SEMANTIC")
    if (
        agreement >= 1
        and evidence_coverage >= float(settings["minimum_agreement_coverage"])
        and project_specific
    ):
        patterns.append("PATTERN_C_RETRIEVER_AGREEMENT")
    if (
        technology_exact >= 1
        and evidence_field_support
        and project_specific
        and (evidence_coverage > 0.0 or dense >= float(settings["technology_dense_floor"]))
    ):
        patterns.append("PATTERN_D_EXACT_CAPABILITY_TECHNOLOGY")

    diagnostics["passing_patterns"] = patterns
    if patterns:
        return RelevanceDecision(True, "SUFFICIENT_RELEVANCE_AND_EVIDENCE", patterns, diagnostics)
    if lexical < float(settings["minimum_field_lexical"]) and dense < float(
        settings["minimum_dense_floor"]
    ):
        reason = "WEAK_LEXICAL_AND_SEMANTIC_SUPPORT"
    elif not project_specific:
        reason = "GENERIC_OR_BOILERPLATE_EVIDENCE"
    elif capability_field_support == 0 and not evidence_field_support:
        reason = "METADATA_ONLY_MATCH"
    elif clean_count == 1 and strong_exact == 0 and agreement == 0:
        reason = "SINGLE_ACCIDENTAL_SEMANTIC_NEIGHBOR"
    else:
        reason = "INSUFFICIENT_RELEVANCE_EVIDENCE"
    return RelevanceDecision(False, reason, [], diagnostics)
