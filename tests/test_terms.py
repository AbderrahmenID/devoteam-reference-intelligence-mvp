from __future__ import annotations

from retrieval.bm25 import BM25Index
from retrieval.terms import (
    analyze_query_terms,
    exact_match_bonus,
    matched_meaningful_terms,
)


SETTINGS = {
    "minimum_idf": 0.5,
    "maximum_document_frequency_ratio": 0.62,
    "exact_match_bonus_per_term": 0.04,
    "maximum_exact_match_bonus": 0.12,
}


def _analysis(query: str, corpus: list[str]):
    return analyze_query_terms(query, BM25Index.build(corpus), SETTINGS)


def test_french_english_and_arabic_stopwords_are_excluded() -> None:
    corpus = [
        "PCA banque cloud implementation",
        "API gateway security",
        "استمرارية الأعمال للبنوك",
        "unrelated delivery evidence",
    ]
    french = _analysis("PCA pour une banque avec le client", corpus)
    english = _analysis("cloud for the bank with a client", corpus)
    arabic = _analysis("استمرارية الأعمال في البنوك ومن أجل العميل", corpus)
    assert {"pour", "une", "avec", "le"} <= set(french.removed_stopwords)
    assert {"for", "the", "with"} <= set(english.removed_stopwords)
    assert {"في", "من"} <= set(arabic.removed_stopwords)
    assert not ({"pour", "une", "for", "the", "في", "من"} & set(
        french.bm25_tokens + english.bm25_tokens + arabic.bm25_tokens
    ))


def test_whole_token_matching_does_not_use_substrings() -> None:
    analysis = _analysis("API", ["API gateway", "capital planning", "unrelated evidence"])
    assert matched_meaningful_terms(analysis, "A capital planning exercise") == []
    assert [term.display for term in matched_meaningful_terms(analysis, "An API Gateway")] == ["API"]


def test_acronyms_technology_names_and_alphanumeric_terms_are_preserved() -> None:
    values = "API Gateway SI PCA IAM SOC ERP CRM IPv6 Kong Azure ISO 27001 RGPD Kubernetes"
    analysis = _analysis(values, [values, "ordinary unrelated text", "another source passage"])
    assert {"api", "si", "pca", "iam", "soc", "erp", "crm", "ipv6", "27001"} <= set(
        analysis.bm25_tokens
    )
    categories = {term.display: term.category for term in analysis.meaningful_terms}
    assert categories["API"] == "acronym"
    assert categories["PCA"] == "acronym"
    assert categories["API Gateway"] == "technology"
    assert categories["ISO 27001"] == "technology"


def test_high_frequency_terms_are_rejected_by_corpus_statistics() -> None:
    analysis = _analysis(
        "common specialist",
        ["common specialist", "common other", "common third", "common fourth"],
    )
    assert "common" in analysis.rejected_common_terms
    assert "common" not in analysis.bm25_tokens
    assert "specialist" in analysis.bm25_tokens


def test_stopwords_never_add_exact_match_bonus_or_explanations() -> None:
    analysis = _analysis(
        "PCA pour une banque",
        ["PCA pour une banque", "cloud migration", "security assessment"],
    )
    matches = matched_meaningful_terms(analysis, "Une mission pour la banque avec PCA")
    assert {term.normalized for term in matches} == {"pca", "banque"}
    assert exact_match_bonus(analysis, "pour une", SETTINGS) == 0.0
    assert exact_match_bonus(analysis, "PCA pour une banque", SETTINGS) == 0.08
