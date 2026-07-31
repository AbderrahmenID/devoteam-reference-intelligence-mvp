from __future__ import annotations

from typing import Any

from retrieval.normalization import normalize_search_text


BOUNDARIES = ("\n\n", "\n", ". ", "! ", "? ", "؟ ", "; ", ": ", ", ", " ")


def chunk_page(page: dict[str, Any], *, maximum: int = 900, overlap: int = 120, minimum: int = 120) -> list[dict[str, Any]]:
    text = str(page.get("original_text") or "")
    if not text.strip():
        return []
    if maximum <= overlap or minimum <= 0:
        raise ValueError("Invalid chunking configuration")
    chunks: list[dict[str, Any]] = []
    start = 0
    while start < len(text):
        end = min(start + maximum, len(text))
        if end < len(text):
            search_start = min(start + minimum, end)
            best_position, best_width = -1, 0
            for boundary in BOUNDARIES:
                position = text.rfind(boundary, search_start, end + 1)
                if position > best_position:
                    best_position, best_width = position, len(boundary)
            if best_position >= search_start:
                end = best_position + best_width
        raw = text[start:end]
        leading = len(raw) - len(raw.lstrip())
        trailing = len(raw.rstrip())
        actual_start, actual_end = start + leading, start + trailing
        evidence = text[actual_start:actual_end]
        if evidence:
            chunks.append({
                "source_filename": page["source_filename"],
                "page_number": page["page_number"],
                "chunk_index": len(chunks) + 1,
                "character_start": actual_start,
                "character_end": actual_end,
                "original_text": evidence,
                "normalized_retrieval_text": normalize_search_text(evidence),
                "quality_status": page["quality_status"],
            })
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    if any(len(item["original_text"]) > maximum for item in chunks):
        raise AssertionError("Chunk exceeds configured maximum")
    return chunks

