from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Protocol

from .normalization import normalize_search_text, tokenize_multilingual


RAW_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)

FRENCH_STOPWORDS = {
    "a", "afin", "ainsi", "au", "aux", "avec", "ce", "ces", "cette", "comme",
    "dans", "de", "des", "du", "elle", "elles", "en", "est", "et", "il", "ils",
    "la", "le", "les", "leur", "leurs", "mais", "ne", "nous", "ou", "par", "pas",
    "plus", "pour", "que", "qui", "reference", "references", "sa", "se", "ses", "son",
    "sont", "sur", "tout", "toute", "toutes", "tous", "un", "une", "votre", "vous",
}
ENGLISH_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "is",
    "it", "its", "of", "on", "or", "our", "reference", "references", "that", "the",
    "their", "these", "this", "those", "to", "was", "were", "which", "who", "with",
    "your",
}
ARABIC_STOPWORDS = {
    "أن", "إن", "إلى", "أو", "أي", "بعد", "بين", "تم", "ثم", "حول", "ذلك", "على",
    "عن", "في", "قبل", "كان", "كل", "كما", "لا", "لدى", "لن", "لم", "ما", "مع", "من",
    "هذا", "هذه", "هو", "هي", "التي", "الذي", "الذين",
}
STOPWORDS = {
    normalize_search_text(value)
    for value in FRENCH_STOPWORDS | ENGLISH_STOPWORDS | ARABIC_STOPWORDS
}

ACRONYMS = {"api", "si", "pca", "iam", "soc", "erp", "crm", "rgpd"}
TECHNOLOGY_TOKENS = {
    "api", "gateway", "kong", "azure", "iso", "27001", "rgpd", "kubernetes", "ipv6",
    "cloud", "cobit", "itil", "sap", "iam", "soc", "erp", "crm",
}
KNOWN_PHRASES: tuple[tuple[tuple[str, ...], str, str], ...] = (
    (("api", "gateway"), "API Gateway", "technology"),
    (("iso", "27001"), "ISO 27001", "technology"),
    (("core", "banking"), "Core banking", "technology"),
)
CAPABILITY_CONCEPTS: dict[str, tuple[tuple[str, ...], ...]] = {
    "business_continuity": (
        ("pca",), ("pci",), ("plan", "continuite"), ("continuite", "activite"),
        ("business", "continuity"), ("استمراريه", "الاعمال"), ("استمرارية", "الاعمال"),
    ),
    "api_management": (("api", "gateway"), ("api", "management"), ("kong",)),
    "cloud": (("cloud",), ("infonuagique",)),
    "cybersecurity": (("cybersecurite",), ("cybersecurity",), ("securite", "si"), ("امن", "المعلومات")),
}
CONCEPT_METADATA_ALIASES: dict[str, tuple[tuple[str, ...], ...]] = {
    "business_continuity": (
        ("pca",), ("pci",), ("continuite", "activite"), ("business", "continuity"),
        ("استمراريه", "الاعمال"), ("استمرارية", "الاعمال"),
    ),
    "api_management": (("api",), ("gateway",), ("kong",)),
    "cloud": (("cloud",), ("infonuagique",)),
    "cybersecurity": (("cyber",), ("securite",), ("security",)),
}


class CorpusTerms(Protocol):
    vocabulary: list[str]
    idf: Any
    offsets: Any
    document_count: int


@dataclass(frozen=True)
class MeaningfulTerm:
    normalized: str
    display: str
    category: str
    idf: float
    document_frequency: int
    document_frequency_ratio: float


@dataclass(frozen=True)
class QueryTermAnalysis:
    normalized_query: str
    raw_tokens: list[str]
    bm25_tokens: list[str]
    meaningful_terms: list[MeaningfulTerm]
    removed_stopwords: list[str]
    rejected_common_terms: list[str]
    rejected_out_of_vocabulary: list[str]
    concepts: list[str]

    @property
    def meaningful_token_set(self) -> set[str]:
        return {term.normalized for term in self.meaningful_terms if " " not in term.normalized}

    def diagnostics(self) -> dict[str, Any]:
        return {
            "normalized_query": self.normalized_query,
            "raw_tokens": self.raw_tokens,
            "bm25_tokens": self.bm25_tokens,
            "removed_stopwords": self.removed_stopwords,
            "rejected_common_terms": self.rejected_common_terms,
            "rejected_out_of_vocabulary": self.rejected_out_of_vocabulary,
            "concepts": self.concepts,
            "meaningful_terms": [
                {
                    "normalized": term.normalized,
                    "display": term.display,
                    "category": term.category,
                    "idf": round(term.idf, 6),
                    "document_frequency": term.document_frequency,
                    "document_frequency_ratio": round(term.document_frequency_ratio, 6),
                }
                for term in self.meaningful_terms
            ],
        }


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def analyze_query_terms(query: object, corpus: CorpusTerms, settings: dict[str, Any]) -> QueryTermAnalysis:
    raw = unicodedata.normalize("NFKC", str(query or ""))
    raw_tokens = RAW_TOKEN_RE.findall(raw)
    vocabulary = {term: index for index, term in enumerate(corpus.vocabulary)}
    minimum_idf = float(settings["minimum_idf"])
    maximum_df_ratio = float(settings["maximum_document_frequency_ratio"])
    meaningful: list[MeaningfulTerm] = []
    removed_stopwords: list[str] = []
    rejected_common: list[str] = []
    rejected_oov: list[str] = []
    seen: set[str] = set()

    for raw_token in raw_tokens:
        normalized_tokens = tokenize_multilingual(raw_token)
        if len(normalized_tokens) != 1:
            continue
        normalized = normalized_tokens[0]
        if normalized in seen:
            continue
        seen.add(normalized)
        stopword = normalized if normalized in STOPWORDS else None
        if not stopword and len(normalized) > 2 and normalized[0] in {"و", "ف"}:
            remainder = normalized[1:]
            stopword = remainder if remainder in STOPWORDS else None
        if stopword:
            removed_stopwords.append(stopword)
            continue
        term_index = vocabulary.get(normalized)
        if term_index is None:
            rejected_oov.append(normalized)
            continue
        document_frequency = int(corpus.offsets[term_index + 1] - corpus.offsets[term_index])
        ratio = document_frequency / max(int(corpus.document_count), 1)
        idf = float(corpus.idf[term_index])
        if idf < minimum_idf or ratio > maximum_df_ratio:
            rejected_common.append(normalized)
            continue
        category = "term"
        display = raw_token
        if normalized in ACRONYMS:
            category = "acronym"
            display = normalized.upper()
        elif normalized in TECHNOLOGY_TOKENS:
            category = "technology"
        meaningful.append(
            MeaningfulTerm(normalized, display, category, idf, document_frequency, ratio)
        )

    normalized_sequence = tokenize_multilingual(raw)
    for phrase_tokens, display, category in KNOWN_PHRASES:
        width = len(phrase_tokens)
        if not any(tuple(normalized_sequence[index : index + width]) == phrase_tokens for index in range(len(normalized_sequence) - width + 1)):
            continue
        components = [term for term in meaningful if term.normalized in phrase_tokens]
        if len({term.normalized for term in components}) != len(set(phrase_tokens)):
            continue
        meaningful.append(
            MeaningfulTerm(
                " ".join(phrase_tokens),
                display,
                category,
                min(term.idf for term in components),
                max(term.document_frequency for term in components),
                max(term.document_frequency_ratio for term in components),
            )
        )

    bm25_tokens = [term.normalized for term in meaningful if " " not in term.normalized]
    concepts = [
        concept
        for concept, aliases in CAPABILITY_CONCEPTS.items()
        if any(_contains_phrase(normalized_sequence, list(alias)) for alias in aliases)
    ]
    return QueryTermAnalysis(
        normalized_query=normalize_search_text(raw),
        raw_tokens=raw_tokens,
        bm25_tokens=_dedupe(bm25_tokens),
        meaningful_terms=meaningful,
        removed_stopwords=_dedupe(removed_stopwords),
        rejected_common_terms=_dedupe(rejected_common),
        rejected_out_of_vocabulary=_dedupe(rejected_oov),
        concepts=concepts,
    )


def _contains_phrase(tokens: list[str], phrase: list[str]) -> bool:
    width = len(phrase)
    return any(tokens[index : index + width] == phrase for index in range(len(tokens) - width + 1))


def matched_meaningful_terms(analysis: QueryTermAnalysis, evidence: object) -> list[MeaningfulTerm]:
    evidence_tokens = tokenize_multilingual(evidence)
    evidence_set = set(evidence_tokens)
    matches: list[MeaningfulTerm] = []
    for term in analysis.meaningful_terms:
        parts = term.normalized.split()
        if (len(parts) == 1 and parts[0] in evidence_set) or (len(parts) > 1 and _contains_phrase(evidence_tokens, parts)):
            matches.append(term)
    return matches


def meaningful_term_coverage(analysis: QueryTermAnalysis, evidence: object) -> float:
    wanted = analysis.meaningful_token_set
    if not wanted:
        return 0.0
    present = set(tokenize_multilingual(evidence))
    return len(wanted & present) / len(wanted)


def exact_match_bonus(analysis: QueryTermAnalysis, evidence: object, settings: dict[str, Any]) -> float:
    matched_tokens = {
        term.normalized
        for term in matched_meaningful_terms(analysis, evidence)
        if " " not in term.normalized
    }
    return min(
        len(matched_tokens) * float(settings["exact_match_bonus_per_term"]),
        float(settings["maximum_exact_match_bonus"]),
    )


def meaningful_content_tokens(text: object) -> list[str]:
    return [token for token in tokenize_multilingual(text) if token not in STOPWORDS]


def metadata_supports_concepts(concepts: list[str], metadata_text: object) -> bool:
    if not concepts:
        return True
    tokens = tokenize_multilingual(metadata_text)
    return all(
        any(_contains_phrase(tokens, list(alias)) for alias in CONCEPT_METADATA_ALIASES[concept])
        for concept in concepts
    )
