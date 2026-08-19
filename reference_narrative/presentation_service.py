from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from reference_pack.evidence_renderer import EvidenceRenderer, EvidenceRenderingError
from reference_pack.pdf_converter import LibreOfficePdfConverter
from reference_pack.validation import ReferenceValidationError, TrustedV2Repository, sha256_file

from .compact_pptx_generator import OrangeBankCompactNarrativePptxGenerator
from .evidence_annex import choose_evidence, render_evidence
from .ollama_client import DisabledNarrativeProvider
from .presentation_copy import PresentationCopyService
from .pptx_generator import NarrativePptxGenerator
from .presentation_schemas import (
    TEMPLATE_DISPLAY_NAMES,
    DirectPresentationRequest,
    NarrativePresentationRequest,
    NarrativePresentationResponse,
    OutputFormat,
)
from .schemas import (
    EditableReferenceSectionNarrative,
    NarrativeEditValidationRequest,
    NarrativeGenerationRequest,
    ReferenceNarrativeDraft,
    SupportedDetailedPresentationCopy,
    SupportedDetailedRealisation,
    SupportedNarrativeText,
    ValidationSeverity,
)
from .service import ReferenceNarrativeService
from .template_mapper import PptxContentOverflowError


GENERATION_ID_RE = re.compile(r"narrative-pptx-[0-9]{8}T[0-9]{12}Z-[0-9a-f]{10}")


class NarrativePresentationExportError(RuntimeError):
    def __init__(self, reason: str, message: str, **details: Any):
        super().__init__(message)
        self.reason = reason
        self.message = message
        self.details = details

    def as_detail(self) -> dict[str, Any]:
        return {"reason": self.reason, "message": self.message, **self.details}


class NarrativePresentationService:
    """Deterministic export boundary with a deliberately disabled model provider."""

    def __init__(
        self,
        project_root: Path,
        application_config: dict[str, Any],
        *,
        repository: TrustedV2Repository | None = None,
        validator: ReferenceNarrativeService | None = None,
        content_generator: PresentationCopyService | None = None,
        evidence_renderer: EvidenceRenderer | None = None,
        pdf_converter: LibreOfficePdfConverter | None = None,
    ):
        self.project_root = project_root.resolve()
        self.repository = repository or TrustedV2Repository(self.project_root, application_config)
        self.validator = validator or ReferenceNarrativeService(
            self.repository,
            DisabledNarrativeProvider(),
        )
        self.generators = {
            "orange_bank_compact": OrangeBankCompactNarrativePptxGenerator(self.project_root),
            "detailed_reference": NarrativePptxGenerator(self.project_root),
        }
        # Retained for compatibility with Phase 4/5 callers that inspect the
        # established detailed generator directly.
        self.generator = self.generators["detailed_reference"]
        self.content_generator = content_generator or PresentationCopyService(
            self.validator,
            self.validator.provider,
            self.project_root,
        )
        existing_config = yaml.safe_load(
            (self.project_root / "templates/reference_pack/v1/template_config.yaml").read_text(encoding="utf-8")
        )
        self.evidence_renderer = evidence_renderer or EvidenceRenderer(self.project_root, existing_config)
        self.pdf_converter = pdf_converter or LibreOfficePdfConverter(
            existing_config["generation"]["libreoffice_candidates"]
        )
        self.output_root = (self.project_root / existing_config["generation"]["output_root"]).resolve()
        self._assert_inside_project(self.output_root)
        self.output_root.mkdir(parents=True, exist_ok=True)

    def _assert_inside_project(self, path: Path) -> None:
        if path != self.project_root and self.project_root not in path.parents:
            raise RuntimeError("Narrative presentation storage escapes the authorized project")

    @staticmethod
    def _canonical_json(payload: Any) -> str:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _write_json(path: Path, payload: Any) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _new_directory(self, request_hash: str) -> tuple[str, Path]:
        for _ in range(5):
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            generation_id = f"narrative-pptx-{stamp}-{request_hash[:10]}"
            directory = (self.output_root / generation_id).resolve()
            self._assert_inside_project(directory)
            try:
                directory.mkdir(parents=False, exist_ok=False)
                return generation_id, directory
            except FileExistsError:
                continue
        raise RuntimeError("Could not allocate a unique narrative presentation generation ID")

    def _cleanup_generation(self, directory: Path) -> None:
        resolved = directory.resolve()
        self._assert_inside_project(resolved)
        if resolved.parent != self.output_root:
            raise RuntimeError("Refusing to clean an unexpected generation directory")
        if resolved.is_dir():
            shutil.rmtree(resolved)

    @staticmethod
    def _unicode_samples(request: NarrativePresentationRequest, review) -> list[str]:
        values = [
            review.narrative.section_intro.text,
            review.narrative.overall_storyline.text,
            review.narrative.why_these_references.text,
        ]
        for reference in review.narrative.references:
            values.extend(
                [
                    reference.headline.text,
                    reference.short_description.text,
                    reference.challenge.text,
                    reference.devoteam_contribution.text,
                    reference.why_relevant_to_opportunity.text,
                    *(item.text for item in reference.realisations),
                    *(item.text for item in reference.benefits),
                ]
            )
        values.append(request.generation_request.opportunity_title)
        return [value for value in values if value]

    @staticmethod
    def _reviewed_content(request: NarrativePresentationRequest, review) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "approved_narrative_status": "READY_FOR_PRESENTATION",
            "selected_reference_ids": list(request.approved_reference_ids),
            "generation_context": request.generation_request.model_dump(mode="json"),
            "narrative": {
                "section_intro": review.narrative.section_intro.text,
                "overall_storyline": review.narrative.overall_storyline.text,
                "why_these_references": review.narrative.why_these_references.text,
                "references": [
                    {
                        "reference_id": reference.reference_id,
                        "headline": reference.headline.text,
                        "short_description": reference.short_description.text,
                        "challenge": reference.challenge.text,
                        "devoteam_contribution": reference.devoteam_contribution.text,
                        "realisations": [item.text for item in reference.realisations],
                        "benefits": [item.text for item in reference.benefits],
                        "why_relevant_to_opportunity": reference.why_relevant_to_opportunity.text,
                        "detailed_presentation": (
                            {
                                "mission_title": reference.detailed_presentation.mission_title.text,
                                "challenges": [
                                    item.text for item in reference.detailed_presentation.challenges
                                ],
                                "realisations": [
                                    {
                                        "text": item.text.text,
                                        "subitems": [subitem.text for subitem in item.subitems],
                                    }
                                    for item in reference.detailed_presentation.realisations
                                ],
                                "benefits": [
                                    item.text for item in reference.detailed_presentation.benefits
                                ],
                            }
                            if reference.detailed_presentation is not None
                            else None
                        ),
                    }
                    for reference in review.narrative.references
                ],
            },
            "trusted_metadata": [item.model_dump(mode="json") for item in review.reference_metadata],
            "validation": {
                "export_eligible": review.validation.export_eligible,
                "warning_codes": [warning.code for warning in review.warnings],
            },
        }

    @staticmethod
    def _editable_review(review) -> EditableReferenceSectionNarrative:
        return EditableReferenceSectionNarrative(
            references=[
                ReferenceNarrativeDraft(
                    headline=reference.headline.text,
                    short_description=reference.short_description.text,
                    challenge=reference.challenge.text,
                    devoteam_contribution=reference.devoteam_contribution.text,
                    realisations=[item.text for item in reference.realisations],
                    benefits=[item.text for item in reference.benefits],
                    why_relevant_to_opportunity=reference.why_relevant_to_opportunity.text,
                )
                for reference in review.narrative.references
            ]
        )

    def generate_direct(
        self,
        request: DirectPresentationRequest,
        on_progress=None,
    ) -> NarrativePresentationResponse:
        if on_progress:
            on_progress({
                "event": "started",
                "message": "Preparing selected references",
                "total_references": len(request.selected_reference_ids),
            })
        copy_result = self.content_generator.generate(request, on_progress)
        opportunity = request.opportunity_context.strip() or "Selected reference presentation"
        legacy_request = NarrativePresentationRequest(
            generation_request=NarrativeGenerationRequest(
                selected_reference_ids=request.selected_reference_ids,
                opportunity_title=opportunity[:180],
                opportunity_description=opportunity,
                target_language=request.target_language,
                tone="commercial",
                audience="executive",
                detail_level="detailed",
            ),
            narrative=self._editable_review(copy_result.review),
            template_id=request.template_id,
            approved=True,
            approved_narrative_status="READY_FOR_PRESENTATION",
            approved_reference_ids=request.selected_reference_ids,
        )
        return self.generate(
            legacy_request,
            output_format=request.output_format,
            on_progress=on_progress,
            prevalidated_review=copy_result.review,
            copy_generation={
                "records": copy_result.generation_records,
                "timings": copy_result.timings,
                "provider": self.content_generator.provider.provider_name,
                "model": self.content_generator.provider.model_name,
                "template_budgets": self.content_generator.fit_profile.manifest(request.template_id),
            },
        )

    def generate(
        self,
        request: NarrativePresentationRequest,
        *,
        output_format: OutputFormat = "both",
        on_progress=None,
        prevalidated_review=None,
        copy_generation: dict[str, Any] | None = None,
    ) -> NarrativePresentationResponse:
        if not request.approved or request.approved_narrative_status != "READY_FOR_PRESENTATION":
            raise NarrativePresentationExportError(
                "NARRATIVE_NOT_APPROVED",
                "The narrative must be explicitly approved before PowerPoint generation.",
            )
        if request.approved_reference_ids != request.generation_request.selected_reference_ids:
            raise NarrativePresentationExportError(
                "NARRATIVE_REFERENCE_SET_CHANGED",
                "The approved reference set or order changed after review.",
            )

        # Revalidate at the export boundary even though direct copy was validated per unit.
        if prevalidated_review is None:
            validation_request = NarrativeEditValidationRequest(
                generation_request=request.generation_request,
                narrative=request.narrative,
            )
            review = self.validator.validate_edit(validation_request)
        else:
            review = prevalidated_review
        if request.template_id == "detailed_reference":
            for reference in review.narrative.references:
                if reference.detailed_presentation is not None:
                    continue
                challenge_lines = [
                    value.strip()
                    for value in reference.challenge.text.splitlines()
                    if value.strip()
                ]
                reference.detailed_presentation = SupportedDetailedPresentationCopy(
                    mission_title=reference.headline,
                    challenges=[
                        SupportedNarrativeText(
                            text=value,
                            support_ids=list(reference.challenge.support_ids),
                        )
                        for value in challenge_lines
                    ],
                    realisations=[
                        SupportedDetailedRealisation(text=item, subitems=[])
                        for item in reference.realisations
                    ],
                    benefits=list(reference.benefits),
                )
        blocking = [
            warning for warning in review.warnings
            if warning.severity == ValidationSeverity.BLOCKING or warning.blocking
        ]
        export_blocking = [
            warning for warning in blocking
            if not (
                copy_generation is not None
                and warning.code == "UNSUPPORTED_COMPLETION_LANGUAGE"
            )
        ]
        if export_blocking:
            raise NarrativePresentationExportError(
                "NARRATIVE_HAS_BLOCKING_WARNINGS",
                "Resolve blocking narrative findings before PowerPoint generation.",
                blocking_warning_codes=[warning.code for warning in export_blocking],
            )
        canonical_ids = [reference.reference_id for reference in review.narrative.references]
        if canonical_ids != request.approved_reference_ids:
            raise NarrativePresentationExportError(
                "NARRATIVE_REFERENCE_SET_CHANGED",
                "Trusted reference identity no longer matches the approved session.",
            )
        # Resolve every selected ID and its evidence lineage again at the export boundary.
        source_result = self.validator.source_builder.build(request.approved_reference_ids)
        trusted = source_result.references
        if [item.reference_id for item in trusted] != request.approved_reference_ids:
            raise NarrativePresentationExportError(
                "NARRATIVE_REFERENCE_SET_CHANGED",
                "Trusted reference resolution changed the approved order.",
            )

        reviewed_content = self._reviewed_content(request, review)
        reviewed_serialized = self._canonical_json(reviewed_content)
        reviewed_hash = hashlib.sha256(reviewed_serialized.encode("utf-8")).hexdigest()
        request_hash = hashlib.sha256(
            self._canonical_json(request.model_dump(mode="json")).encode("utf-8")
        ).hexdigest()
        generation_id, directory = self._new_directory(request_hash)
        reviewed_path = directory / "reviewed_content.json"
        pptx_path = directory / "narrative_reference_pack.pptx"
        pdf_path = directory / "narrative_reference_pack.pdf"
        render_dir = directory / ".evidence_render"
        generator = self.generators[request.template_id]
        try:
            evidence_selections = []
            if request.template_id == "orange_bank_compact":
                selected_evidence = choose_evidence(trusted, review, source_result.support_index)
                evidence_selections = render_evidence(
                    self.evidence_renderer,
                    selected_evidence,
                    render_dir,
                )
            if on_progress:
                on_progress({"event": "build_started", "message": "Building presentation…"})
            if request.template_id == "orange_bank_compact":
                result = generator.generate(
                    pptx_path,
                    request,
                    review,
                    evidence_selections,
                    trusted_references=trusted,
                    prevalidated_review=prevalidated_review,
                    copy_generation=copy_generation,
                )
            else:
                result = generator.generate(
                    pptx_path,
                    request,
                    review,
                    evidence_selections,
                    prevalidated_review=prevalidated_review,
                    copy_generation=copy_generation,
                )
        except PptxContentOverflowError as exc:
            self._cleanup_generation(directory)
            condition = exc.condition
            raise NarrativePresentationExportError(
                "PPTX_CONTENT_OVERFLOW",
                str(exc),
                reference_id=condition.reference_id,
                field=condition.field,
                estimated_required_lines=condition.required_lines,
                available_lines=condition.available_lines,
                minimum_font_pt=condition.minimum_font_pt,
            ) from exc
        except EvidenceRenderingError as exc:
            self._cleanup_generation(directory)
            raise NarrativePresentationExportError(
                exc.reason,
                exc.message,
                reference_id=exc.reference_id,
                document_id=exc.document_id,
                page=exc.page,
            ) from exc
        except ValueError as exc:
            self._cleanup_generation(directory)
            raise NarrativePresentationExportError(
                "EVIDENCE_PAGE_NOT_APPROVED",
                str(exc),
            ) from exc
        except Exception:
            self._cleanup_generation(directory)
            raise

        self._write_json(reviewed_path, reviewed_content)
        if render_dir.is_dir():
            shutil.rmtree(render_dir)

        pdf_result = None
        if output_format in {"pdf", "both"}:
            if on_progress:
                on_progress({"event": "pdf_started", "message": "Preparing PDF…"})
            try:
                pdf_result = self.pdf_converter.convert(
                    pptx_path,
                    pdf_path,
                    result.slide_count,
                    self._unicode_samples(request, review),
                )
                if pdf_result.path is None or pdf_result.validation.get("status") != "PASS":
                    raise NarrativePresentationExportError(
                        "PDF_CONVERSION_FAILED",
                        pdf_result.warning or "LibreOffice did not produce a validated PDF.",
                        conversion_validation=pdf_result.validation,
                    )
            except NarrativePresentationExportError:
                self._cleanup_generation(directory)
                raise
            except Exception as exc:
                self._cleanup_generation(directory)
                raise NarrativePresentationExportError(
                    "PDF_CONVERSION_FAILED",
                    str(exc),
                ) from exc

        generated_at = datetime.now(timezone.utc).isoformat()
        template_hash = generator.source_sha256
        nonblocking = [
            *[warning.code for warning in review.warnings if not warning.blocking],
            *result.export_warnings,
        ]
        identity = getattr(self.repository, "identity", None)
        manifest = {
            "schema_version": 3,
            "generation_id": generation_id,
            "generated_at_utc": generated_at,
            "status": "completed",
            "template_id": request.template_id,
            "template_display_name": TEMPLATE_DISPLAY_NAMES[request.template_id],
            "template_source_filename": generator.source_path.name,
            "template_source_sha256": template_hash,
            "selected_reference_ids": list(request.approved_reference_ids),
            "approved_narrative_status": "READY_FOR_PRESENTATION",
            "reviewed_content_sha256": reviewed_hash,
            "corpus_version": getattr(identity, "version", "unknown"),
            "narrative_slide_count": result.narrative_slide_count,
            "evidence_slide_count": result.evidence_slide_count,
            "total_slide_count": result.slide_count,
            "slide_count": result.slide_count,
            "reference_to_slide": result.reference_to_slide,
            "narrative_slide_mappings": result.narrative_slide_mappings,
            "reference_slide_mappings": result.reference_to_slide,
            "reference_to_evidence_slide": result.reference_to_evidence_slide,
            "evidence_pages": result.evidence_visuals,
            "font_substitution": result.font_substitution,
            "overflow_validation": result.overflow_validation,
            "approved_content_sha256": reviewed_hash,
            "approved_content_hash_validation": "PASS",
            "output_format": output_format,
            "presentation_copy_generation": copy_generation,
            "pdf_conversion_result": pdf_result.validation if pdf_result else {"status": "NOT_REQUESTED"},
            "warnings": nonblocking,
            "outputs": {
                "pptx": {
                    "filename": pptx_path.name,
                    "sha256": sha256_file(pptx_path),
                    "bytes": pptx_path.stat().st_size,
                },
                "reviewed_content": {
                    "filename": reviewed_path.name,
                    "sha256": sha256_file(reviewed_path),
                    "bytes": reviewed_path.stat().st_size,
                },
            },
        }
        if pdf_result:
            manifest["outputs"]["pdf"] = {
                "filename": pdf_path.name,
                "sha256": sha256_file(pdf_path),
                "bytes": pdf_path.stat().st_size,
            }
        self._write_json(directory / "generation_manifest.json", manifest)
        return NarrativePresentationResponse(
            generation_id=generation_id,
            status="completed",
            template_id=request.template_id,
            selected_reference_count=len(request.approved_reference_ids),
            slide_count=result.slide_count,
            pptx_download_url=(
                f"/api/presentations/{generation_id}/download/pptx"
                if output_format in {"pptx", "both"} else None
            ),
            pdf_download_url=(
                f"/api/presentations/{generation_id}/download/pdf"
                if output_format in {"pdf", "both"} else None
            ),
            manifest_download_url=f"/api/reference-narrative/presentations/{generation_id}/download/manifest",
            warnings=nonblocking,
        )

    def download_path(self, generation_id: str, kind: str) -> Path:
        filenames = {
            "pptx": "narrative_reference_pack.pptx",
            "pdf": "narrative_reference_pack.pdf",
            "manifest": "generation_manifest.json",
            "reviewed": "reviewed_content.json",
        }
        if not GENERATION_ID_RE.fullmatch(generation_id):
            raise ValueError("Invalid narrative presentation generation ID")
        if kind not in filenames:
            raise ValueError("Unsupported narrative presentation download type")
        directory = (self.output_root / generation_id).resolve()
        self._assert_inside_project(directory)
        path = (directory / filenames[kind]).resolve()
        if directory not in path.parents or not path.is_file():
            raise FileNotFoundError("Narrative presentation artifact was not found")
        return path
