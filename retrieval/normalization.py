from __future__ import annotations

import json
import re
import unicodedata
from typing import Any, Iterable


TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)
ARABIC_DIACRITICS_RE = re.compile(r"[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed]")
ARABIC_TRANSLATION = str.maketrans(
    {"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ؤ": "و", "ئ": "ي"}
)


def normalize_search_text(value: object) -> str:
    """Return a retrieval-only form while leaving source/evidence text untouched."""
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    text = ARABIC_DIACRITICS_RE.sub("", text).replace("ـ", "")
    text = text.translate(ARABIC_TRANSLATION)
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def tokenize_multilingual(value: object) -> list[str]:
    return [token for token in TOKEN_RE.findall(normalize_search_text(value)) if len(token) >= 2]


def json_values(value: Any) -> list[str]:
    if isinstance(value, list):
        raw = value
    elif value is None or (isinstance(value, float) and value != value):
        raw = []
    else:
        try:
            parsed = json.loads(str(value))
            raw = parsed if isinstance(parsed, list) else [parsed]
        except (TypeError, ValueError, json.JSONDecodeError):
            raw = [value]
    output: list[str] = []
    seen: set[str] = set()
    for item in raw:
        cleaned = " ".join(str(item or "").split()).strip()
        key = normalize_search_text(cleaned)
        if cleaned and key not in seen:
            output.append(cleaned)
            seen.add(key)
    return output


def term_coverage(query: object, evidence: object) -> float:
    query_terms = set(tokenize_multilingual(query))
    if not query_terms:
        return 0.0
    evidence_terms = set(tokenize_multilingual(evidence))
    return len(query_terms & evidence_terms) / len(query_terms)


def exact_term_matches(query: object, evidence: object) -> list[str]:
    query_terms = set(tokenize_multilingual(query))
    evidence_terms = set(tokenize_multilingual(evidence))
    return sorted(query_terms & evidence_terms, key=lambda value: (-len(value), value))


def normalized_set(values: Iterable[object]) -> set[str]:
    return {normalize_search_text(value) for value in values if str(value or "").strip()}

