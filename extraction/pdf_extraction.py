from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

import fitz
from PIL import Image

from retrieval.language import analyze_language
from retrieval.normalization import normalize_search_text

from .chunking import chunk_page
from .ocr import ocr_image


WORD_RE = re.compile(r"\w+", re.UNICODE)


def _clean_original_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", value).replace("\r\n", "\n").replace("\r", "\n")
    return "".join(ch for ch in text if ch in "\n\t" or unicodedata.category(ch)[0] != "C").strip()


def _usable_digital_text(text: str, config: dict) -> bool:
    return len(text) >= int(config["digital_text_min_characters"]) and len(WORD_RE.findall(text)) >= int(
        config["digital_text_min_words"]
    )


def _quality(text: str, method: str, confidence: float | None) -> str:
    if not text.strip():
        return "FAILED"
    if len(text) < 20:
        return "REVIEW"
    if method == "tesseract_ocr" and float(confidence or 0) < 35:
        return "REVIEW"
    return "PASS"


def extract_pdf(path: Path, config: dict, *, max_pages: int | None = None) -> dict[str, Any]:
    path = path.resolve()
    if not path.is_file() or path.suffix.casefold() != ".pdf":
        raise ValueError("Extraction preview accepts an existing PDF file only")
    pages: list[dict[str, Any]] = []
    with fitz.open(path) as document:
        limit = min(len(document), max_pages or len(document))
        for page_index in range(limit):
            page = document[page_index]
            digital = _clean_original_text(page.get_text("text"))
            confidence: float | None = None
            if _usable_digital_text(digital, config):
                original = digital
                method = "digital_text"
            else:
                matrix = fitz.Matrix(int(config["pdf_render_dpi"]) / 72, int(config["pdf_render_dpi"]) / 72)
                pixmap = page.get_pixmap(matrix=matrix, alpha=False)
                image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
                original, confidence = ocr_image(
                    image, languages=str(config["ocr_languages"]), psm=int(config["tesseract_psm"])
                )
                original = _clean_original_text(original)
                method = "tesseract_ocr"
            language = analyze_language(original)
            record = {
                "source_filename": path.name,
                "page_number": page_index + 1,
                "extraction_method": method,
                "quality_status": _quality(original, method, confidence),
                "ocr_confidence": confidence,
                "original_text": original,
                "normalized_retrieval_text": normalize_search_text(original),
                "detected_language": language.detected_language,
                "scripts": language.scripts,
                "rtl": language.rtl,
            }
            pages.append(record)
    chunks = [
        chunk
        for page in pages
        for chunk in chunk_page(
            page,
            maximum=int(config["chunk_max_characters"]),
            overlap=int(config["chunk_overlap_characters"]),
            minimum=int(config["chunk_min_characters"]),
        )
    ]
    return {"source_filename": path.name, "page_count": len(pages), "pages": pages, "chunks": chunks}

