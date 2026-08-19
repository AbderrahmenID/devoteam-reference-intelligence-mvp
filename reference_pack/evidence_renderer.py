from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import fitz
from PIL import Image, ImageChops, ImageOps

from .schemas import TrustedEvidence
from .validation import sha256_file


SUPPORTED_IMAGES = {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
OFFICE_FORMATS = {".doc", ".docx", ".odp", ".ppt", ".pptx"}


@dataclass(frozen=True)
class EvidenceVisual:
    reference_id: str
    chunk_id: str
    document_id: str
    source_file_name: str
    source_page: int
    source_sha256: str
    image_path: Path | None
    rendering_method: str
    fallback_reason: str | None
    original_pixel_width: int | None = None
    original_pixel_height: int | None = None
    rendered_pixel_width: int | None = None
    rendered_pixel_height: int | None = None
    crop_coordinates_px: tuple[int, int, int, int] | None = None

    @property
    def is_rendered(self) -> bool:
        return self.image_path is not None and self.fallback_reason is None

    def manifest_record(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            "reference_id": self.reference_id,
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "source_file_name": self.source_file_name,
            "source_page": self.source_page,
            "source_sha256": self.source_sha256,
            "rendering_method": self.rendering_method,
            "rendered_source_image": self.is_rendered,
            "fallback_reason": self.fallback_reason,
        }
        if self.is_rendered:
            record.update(
                {
                    "image_file_name": self.image_path.name,
                    "original_pixel_size": [self.original_pixel_width, self.original_pixel_height],
                    "rendered_pixel_size": [self.rendered_pixel_width, self.rendered_pixel_height],
                    "crop_coordinates_px": list(self.crop_coordinates_px or ()),
                    "aspect_ratio": round(
                        float(self.rendered_pixel_width) / float(self.rendered_pixel_height), 6
                    ),
                }
            )
        return record


class EvidenceRenderingError(RuntimeError):
    """Stable fail-closed error raised when an approved page cannot be rendered."""

    def __init__(self, reason: str, message: str, *, reference_id: str, document_id: str, page: int):
        super().__init__(message)
        self.reason = reason
        self.message = message
        self.reference_id = reference_id
        self.document_id = document_id
        self.page = page


class EvidenceRenderer:
    """Resolve hash-pinned local evidence and render the approved source page."""

    def __init__(self, project_root: Path, config: dict[str, Any]):
        self.project_root = project_root.resolve()
        evidence_config = config["evidence"]
        self.allowed_roots = [
            (self.project_root / value).resolve()
            for value in evidence_config.get("local_source_roots", [])
        ]
        for root in self.allowed_roots:
            if root != self.project_root and self.project_root not in root.parents:
                raise RuntimeError("Evidence source root escapes the project")
        self.render_scale = float(evidence_config.get("render_scale", 3.0))
        self.white_margin_threshold = int(evidence_config.get("white_margin_threshold", 247))
        self.crop_padding_px = int(evidence_config.get("crop_padding_px", 28))
        self.office_candidates = [Path(value) for value in config["generation"].get("libreoffice_candidates", [])]

    def _approved_local_source(self, evidence: TrustedEvidence) -> tuple[Path | None, str | None]:
        if not evidence.source_relative_path:
            return None, "approved source path is unavailable"
        relative = Path(evidence.source_relative_path)
        if relative.is_absolute() or ".." in relative.parts:
            return None, "approved source path is invalid"

        candidates: list[Path] = []
        for root in self.allowed_roots:
            exact = (root / relative).resolve()
            if root == exact or root in exact.parents:
                candidates.append(exact)
            parent = (root / relative.parent).resolve()
            if root == parent or root in parent.parents:
                stem_prefix = relative.name.split("__", 1)[0]
                if parent.is_dir() and stem_prefix:
                    candidates.extend(sorted(parent.glob(f"{stem_prefix}__*")))

        existing = list(dict.fromkeys(path for path in candidates if path.is_file()))
        if not existing:
            return None, "approved source file is unavailable"
        for candidate in existing:
            if sha256_file(candidate) == evidence.source_sha256:
                return candidate, None
        return None, "approved source hash mismatch"

    @staticmethod
    def _safe_white_margin_crop(image: Image.Image, threshold: int, padding: int) -> tuple[Image.Image, tuple[int, int, int, int]]:
        rgb = image.convert("RGB")
        gray = ImageOps.grayscale(rgb)
        background = Image.new("L", gray.size, 255)
        difference = ImageChops.difference(gray, background)
        ink = difference.point(lambda value: 255 if value > 255 - threshold else 0)
        bounds = ink.getbbox()
        if bounds is None:
            return rgb, (0, 0, rgb.width, rgb.height)
        left = max(0, bounds[0] - padding)
        top = max(0, bounds[1] - padding)
        right = min(rgb.width, bounds[2] + padding)
        bottom = min(rgb.height, bounds[3] + padding)
        # A crop is accepted only when it removes margins, never document content.
        if right - left < rgb.width * 0.55 or bottom - top < rgb.height * 0.55:
            return rgb, (0, 0, rgb.width, rgb.height)
        return rgb.crop((left, top, right, bottom)), (left, top, right, bottom)

    def _libreoffice(self) -> Path | None:
        for candidate in self.office_candidates:
            if candidate.is_file():
                return candidate
        found = shutil.which("soffice") or shutil.which("libreoffice")
        return Path(found) if found else None

    def _office_to_pdf(self, source: Path, work_dir: Path) -> tuple[Path | None, str | None]:
        executable = self._libreoffice()
        if executable is None:
            return None, "LibreOffice is unavailable for source-document rendering"
        converted_dir = work_dir / "converted"
        converted_dir.mkdir(parents=True, exist_ok=True)
        completed = subprocess.run(
            [str(executable), "--headless", "--convert-to", "pdf", "--outdir", str(converted_dir), str(source)],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        converted = converted_dir / f"{source.stem}.pdf"
        if completed.returncode != 0 or not converted.is_file():
            detail = (completed.stderr or completed.stdout or "conversion failed").strip()
            return None, f"source-document conversion failed: {detail[:180]}"
        return converted, None

    def _render_pdf_page(self, source: Path, page_number: int) -> tuple[Image.Image | None, str | None]:
        try:
            with fitz.open(source) as document:
                if page_number < 1 or page_number > document.page_count:
                    return None, "approved source page is outside the document"
                page = document[page_number - 1]
                pixmap = page.get_pixmap(
                    matrix=fitz.Matrix(self.render_scale, self.render_scale), alpha=False
                )
                mode = "RGB" if pixmap.n < 4 else "RGBA"
                return Image.frombytes(mode, (pixmap.width, pixmap.height), pixmap.samples).convert("RGB"), None
        except Exception as exc:
            return None, f"source PDF page could not be rendered: {type(exc).__name__}"

    def render(
        self,
        reference_id: str,
        evidence: TrustedEvidence,
        output_path: Path,
    ) -> EvidenceVisual:
        source, resolution_error = self._approved_local_source(evidence)
        if source is None:
            return EvidenceVisual(
                reference_id, evidence.chunk_id, evidence.document_id, evidence.source_file_name,
                evidence.source_page, evidence.source_sha256, None, "text_fallback", resolution_error,
            )

        suffix = source.suffix.casefold()
        method = ""
        image: Image.Image | None = None
        error: str | None = None
        if suffix == ".pdf":
            method = "pdf_page_render"
            image, error = self._render_pdf_page(source, evidence.source_page)
        elif suffix in SUPPORTED_IMAGES:
            method = "source_image_render"
            if evidence.source_page != 1:
                error = "approved image evidence supports page 1 only"
            else:
                try:
                    with Image.open(source) as opened:
                        image = opened.convert("RGB")
                except Exception as exc:
                    error = f"source image could not be rendered: {type(exc).__name__}"
        elif suffix in OFFICE_FORMATS:
            method = "libreoffice_page_render"
            converted, error = self._office_to_pdf(source, output_path.parent)
            if converted is not None:
                image, error = self._render_pdf_page(converted, evidence.source_page)
        else:
            method = "text_fallback"
            error = f"unsupported source format: {suffix or 'unknown'}"

        if image is None:
            return EvidenceVisual(
                reference_id, evidence.chunk_id, evidence.document_id, evidence.source_file_name,
                evidence.source_page, evidence.source_sha256, None, method or "text_fallback",
                error or "source page rendering failed",
            )

        original_width, original_height = image.size
        cropped, crop = self._safe_white_margin_crop(
            image, self.white_margin_threshold, self.crop_padding_px
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cropped.save(output_path, format="PNG", optimize=True)
        return EvidenceVisual(
            reference_id=reference_id,
            chunk_id=evidence.chunk_id,
            document_id=evidence.document_id,
            source_file_name=evidence.source_file_name,
            source_page=evidence.source_page,
            source_sha256=evidence.source_sha256,
            image_path=output_path,
            rendering_method=method,
            fallback_reason=None,
            original_pixel_width=original_width,
            original_pixel_height=original_height,
            rendered_pixel_width=cropped.width,
            rendered_pixel_height=cropped.height,
            crop_coordinates_px=crop,
        )

    def render_required(
        self,
        reference_id: str,
        evidence: TrustedEvidence,
        output_path: Path,
    ) -> EvidenceVisual:
        """Render one trusted page and reject every former text-fallback case."""
        visual = self.render(reference_id, evidence, output_path)
        if visual.is_rendered:
            return visual

        detail = visual.fallback_reason or "approved source page rendering failed"
        normalized = detail.casefold()
        if "hash mismatch" in normalized:
            reason = "EVIDENCE_HASH_MISMATCH"
        elif "source path" in normalized or "source file is unavailable" in normalized:
            reason = "EVIDENCE_SOURCE_NOT_FOUND"
        elif "outside the document" in normalized or "supports page 1 only" in normalized:
            reason = "EVIDENCE_PAGE_NOT_APPROVED"
        else:
            reason = "EVIDENCE_PAGE_RENDER_FAILED"
        raise EvidenceRenderingError(
            reason,
            detail,
            reference_id=reference_id,
            document_id=evidence.document_id,
            page=evidence.source_page,
        )
