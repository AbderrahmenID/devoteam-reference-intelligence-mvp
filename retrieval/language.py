from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)
FRENCH_HINTS = {
    "de", "la", "le", "les", "des", "du", "une", "et", "en", "pour", "dans",
    "sur", "avec", "au", "aux", "référence", "projet", "mission", "banque", "sécurité",
}
ENGLISH_HINTS = {
    "the", "of", "and", "to", "in", "for", "on", "with", "is", "are", "reference",
    "project", "bank", "security", "strategy", "implementation", "cloud",
}


@dataclass(frozen=True)
class LanguageInfo:
    detected_language: str
    scripts: list[str]
    rtl: bool
    mixed_script: bool
    arabic_ratio: float
    latin_ratio: float


def _script_name(character: str) -> str | None:
    if not character.isalpha():
        return None
    name = unicodedata.name(character, "")
    if "ARABIC" in name:
        return "Arabic"
    if "LATIN" in name:
        return "Latin"
    if "CYRILLIC" in name:
        return "Cyrillic"
    if "HEBREW" in name:
        return "Hebrew"
    return "Other"


def analyze_language(text: str) -> LanguageInfo:
    normalized = unicodedata.normalize("NFKC", str(text or ""))
    script_counts: dict[str, int] = {}
    for character in normalized:
        script = _script_name(character)
        if script:
            script_counts[script] = script_counts.get(script, 0) + 1
    letters = max(sum(script_counts.values()), 1)
    arabic_ratio = script_counts.get("Arabic", 0) / letters
    latin_ratio = script_counts.get("Latin", 0) / letters
    scripts = sorted(script_counts, key=lambda value: (-script_counts[value], value))
    mixed = script_counts.get("Arabic", 0) > 0 and script_counts.get("Latin", 0) > 0

    words = [word.casefold() for word in WORD_RE.findall(normalized)]
    french_score = sum(word in FRENCH_HINTS for word in words)
    english_score = sum(word in ENGLISH_HINTS for word in words)
    if re.search(r"[àâçéèêëîïôùûüÿœ]", normalized.casefold()):
        french_score += 2

    if mixed:
        language = "mixed"
    elif arabic_ratio >= 0.5:
        language = "ar"
    elif latin_ratio >= 0.4:
        language = "fr" if french_score > english_score else "en"
    else:
        language = "und"
    return LanguageInfo(
        detected_language=language,
        scripts=scripts,
        rtl=arabic_ratio > latin_ratio and arabic_ratio >= 0.5,
        mixed_script=mixed,
        arabic_ratio=round(arabic_ratio, 4),
        latin_ratio=round(latin_ratio, 4),
    )


def is_rtl(text: str) -> bool:
    return analyze_language(text).rtl

