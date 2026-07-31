from __future__ import annotations

import shutil
from typing import Any

from PIL import Image


def tesseract_available() -> bool:
    return shutil.which("tesseract") is not None


def ocr_image(image: Image.Image, languages: str = "fra+eng+ara", psm: int = 3) -> tuple[str, float | None]:
    if not tesseract_available():
        raise RuntimeError(
            "Tesseract is not installed. Install Tesseract plus fra, eng and ara language packs "
            "to use OCR fallback; ordinary retrieval does not require OCR."
        )
    import pytesseract

    config = f"--psm {int(psm)}"
    text = pytesseract.image_to_string(image, lang=languages, config=config)
    data: dict[str, Any] = pytesseract.image_to_data(
        image, lang=languages, config=config, output_type=pytesseract.Output.DICT
    )
    confidences = []
    for raw in data.get("conf", []):
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if value >= 0:
            confidences.append(value)
    return text, (sum(confidences) / len(confidences) if confidences else None)

