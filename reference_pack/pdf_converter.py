from __future__ import annotations

import shutil
import subprocess
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import fitz


@dataclass(frozen=True)
class PdfConversionResult:
    path: Path | None
    warning: str | None
    validation: dict[str, Any]
    command: list[str]


def _contains_arabic(value: str) -> bool:
    return any("ARABIC" in unicodedata.name(character, "") for character in value)


def _contains_accented_latin(value: str) -> bool:
    return any(ord(character) > 127 and "LATIN" in unicodedata.name(character, "") for character in value)


class LibreOfficePdfConverter:
    def __init__(self, candidates: list[str]):
        self.candidates = [Path(value) for value in candidates]

    def executable(self) -> Path | None:
        for candidate in self.candidates:
            if candidate.is_file():
                return candidate
        discovered = shutil.which("soffice") or shutil.which("libreoffice")
        return Path(discovered) if discovered else None

    def convert(
        self,
        pptx_path: Path,
        pdf_path: Path,
        expected_slide_count: int,
        unicode_samples: list[str],
    ) -> PdfConversionResult:
        executable = self.executable()
        if executable is None:
            return PdfConversionResult(
                path=None,
                warning="LibreOffice is unavailable; the editable PPTX was generated but no PDF was created.",
                validation={"status": "NOT_RUN", "reason": "LIBREOFFICE_UNAVAILABLE"},
                command=[],
            )
        with tempfile.TemporaryDirectory(prefix="devoteam_reference_pack_pdf_") as temporary:
            output_dir = Path(temporary)
            command = [
                str(executable), "--headless", "--nologo", "--nodefault", "--nolockcheck",
                "--nofirststartwizard", "--convert-to", "pdf", "--outdir", str(output_dir),
                str(pptx_path.resolve()),
            ]
            completed = subprocess.run(
                command,
                cwd=pptx_path.parent,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
                check=False,
            )
            converted = output_dir / f"{pptx_path.stem}.pdf"
            if completed.returncode != 0 or not converted.is_file():
                message = (completed.stderr or completed.stdout or "unknown LibreOffice error").strip()
                return PdfConversionResult(
                    path=None,
                    warning=f"PDF conversion failed: {message}",
                    validation={"status": "FAIL", "exit_code": completed.returncode},
                    command=command,
                )
            pdf_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(converted, pdf_path)

        validation = self.validate(pdf_path, expected_slide_count, unicode_samples)
        return PdfConversionResult(pdf_path, None, validation, command)

    @staticmethod
    def validate(path: Path, expected_pages: int, unicode_samples: list[str]) -> dict[str, Any]:
        if not path.is_file() or path.stat().st_size < 1024:
            raise RuntimeError("LibreOffice produced an empty or missing PDF")
        with fitz.open(path) as document:
            if document.page_count != expected_pages:
                raise RuntimeError(
                    f"PDF page count {document.page_count} does not match PPTX slide count {expected_pages}"
                )
            text = "\n".join(page.get_text("text") for page in document)
            accents_required = any(_contains_accented_latin(value) for value in unicode_samples)
            arabic_required = any(_contains_arabic(value) for value in unicode_samples)
            accents_present = (not accents_required) or _contains_accented_latin(text)
            arabic_present = (not arabic_required) or _contains_arabic(text)
            if not accents_present:
                raise RuntimeError("French accented text did not survive PDF conversion")
            if not arabic_present:
                raise RuntimeError("Arabic Unicode did not survive PDF conversion")
            blank_pages: list[int] = []
            non_landscape_pages: list[int] = []
            for page_number, page in enumerate(document, start=1):
                if page.rect.width <= page.rect.height:
                    non_landscape_pages.append(page_number)
                pixmap = page.get_pixmap(matrix=fitz.Matrix(0.25, 0.25), alpha=False)
                if not any(value < 245 for value in pixmap.samples):
                    blank_pages.append(page_number)
            if blank_pages:
                raise RuntimeError(f"The rendered PDF contains blank pages: {blank_pages}")
            if non_landscape_pages:
                raise RuntimeError(f"The rendered PDF contains unexpected page orientation: {non_landscape_pages}")
            return {
                "status": "PASS",
                "page_count": document.page_count,
                "bytes": path.stat().st_size,
                "french_accents": "PASS" if accents_present else "FAIL",
                "arabic_unicode": "PASS" if arabic_present else "FAIL",
                "all_pages_nonblank": "PASS",
                "page_orientation": "PASS",
            }
