from __future__ import annotations

import html
import re
import unicodedata


SCRIPT_STYLE_RE = re.compile(r"<(?:script|style)\b[^>]*>.*?</(?:script|style)>", re.IGNORECASE | re.DOTALL)
TAG_RE = re.compile(r"<[^>]*>")
HORIZONTAL_SPACE_RE = re.compile(r"[ \t\f\v]+")


def sanitize_generation_text(value: str, *, maximum_characters: int) -> str:
    """Sanitize user/source input before it is placed in an LLM prompt."""
    decoded = html.unescape(str(value or ""))
    without_markup = TAG_RE.sub("", SCRIPT_STYLE_RE.sub("", decoded))
    without_controls = "".join(
        character
        for character in without_markup
        if character in "\n\r" or not unicodedata.category(character).startswith("C")
    )
    normalized = HORIZONTAL_SPACE_RE.sub(" ", without_controls)
    normalized = "\n".join(line.strip() for line in normalized.splitlines() if line.strip()).strip()
    return normalized[:maximum_characters]


def sanitize_source_label(value: str) -> str:
    """Return a display-safe basename without preserving an internal path."""
    normalized = str(value or "").replace("\\", "/")
    return sanitize_generation_text(normalized.rsplit("/", 1)[-1], maximum_characters=180)
