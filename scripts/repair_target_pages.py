from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import statistics
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import fitz
import pandas as pd
import pytesseract
import yaml
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
from pytesseract import Output

from extraction.chunking import chunk_page
from retrieval.evidence import EvidenceQualityEvaluator, clean_display_text
from retrieval.language import analyze_language
from retrieval.normalization import normalize_search_text
from retrieval.terms import QueryTermAnalysis


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "data" / "versions" / "v2" / "TARGETED_REPAIR_MANIFEST.csv"
DEFAULT_OUTPUT = ROOT / "data" / "versions" / "v2"
TESSERACT_EXE = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
DEFAULT_TESSDATA = Path.home() / "AppData" / "Local" / "DevoteamOCR" / "tessdata"
WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def clean_text(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(character for character in text if character in "\n\t" or unicodedata.category(character)[0] != "C")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def empty_query_terms() -> QueryTermAnalysis:
    return QueryTermAnalysis(
        normalized_query="",
        raw_tokens=[],
        bm25_tokens=[],
        meaningful_terms=[],
        removed_stopwords=[],
        rejected_common_terms=[],
        rejected_out_of_vocabulary=[],
        concepts=[],
    )


def ocr_text_and_confidence(image: Image.Image, *, psm: int, languages: str = "fra+eng+ara") -> tuple[str, float | None]:
    values = pytesseract.image_to_data(
        image,
        lang=languages,
        config=f"--oem 1 --psm {psm} -c preserve_interword_spaces=1",
        output_type=Output.DICT,
    )
    lines: list[str] = []
    current_key: tuple[int, int, int, int] | None = None
    current_words: list[str] = []
    confidences: list[float] = []
    for index, raw_word in enumerate(values["text"]):
        word = str(raw_word or "").strip()
        if not word:
            continue
        key = tuple(int(values[name][index]) for name in ("page_num", "block_num", "par_num", "line_num"))
        if current_key is not None and key != current_key and current_words:
            lines.append(" ".join(current_words))
            current_words = []
        current_key = key
        current_words.append(word)
        try:
            confidence = float(values["conf"][index])
        except (TypeError, ValueError):
            confidence = -1.0
        if confidence >= 0:
            confidences.append(confidence)
    if current_words:
        lines.append(" ".join(current_words))
    text = clean_text("\n".join(lines))
    confidence = statistics.fmean(confidences) if confidences else None
    return text, confidence


def render_page(page: fitz.Page, dpi: int) -> Image.Image:
    scale = dpi / 72.0
    pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False, colorspace=fitz.csRGB)
    return Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)


def threshold_image(image: Image.Image) -> Image.Image:
    gray = ImageOps.grayscale(image)
    gray = ImageOps.autocontrast(gray, cutoff=1)
    gray = gray.filter(ImageFilter.MedianFilter(size=3))
    histogram = gray.histogram()
    total = sum(histogram)
    weighted = sum(index * count for index, count in enumerate(histogram))
    threshold = max(130, min(210, int(weighted / max(total, 1)) - 18))
    return gray.point(lambda value: 255 if value > threshold else 0, mode="1")


def quality_diagnostics(text: str, evaluator: EvidenceQualityEvaluator, extraction: dict[str, Any]) -> dict[str, Any]:
    language = analyze_language(text)
    page = {
        "source_filename": extraction["source_file_name"],
        "page_number": int(extraction["source_page"]),
        "original_text": text,
        "quality_status": "REVIEW",
    }
    chunks = chunk_page(page, maximum=900, overlap=120, minimum=120)
    results = []
    reasons: Counter[str] = Counter()
    for chunk in chunks:
        display = clean_display_text(chunk["original_text"])
        result = evaluator.evaluate(
            chunk["original_text"],
            display,
            empty_query_terms(),
            dense_score=0.0,
            query_language="und",
            extraction_quality="REPAIR_ATTEMPT",
        )
        reasons.update(result.rejection_reasons)
        results.append(result)
    passing = sum(result.quality_pass for result in results)
    return {
        "character_count": len(text),
        "word_count": len(WORD_RE.findall(text)),
        "text_sha256": sha256_text(text),
        "detected_language": language.detected_language,
        "scripts": language.scripts,
        "rtl": language.rtl,
        "chunk_count": len(chunks),
        "quality_passing_chunks": passing,
        "quality_pass_rate": round(passing / max(len(results), 1), 6),
        "mean_quality_score": round(statistics.fmean(result.quality_score for result in results), 6) if results else 0.0,
        "minimum_quality_score": round(min(result.quality_score for result in results), 6) if results else 0.0,
        "rejection_reason_counts": dict(sorted(reasons.items())),
    }


def choose_attempt(attempts: list[dict[str, Any]]) -> dict[str, Any] | None:
    viable = [
        attempt
        for attempt in attempts
        if (
            (
                attempt["diagnostics"]["quality_passing_chunks"] > 0
                and attempt["diagnostics"]["quality_pass_rate"] >= 0.5
            )
            or (
                attempt["display_diagnostics"]["quality_passing_chunks"] > 0
                and attempt["display_diagnostics"]["quality_pass_rate"] >= 0.5
                and attempt["diagnostics"]["mean_quality_score"] >= 0.68
                and float(attempt.get("ocr_confidence") or 0.0) >= 70.0
            )
        )
        and attempt["diagnostics"]["word_count"] >= 10
    ]
    if not viable:
        return None
    return max(
        viable,
        key=lambda attempt: (
            attempt["display_diagnostics"]["quality_pass_rate"],
            attempt["diagnostics"]["quality_pass_rate"],
            attempt["display_diagnostics"]["mean_quality_score"],
            attempt["diagnostics"]["mean_quality_score"],
            min(attempt["diagnostics"]["word_count"], 500),
            float(attempt.get("ocr_confidence") or 0.0),
            -attempt["strategy_order"],
        ),
    )


def run(manifest_path: Path, output_root: Path, tessdata: Path, dpi: int) -> int:
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    evaluator = EvidenceQualityEvaluator(config["evidence_quality"])
    required = {"ara.traineddata", "eng.traineddata", "fra.traineddata"}
    present = {path.name for path in tessdata.glob("*.traineddata")}
    if not TESSERACT_EXE.is_file() or not required.issubset(present):
        raise RuntimeError("Tesseract or required ara/eng/fra language packs are unavailable")
    pytesseract.pytesseract.tesseract_cmd = str(TESSERACT_EXE)
    os.environ["TESSDATA_PREFIX"] = str(tessdata)

    with manifest_path.open("r", encoding="utf-8-sig", newline="") as handle:
        manifest = list(csv.DictReader(handle))
    attempts_root = output_root / "repair_attempts"
    attempts_root.mkdir(parents=True, exist_ok=True)
    selected_pages: list[dict[str, Any]] = []
    page_results: list[dict[str, Any]] = []
    blocked: list[str] = []

    for manifest_row in manifest:
        repair_id = manifest_row["repair_id"]
        source_path = Path(manifest_row["source_file_path"])
        if not source_path.is_file():
            raise FileNotFoundError(source_path)
        if sha256_file(source_path) != manifest_row["source_document_hash"].casefold():
            raise RuntimeError(f"Source hash mismatch for {repair_id}")
        page_number = int(manifest_row["source_page"])
        attempt_dir = attempts_root / repair_id
        attempt_dir.mkdir(parents=True, exist_ok=True)
        attempts: list[dict[str, Any]] = []

        with fitz.open(source_path) as document:
            if page_number < 1 or page_number > len(document):
                raise RuntimeError(f"Page out of range for {repair_id}")
            page = document[page_number - 1]
            digital_text = clean_text(page.get_text("text"))
            image = render_page(page, dpi)
            strategies: list[tuple[str, int | None, Image.Image | None, str, str | None]] = [
                ("digital_text", None, None, digital_text, None),
                ("ocr_rgb_psm3", 3, image, "", "fra+eng+ara"),
                ("ocr_gray_autocontrast_psm3", 3, ImageEnhance.Contrast(ImageOps.autocontrast(ImageOps.grayscale(image))).enhance(1.35), "", "fra+eng+ara"),
                ("ocr_threshold_psm6", 6, threshold_image(image), "", "fra+eng+ara"),
            ]
            for order, (strategy, psm, strategy_image, initial_text, languages) in enumerate(strategies):
                if strategy == "digital_text":
                    text, confidence = initial_text, None
                else:
                    text, confidence = ocr_text_and_confidence(strategy_image, psm=int(psm), languages=str(languages))
                diagnostics = quality_diagnostics(text, evaluator, manifest_row)
                display_text = clean_display_text(text)
                display_diagnostics = quality_diagnostics(display_text, evaluator, manifest_row)
                record = {
                    "repair_id": repair_id,
                    "strategy": strategy,
                    "strategy_order": order,
                    "psm": psm,
                    "render_dpi": dpi if psm is not None else None,
                    "ocr_languages": languages,
                    "ocr_confidence": round(confidence, 6) if confidence is not None else None,
                    "diagnostics": diagnostics,
                    "display_diagnostics": display_diagnostics,
                    "display_text": display_text,
                    "text": text,
                }
                attempts.append(record)
                (attempt_dir / f"{order:02d}_{strategy}.txt").write_text(text, encoding="utf-8")
                (attempt_dir / f"{order:02d}_{strategy}.json").write_text(
                    json.dumps({key: value for key, value in record.items() if key not in {"text", "display_text"}}, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

            multilingual_text = attempts[1]["text"]
            alphabetic = [character for character in multilingual_text if character.isalpha()]
            latin = sum("LATIN" in unicodedata.name(character, "") for character in alphabetic)
            if alphabetic and latin / len(alphabetic) >= 0.80:
                strategy = "ocr_latin_dominant_fra_eng_psm3"
                text, confidence = ocr_text_and_confidence(image, psm=3, languages="fra+eng")
                diagnostics = quality_diagnostics(text, evaluator, manifest_row)
                display_text = clean_display_text(text)
                display_diagnostics = quality_diagnostics(display_text, evaluator, manifest_row)
                record = {
                    "repair_id": repair_id,
                    "strategy": strategy,
                    "strategy_order": len(attempts),
                    "psm": 3,
                    "render_dpi": dpi,
                    "ocr_languages": "fra+eng",
                    "ocr_confidence": round(confidence, 6) if confidence is not None else None,
                    "diagnostics": diagnostics,
                    "display_diagnostics": display_diagnostics,
                    "display_text": display_text,
                    "text": text,
                    "refinement_basis": "mandatory_multilingual_pass_was_at_least_80_percent_latin_alphabetic_characters",
                }
                attempts.append(record)
                order = record["strategy_order"]
                (attempt_dir / f"{order:02d}_{strategy}.txt").write_text(text, encoding="utf-8")
                (attempt_dir / f"{order:02d}_{strategy}.json").write_text(
                    json.dumps({key: value for key, value in record.items() if key not in {"text", "display_text"}}, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

        selected = choose_attempt(attempts)
        if selected is None:
            blocked.append(repair_id)
            page_results.append({
                "repair_id": repair_id,
                "source_document_id": manifest_row["source_document_id"],
                "source_page": page_number,
                "status": "BLOCKED_UNREADABLE_AFTER_CONTROLLED_REPAIR",
                "selected_strategy": "",
                "selected_text_sha256": "",
                "selected_character_count": 0,
                "selected_word_count": 0,
                "selected_quality_pass_rate": 0.0,
                "selected_mean_quality_score": 0.0,
                "selected_ocr_confidence": "",
                "required_human_follow_up": manifest_row["required_human_follow_up"],
            })
            continue

        selected_text = selected.pop("text")
        selected_display_text = selected.pop("display_text")
        normalized_layout = selected["diagnostics"]["quality_pass_rate"] < 0.5
        selected_page = {
            **manifest_row,
            "selected_extraction_method": selected["strategy"],
            "selected_ocr_confidence": selected["ocr_confidence"],
            "selected_text": selected_text,
            "selected_display_text": selected_display_text,
            "selected_text_sha256": sha256_text(selected_text),
            "selected_display_text_sha256": sha256_text(selected_display_text),
            "selected_diagnostics_json": json.dumps(selected["diagnostics"], ensure_ascii=False, sort_keys=True),
            "selected_display_diagnostics_json": json.dumps(selected["display_diagnostics"], ensure_ascii=False, sort_keys=True),
            "repair_status": "REPAIRED_WITH_LAYOUT_NORMALIZATION_PENDING_HUMAN_FOLLOW_UP" if normalized_layout else "REPAIRED_PENDING_HUMAN_FOLLOW_UP",
            "repair_attempt_count": len(attempts),
        }
        selected_pages.append(selected_page)
        page_results.append({
            "repair_id": repair_id,
            "source_document_id": manifest_row["source_document_id"],
            "source_page": page_number,
            "status": selected_page["repair_status"],
            "selected_strategy": selected["strategy"],
            "selected_text_sha256": selected_page["selected_text_sha256"],
            "selected_character_count": selected["diagnostics"]["character_count"],
            "selected_word_count": selected["diagnostics"]["word_count"],
            "selected_quality_pass_rate": selected["display_diagnostics"]["quality_pass_rate"],
            "selected_mean_quality_score": selected["display_diagnostics"]["mean_quality_score"],
            "selected_ocr_confidence": selected["ocr_confidence"],
            "required_human_follow_up": manifest_row["required_human_follow_up"],
        })

    pd.DataFrame(page_results).to_csv(output_root / "PAGE_REPAIR_RESULTS.csv", index=False, encoding="utf-8-sig")
    if selected_pages:
        pd.DataFrame(selected_pages).to_parquet(output_root / "repaired_pages.parquet", index=False)
    run_manifest = {
        "schema_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_manifest": str(manifest_path.relative_to(ROOT)).replace("\\", "/"),
        "input_manifest_sha256": sha256_file(manifest_path),
        "tesseract_executable": str(TESSERACT_EXE),
        "tesseract_version": str(pytesseract.get_tesseract_version()).splitlines()[0],
        "tessdata_prefix": str(tessdata),
        "ocr_languages": ["fra", "eng", "ara"],
        "ocr_language_sha256": {language: sha256_file(tessdata / f"{language}.traineddata") for language in ("fra", "eng", "ara")},
        "render_dpi": dpi,
        "controlled_strategies": ["digital_text", "ocr_rgb_psm3", "ocr_gray_autocontrast_psm3", "ocr_threshold_psm6", "conditional_latin_dominant_fra_eng_psm3"],
        "page_count": len(manifest),
        "repaired_page_count": len(selected_pages),
        "blocked_page_count": len(blocked),
        "blocked_repair_ids": blocked,
        "status": "PASS" if not blocked else "BLOCKED_UNREADABLE_PAGES",
    }
    (output_root / "PAGE_REPAIR_RUN_MANIFEST.json").write_text(json.dumps(run_manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Targeted Page Repair Report",
        "",
        f"Status: **{run_manifest['status']}**",
        "",
        f"- Targeted pages: {len(manifest)}",
        f"- Repaired pages: {len(selected_pages)}",
        f"- Unreadable after controlled attempts: {len(blocked)}",
        "- OCR languages: `fra+eng+ara`",
        f"- Tesseract: `{run_manifest['tesseract_version']}`",
        "- All selected repairs remain explicitly pending human text-and-lineage verification.",
        "",
        "| Repair ID | Page | Result | Strategy | Pass rate | Mean quality | Confidence |",
        "|---|---:|---|---|---:|---:|---:|",
    ]
    for row in page_results:
        confidence = row["selected_ocr_confidence"]
        confidence_text = "" if confidence == "" or confidence is None else f"{float(confidence):.2f}"
        lines.append(
            f"| {row['repair_id']} | {row['source_page']} | {row['status']} | {row['selected_strategy']} | "
            f"{float(row['selected_quality_pass_rate']):.3f} | {float(row['selected_mean_quality_score']):.3f} | {confidence_text} |"
        )
    (ROOT / "docs" / "TARGETED_PAGE_REPAIR_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(run_manifest, indent=2))
    return 0 if not blocked else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Re-extract only human-approved targeted repair pages.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--tessdata", type=Path, default=DEFAULT_TESSDATA)
    parser.add_argument("--dpi", type=int, default=300)
    args = parser.parse_args()
    return run(args.manifest.resolve(), args.output_root.resolve(), args.tessdata.resolve(), args.dpi)


if __name__ == "__main__":
    raise SystemExit(main())
