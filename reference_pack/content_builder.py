from __future__ import annotations

import re
from collections.abc import Iterable

from retrieval.evidence import clean_display_text

from .schemas import BulletSource, PreparedReference, TrustedReference


BOILERPLATE_PATTERNS = (
    r"\bje soussign[ée]\b",
    r"\batteste(?: par la pr[ée]sente)?\b",
    r"\bcertifie(?: par la pr[ée]sente)?\b",
    r"\ben foi de quoi\b",
    r"\bservir et valoir ce que de droit\b",
    r"\bfait [àa]\b",
    r"\bsignature\b",
    r"\bt[ée]l(?:[ée]phone)?\b",
    r"\be[- ]?mail\b",
    r"\badresse\b",
    r"\bcontrat n[°o]\b",
    r"\battestation (?:de|du|d['’])\b",
    r"\bpleine satisfaction\b",
    r"\[PHONE_LIKE\]",
)
BOILERPLATE_RE = re.compile("|".join(BOILERPLATE_PATTERNS), re.IGNORECASE)
SPLIT_RE = re.compile(r"(?:\r?\n|[•▪◦]|\s+[–—-]\s+|;\s+|(?<=[.!?])\s+)")
SPACE_RE = re.compile(r"\s+")


LABELS = {
    "fr": {
        "offering": "Les métadonnées structurées identifient l’offre {value}.",
        "sector": "Les métadonnées structurées situent l’expérience dans le secteur {value}.",
        "evidence": "Une preuve approuvée confirme les services réalisés pour ce projet.",
    },
    "en": {
        "offering": "Structured metadata identifies the {value} offering.",
        "sector": "Structured metadata records experience in the {value} sector.",
        "evidence": "Approved evidence confirms services delivered for this project.",
    },
    "ar": {
        "offering": "تحدد البيانات الوصفية المنظمة العرض التالي: {value}.",
        "sector": "تسجل البيانات الوصفية المنظمة خبرة في قطاع {value}.",
        "evidence": "تؤكد الأدلة المعتمدة الخدمات المنفذة لهذا المشروع.",
    },
}


def _normalize(value: str) -> str:
    return SPACE_RE.sub(" ", str(value or "")).strip(" \t\r\n•▪◦-–—:;")


def _strip_administrative_prefix(value: str) -> str:
    if not BOILERPLATE_RE.search(value):
        return value
    normalized = value.casefold()
    positions = [position for marker in ("le projet", "la mission", "l’étude", "l'etude") if (position := normalized.find(marker)) >= 0]
    return value[min(positions):] if positions else value


def _safe_items(value: str, *, maximum_characters: int) -> list[str]:
    """Select source fragments without generating replacement language."""
    cleaned = clean_display_text(str(value or ""))
    candidates = [_normalize(item) for item in SPLIT_RE.split(cleaned)]
    output: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        item = _strip_administrative_prefix(item)
        if len(item) < 12 or BOILERPLATE_RE.search(item):
            continue
        if len(item) > maximum_characters:
            clauses = [_normalize(part) for part in re.split(r"(?<=,)|\s*:\s*", item)]
            item = next((part for part in clauses if 12 <= len(part) <= maximum_characters), "")
        key = item.casefold()
        if not item or key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def _sources(items: Iterable[str], source_field: str) -> list[BulletSource]:
    return [BulletSource(text=item, source_fields=[source_field]) for item in items]


def prepare_evidence_excerpt(value: str, maximum_characters: int) -> str:
    """Join complete, display-safe source fragments within a deterministic limit."""
    selected: list[str] = []
    length = 0
    for item in _safe_items(value, maximum_characters=maximum_characters):
        addition = len(item) + (1 if selected else 0)
        if length + addition > maximum_characters:
            continue
        selected.append(item)
        length += addition
    return " ".join(selected)


def prepare_reference(reference: TrustedReference, language: str) -> PreparedReference:
    service_items = _safe_items(reference.description, maximum_characters=150)
    evidence_items: list[str] = []
    evidence_chunk_ids: dict[str, str] = {}
    for evidence in reference.evidence:
        for item in _safe_items(evidence.display_text, maximum_characters=150):
            evidence_items.append(item)
            evidence_chunk_ids[item] = evidence.chunk_id

    summary: list[BulletSource] = []
    if reference.offering:
        summary.append(BulletSource(text=reference.offering, source_fields=["reference_catalog.offering"]))
    summary.extend(_sources(service_items, "reference_catalog.service_nature"))
    for technology in reference.technologies:
        summary.append(BulletSource(text=technology, source_fields=["derived.technology_rules"]))
    for capability in reference.capabilities:
        summary.append(BulletSource(text=capability, source_fields=["derived.theme_rules"]))

    deduplicated: list[BulletSource] = []
    seen: set[str] = set()
    for bullet in summary:
        key = bullet.text.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(bullet)

    # Summary slides are commercial overviews, not OCR/extraction inventories.
    # Add a short, approved evidence fragment only when structured metadata does
    # not provide enough distinct scope items for a compact three-bullet row.
    for item in evidence_items:
        if len(deduplicated) >= 3:
            break
        normalized = item.casefold()
        if any(
            normalized in bullet.text.casefold() or bullet.text.casefold() in normalized
            for bullet in deduplicated
        ):
            continue
        deduplicated.append(
            BulletSource(
                text=item,
                source_fields=["chunks.display_text"],
                evidence_chunk_ids=[evidence_chunk_ids[item]],
            )
        )
    if len(deduplicated) < 3 and reference.sector:
        deduplicated.append(
            BulletSource(
                text=f"{reference.sector}",
                source_fields=["reference_catalog.sector"],
            )
        )

    labels = LABELS[language]
    why: list[BulletSource] = []
    if reference.offering:
        why.append(
            BulletSource(
                text=labels["offering"].format(value=reference.offering),
                source_fields=["reference_catalog.offering"],
            )
        )
    if reference.sector:
        why.append(
            BulletSource(
                text=labels["sector"].format(value=reference.sector),
                source_fields=["reference_catalog.sector"],
            )
        )
    if reference.evidence:
        why.append(
            BulletSource(
                text=labels["evidence"],
                source_fields=["chunks.display_text", "chunks.approved_for_display"],
                evidence_chunk_ids=[reference.evidence[0].chunk_id],
            )
        )

    description = _sources(service_items[:3], "reference_catalog.service_nature")
    if not description and reference.offering:
        description = [BulletSource(text=reference.offering, source_fields=["reference_catalog.offering"])]
    services = deduplicated[:6]
    return PreparedReference(
        reference=reference,
        summary_bullets=deduplicated[:6],
        description_items=description,
        service_items=services,
        why_selected=why[:3],
        evidence_items=reference.evidence[:2],
    )
