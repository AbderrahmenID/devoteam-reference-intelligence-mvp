from pathlib import Path

import fitz

from extraction.pdf_extraction import extract_pdf


def test_digital_pdf_preserves_multilingual_original_and_provenance(tmp_path: Path) -> None:
    path = tmp_path / "small.pdf"
    document = fitz.open()
    page = document.new_page()
    text = "French reference banque cloud security project with enough words for digital extraction."
    page.insert_text((72, 72), text)
    document.save(path)
    document.close()
    config = {
        "digital_text_min_characters": 20, "digital_text_min_words": 5,
        "pdf_render_dpi": 72, "ocr_languages": "fra+eng+ara", "tesseract_psm": 3,
        "chunk_max_characters": 900, "chunk_overlap_characters": 120,
        "chunk_min_characters": 10,
    }
    result = extract_pdf(path, config, max_pages=1)
    assert result["page_count"] == 1
    assert result["pages"][0]["extraction_method"] == "digital_text"
    assert result["pages"][0]["source_filename"] == "small.pdf"
    assert result["pages"][0]["page_number"] == 1
    assert text in result["pages"][0]["original_text"]
    assert result["chunks"][0]["original_text"]

