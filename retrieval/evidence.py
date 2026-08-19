from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass
from typing import Any

from .language import analyze_language
from .normalization import normalize_search_text, tokenize_multilingual
from .terms import (
    QueryTermAnalysis,
    exact_match_bonus,
    meaningful_content_tokens,
    meaningful_term_coverage,
    metadata_supports_concepts,
)


WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)
BULLET_RE = re.compile(r"^(?:[-*•▪◦‣]|\d+[.)])\s+")
SAFE_HYPHEN_RE = re.compile(r"([A-Za-zÀ-ÖØ-öø-ÿ]{3,})-$")
SAFE_CONTINUATION_RE = re.compile(r"^[a-zà-öø-ÿ]{2,}")
ALLOWED_SYMBOLS = set(".,;:!?…'’\"“”()[]{}%€$£¥@&/+–—-·•°№#<>_=:")
PROJECT_EVIDENCE_MARKERS = (
    "objet du contrat", "objet de la mission", "plan de continuite", "services rendus",
    "prestations", "accompagnement", "mise en place", "realisation de la mission",
    "project scope", "services delivered", "implementation", "business continuity",
    "نطاق المشروع", "الخدمات المقدمة", "استمرارية الاعمال", "تنفيذ المشروع",
)
FOCUS_MARKERS = (
    re.compile(r"\bARTICLE\s+\d+\s*:\s*OBJET\b", re.IGNORECASE),
    re.compile(r"\bOBJET\s+(?:DU\s+CONTRAT|DE\s+LA\s+MISSION)\b", re.IGNORECASE),
    re.compile(
        r"\b(?:DEVOTEAM|le\s+Cabinet)\b.{0,90}\b(?:a\s+r[ée]alis[ée]|"
        r"est\s+en\s+cours\s+de\s+r[ée]alisation|nous\s+assiste|a\s+accompagn[ée])\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bproject\s+scope\b", re.IGNORECASE),
    re.compile(r"نطاق\s+المشروع"),
)
CONTACT_OR_SIGNATURE_RE = re.compile(
    r"(?:\b(?:t[ée]l(?:[ée]phone)?|fax|e-?mail|adresse|bo[iî]te\s+postale|bp)\b\s*[:.]|"
    r"\[PHONE_LIKE\]|\b(?:fait\s+[àa]|en\s+foi\s+de\s+quoi|"
    r"(?:cette|la\s+pr[ée]sente)\s+attestation\s+est\s+d[ée]livr[ée]e|"
    r"il\s+y[’']?a(?:\s+eu)?\s+lieu\s+de\s+signaler|"
    r"les\s+experts\s+ayant\s+particip[ée])\b)",
    re.IGNORECASE,
)
LEGAL_BOILERPLATE_MARKERS = (
    "confidentialite",
    "dommages et interets",
    "servir et valoir ce que de droit",
    "juridiction competente",
    "conditions generales",
    "resiliation du contrat",
)


def clean_display_text(value: object) -> str:
    """Derive readable evidence without mutating the source or retrieval text."""
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(
        character
        for character in text
        if character in "\n\t" or unicodedata.category(character)[0] != "C"
    )
    text = re.sub(r"^(?:passage|query)\s*:\s*", "", text, count=1, flags=re.IGNORECASE)
    raw_paragraphs = re.split(r"\n\s*\n+", text)
    paragraphs: list[str] = []
    for raw_paragraph in raw_paragraphs:
        lines = [re.sub(r"[ \t]+", " ", line).strip() for line in raw_paragraph.splitlines()]
        lines = [line for line in lines if line]
        deduplicated: list[str] = []
        seen_short_lines: set[str] = set()
        for line in lines:
            key = normalize_search_text(line)
            if deduplicated and key == normalize_search_text(deduplicated[-1]):
                continue
            if len(line) <= 100 and key in seen_short_lines:
                continue
            if len(line) <= 100:
                seen_short_lines.add(key)
            deduplicated.append(line)
        if not deduplicated:
            continue

        joined = deduplicated[0]
        for line in deduplicated[1:]:
            if SAFE_HYPHEN_RE.search(joined) and SAFE_CONTINUATION_RE.match(line):
                joined = SAFE_HYPHEN_RE.sub(r"\1", joined) + line
            elif BULLET_RE.match(line):
                joined += "\n" + line
            else:
                joined += " " + line
        joined = re.sub(r"[ \t]+", " ", joined).strip()
        if joined:
            paragraphs.append(joined)
    return "\n\n".join(paragraphs)


def focus_display_passage(cleaned_text: object, maximum_characters: int = 700) -> str:
    """Select a source-faithful project/delivery excerpt from a cleaned chunk."""
    text = str(cleaned_text or "").strip()
    matches = [match for pattern in FOCUS_MARKERS if (match := pattern.search(text))]
    if matches:
        text = text[min(match.start() for match in matches) :]
    window = text[: maximum_characters + 1]
    sentence_ends = [
        match.end()
        for match in re.finditer(r"[.!?؟](?=\s|$)", window)
        if not re.search(r"\b(?:m|mr|mme|mlle|dr)\.$", window[max(0, match.end() - 7) : match.end()], re.IGNORECASE)
    ]
    eligible_ends = [end for end in sentence_ends if end >= 120]
    if eligible_ends:
        cutoff = eligible_ends[min(1, len(eligible_ends) - 1)]
    elif len(text) <= maximum_characters:
        return text
    else:
        cutoff = window.rfind(" ", 0, maximum_characters)
        if cutoff < 180:
            cutoff = maximum_characters
    excerpt = text[:cutoff].rstrip(" ,;:")
    return excerpt if cutoff >= len(text) else excerpt + "…"


def derive_display_text(value: object) -> str:
    cleaned = clean_display_text(value)
    match = CONTACT_OR_SIGNATURE_RE.search(cleaned)
    if match and match.start() >= 40:
        cleaned = cleaned[: match.start()].rstrip(" ,;:.-–—")
    return focus_display_passage(cleaned)


@dataclass(frozen=True)
class EvidenceQualityResult:
    quality_pass: bool
    quality_score: float
    rejection_reasons: list[str]
    diagnostics: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class EvidenceQualityEvaluator:
    def __init__(self, settings: dict[str, Any]):
        self.settings = settings

    def evaluate(
        self,
        raw_text: object,
        display_text: object,
        query_terms: QueryTermAnalysis,
        *,
        dense_score: float,
        query_language: str,
        extraction_quality: str | None = None,
    ) -> EvidenceQualityResult:
        raw = unicodedata.normalize("NFKC", str(raw_text or ""))
        display = str(display_text or "")
        characters = list(raw)
        printable_ratio = (
            sum(character.isprintable() or character in "\n\t" for character in characters)
            / max(len(characters), 1)
        )
        visible = [character for character in display if not character.isspace()]
        alphabetic_ratio = sum(character.isalpha() for character in visible) / max(len(visible), 1)
        all_tokens = WORD_RE.findall(display)
        content_tokens = meaningful_content_tokens(display)
        average_token_length = (
            sum(len(token) for token in all_tokens) / max(len(all_tokens), 1)
        )
        single_character_ratio = (
            sum(len(token) == 1 for token in all_tokens) / max(len(all_tokens), 1)
        )
        lines = [line.strip() for line in raw.splitlines() if line.strip()]
        fragmented_lines = [line for line in lines if len(WORD_RE.findall(line)) <= 3]
        line_fragmentation = len(fragmented_lines) / max(len(lines), 1) if len(lines) >= 3 else 0.0
        normalized_lines = [normalize_search_text(line) for line in lines]
        repeated_line_ratio = (
            (len(normalized_lines) - len(set(normalized_lines))) / max(len(normalized_lines), 1)
        )
        leading_lines = [line.strip() for line in raw[:260].splitlines() if line.strip()]
        leading_fragmentation = (
            sum(len(WORD_RE.findall(line)) <= 3 for line in leading_lines)
            / max(len(leading_lines), 1)
            if len(leading_lines) >= 4
            else 0.0
        )
        suspicious_symbol_ratio = (
            sum(
                not character.isalnum()
                and not character.isspace()
                and character not in ALLOWED_SYMBOLS
                for character in display
            )
            / max(len(display), 1)
        )
        language = analyze_language(display)
        query_coverage = meaningful_term_coverage(query_terms, display)
        sentence_marks = len(re.findall(r"[.!?؟](?:\s|$)", display))
        sentence_completeness = min(1.0, sentence_marks / max(len(display) / 240, 1.0))
        normalized_display = normalize_search_text(display)
        project_delivery_signal = any(
            normalize_search_text(marker) in normalized_display
            for marker in PROJECT_EVIDENCE_MARKERS
        )
        concept_evidence_support = metadata_supports_concepts(
            query_terms.concepts, display
        )
        boilerplate_markers = [
            marker for marker in LEGAL_BOILERPLATE_MARKERS if marker in normalized_display
        ]
        contact_or_signature = bool(CONTACT_OR_SIGNATURE_RE.search(display))

        quality_score = (
            0.10 * min(printable_ratio, 1.0)
            + 0.14 * min(alphabetic_ratio / 0.65, 1.0)
            + 0.14 * min(len(content_tokens) / 12, 1.0)
            + 0.08 * min(average_token_length / 5, 1.0)
            + 0.12 * max(0.0, 1.0 - single_character_ratio)
            + 0.14 * max(0.0, 1.0 - line_fragmentation)
            + 0.08 * max(0.0, 1.0 - repeated_line_ratio)
            + 0.08 * max(0.0, 1.0 - suspicious_symbol_ratio * 4)
            + 0.12 * sentence_completeness
        )
        quality_score = round(max(0.0, min(1.0, quality_score)), 6)

        reasons: list[str] = []
        if len(content_tokens) < int(self.settings["minimum_meaningful_tokens"]):
            reasons.append("TOO_FEW_MEANINGFUL_WORDS")
        if line_fragmentation > float(self.settings["maximum_line_fragmentation"]):
            reasons.append("EXCESSIVE_FRAGMENTATION")
        if single_character_ratio > float(self.settings["maximum_single_character_token_ratio"]):
            reasons.append("EXCESSIVE_SINGLE_CHARACTER_TOKENS")
        if printable_ratio < float(self.settings["minimum_printable_ratio"]):
            reasons.append("LOW_PRINTABLE_RATIO")
        if repeated_line_ratio > float(self.settings["maximum_repeated_line_ratio"]):
            reasons.append("REPETITIVE_TEXT")
        if suspicious_symbol_ratio > float(self.settings["maximum_suspicious_symbol_ratio"]):
            reasons.append("OCR_GIBBERISH")
        if leading_fragmentation > float(self.settings["maximum_leading_fragmentation"]):
            reasons.append("OCR_GIBBERISH")
        if alphabetic_ratio < float(self.settings["minimum_alphabetic_ratio"]) or quality_score < float(
            self.settings["minimum_quality_score"]
        ):
            reasons.append("OCR_GIBBERISH")
        if (
            language.mixed_script
            and min(language.arabic_ratio, language.latin_ratio) >= 0.08
            and (single_character_ratio > 0.18 or line_fragmentation > 0.65)
        ):
            reasons.append("INCOHERENT_MIXED_SCRIPT")
        if boilerplate_markers or contact_or_signature:
            reasons.append("LEGAL_OR_CONTACT_BOILERPLATE")

        evidence_language = language.detected_language
        cross_language = (
            query_language not in {"und", "mixed"}
            and evidence_language not in {"und", "mixed", query_language}
        )
        semantic_cross_language_support = (
            cross_language
            and dense_score >= float(self.settings["semantic_cross_language_override"])
            and project_delivery_signal
        )
        if query_terms.meaningful_token_set and query_coverage < float(
            self.settings["minimum_query_term_coverage"]
        ) and not semantic_cross_language_support:
            reasons.append("NO_MEANINGFUL_QUERY_EVIDENCE")
        if query_terms.concepts and not concept_evidence_support:
            reasons.append("NO_MEANINGFUL_QUERY_EVIDENCE")

        reasons = list(dict.fromkeys(reasons))
        diagnostics = {
            "printable_character_ratio": round(printable_ratio, 6),
            "alphabetic_character_ratio": round(alphabetic_ratio, 6),
            "meaningful_token_count": len(content_tokens),
            "average_token_length": round(average_token_length, 6),
            "one_character_token_ratio": round(single_character_ratio, 6),
            "line_count": len(lines),
            "line_fragmentation": round(line_fragmentation, 6),
            "leading_fragmentation": round(leading_fragmentation, 6),
            "repeated_line_ratio": round(repeated_line_ratio, 6),
            "suspicious_symbol_ratio": round(suspicious_symbol_ratio, 6),
            "language": evidence_language,
            "scripts": language.scripts,
            "mixed_script": language.mixed_script,
            "query_meaningful_term_coverage": round(query_coverage, 6),
            "sentence_completeness": round(sentence_completeness, 6),
            "project_delivery_signal": project_delivery_signal,
            "boilerplate_markers": boilerplate_markers,
            "contact_or_signature": contact_or_signature,
            "concept_evidence_support": concept_evidence_support,
            "extraction_quality": extraction_quality,
            "dense_score": round(float(dense_score), 6),
            "semantic_cross_language_support": semantic_cross_language_support,
        }
        return EvidenceQualityResult(not reasons, quality_score, reasons, diagnostics)


def select_best_evidence(
    candidates: list[dict[str, Any]],
    query_terms: QueryTermAnalysis,
    query_language: str,
    reference_text: str,
    evaluator: EvidenceQualityEvaluator,
    term_settings: dict[str, Any],
    selection_settings: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    reference_tokens = set(meaningful_content_tokens(reference_text))
    evaluated: list[dict[str, Any]] = []
    for candidate in candidates:
        chunk = candidate["chunk"]
        if "approved_for_display" in chunk and not bool(chunk["approved_for_display"]):
            continue
        has_lineage_fields = any(
            key in chunk for key in ("source_file_name", "page_number_1_based", "citation_uri")
        )
        if has_lineage_fields and (
            not str(chunk.get("source_file_name") or "").strip()
            or int(chunk.get("page_number_1_based") or 0) <= 0
            or not str(chunk.get("citation_uri") or "").strip()
        ):
            continue
        raw_text = str(chunk["chunk_text"])
        approved_display = chunk.get("display_text")
        display_text = derive_display_text(
            approved_display if isinstance(approved_display, str) and approved_display.strip() else raw_text
        )
        quality = evaluator.evaluate(
            raw_text,
            display_text,
            query_terms,
            dense_score=float(candidate["dense"]),
            query_language=query_language,
            extraction_quality=str(chunk.get("data_quality_status") or "") or None,
        )
        display_tokens = set(meaningful_content_tokens(display_text))
        metadata_support = (
            len(reference_tokens & display_tokens) / max(min(len(reference_tokens), 20), 1)
            if reference_tokens
            else 0.0
        )
        coverage = meaningful_term_coverage(query_terms, display_text)
        bonus = exact_match_bonus(query_terms, display_text, term_settings)
        dense_component = max(0.0, min(1.0, (float(candidate["dense"]) + 1.0) / 2.0))
        selection_score = (
            0.42 * quality.quality_score
            + 0.20 * coverage
            + 0.15 * dense_component
            + 0.08 * min(metadata_support, 1.0)
            + 0.05 * min(bonus / max(float(term_settings["maximum_exact_match_bonus"]), 1e-9), 1.0)
            + 0.10 * float(quality.diagnostics["project_delivery_signal"])
        )
        evaluated.append(
            {
                **candidate,
                "raw_source_text": raw_text,
                "retrieval_text": raw_text,
                "display_text": display_text,
                "coverage": coverage,
                "exact_term_bonus": bonus,
                "metadata_support": metadata_support,
                "quality": quality,
                "selection_score": round(selection_score, 8),
            }
        )
    passed = [candidate for candidate in evaluated if candidate["quality"].quality_pass]
    passed.sort(
        key=lambda candidate: (
            -float(candidate["selection_score"]),
            -float(candidate["coverage"]),
            -float(candidate["quality"].quality_score),
            -float(candidate["dense"]),
            str(candidate["chunk"]["chunk_id"]),
        )
    )
    maximum = int(selection_settings["maximum_passages_per_reference"])
    return passed[:maximum], evaluated
