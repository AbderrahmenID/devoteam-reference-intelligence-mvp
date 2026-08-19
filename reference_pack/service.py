from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .content_builder import prepare_reference
from .pdf_converter import LibreOfficePdfConverter
from .pptx_generator import PowerPointGenerator
from .schemas import GenerationArtifacts, ReferencePackRequest, ReferencePackResponse
from .validation import ReferenceValidationError, TrustedV2Repository, sha256_file


GENERATION_ID_RE = re.compile(r"reference-pack-[0-9]{8}T[0-9]{12}Z-[0-9a-f]{10}")


class ReferencePackService:
    def __init__(self, project_root: Path, application_config: dict[str, Any]):
        self.project_root = project_root.resolve()
        self.application_config = application_config
        self.template_path = self.project_root / "templates/reference_pack/v1/template_config.yaml"
        self.template = yaml.safe_load(self.template_path.read_text(encoding="utf-8"))
        self._validate_template()
        self.repository = TrustedV2Repository(self.project_root, application_config)
        self.output_root = (self.project_root / self.template["generation"]["output_root"]).resolve()
        self._assert_inside_project(self.output_root)
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.converter = LibreOfficePdfConverter(self.template["generation"]["libreoffice_candidates"])

    def _assert_inside_project(self, path: Path) -> None:
        if path != self.project_root and self.project_root not in path.parents:
            raise RuntimeError("Reference-pack storage escapes the authorized project")

    def _validate_template(self) -> None:
        if self.template.get("template_id") != "DEVOTEAM_REFERENCE_PACK_V1":
            raise RuntimeError("Unexpected reference-pack template ID")
        source = (self.project_root / self.template["source_pdf"]).resolve()
        self._assert_inside_project(source)
        if sha256_file(source) != str(self.template["source_pdf_sha256"]).casefold():
            raise RuntimeError("Reference-pack source PDF hash mismatch")
        logo = (self.project_root / self.template["footer"]["logo_path"]).resolve()
        self._assert_inside_project(logo)
        if not logo.is_file():
            raise RuntimeError("Approved Devoteam logo is missing")

    def _application_version(self) -> str:
        pyproject = (self.project_root / "pyproject.toml").read_text(encoding="utf-8")
        match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.MULTILINE)
        return match.group(1) if match else "unknown"

    def _new_generation_directory(self, request_hash: str) -> tuple[str, Path]:
        for _ in range(5):
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            generation_id = f"reference-pack-{stamp}-{request_hash[:10]}"
            directory = (self.output_root / generation_id).resolve()
            self._assert_inside_project(directory)
            try:
                directory.mkdir(parents=False, exist_ok=False)
                return generation_id, directory
            except FileExistsError:
                continue
        raise RuntimeError("Could not allocate a unique reference-pack generation ID")

    @staticmethod
    def _write_json(path: Path, payload: Any) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def _response_from_manifest(manifest: dict[str, Any]) -> ReferencePackResponse:
        generation_id = manifest["generation_id"]
        formats = set(manifest["requested_output_formats"])
        pdf_ok = bool(manifest["outputs"].get("pdf", {}).get("sha256"))
        pptx_ok = bool(manifest["outputs"].get("pptx", {}).get("sha256"))
        pptx_url = None
        if pptx_ok and ("pptx" in formats or ("pdf" in formats and not pdf_ok)):
            pptx_url = f"/api/reference-packs/{generation_id}/download/pptx"
        return ReferencePackResponse(
            generation_id=generation_id,
            status=manifest["status"],
            selected_reference_count=len(manifest["selected_reference_ids"]),
            slide_count=int(manifest["slide_count"]),
            pptx_download_url=pptx_url,
            pdf_download_url=(f"/api/reference-packs/{generation_id}/download/pdf" if pdf_ok else None),
            manifest_download_url=f"/api/reference-packs/{generation_id}/download/manifest",
            warnings=list(manifest.get("generation_warnings", [])),
        )

    def generate(self, request: ReferencePackRequest) -> GenerationArtifacts:
        started = time.perf_counter()
        canonical = json.dumps(request.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        request_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        references = self.repository.load_selected(request.reference_ids)
        prepared = [prepare_reference(reference, request.language) for reference in references]
        empty_evidence = [item.reference.reference_id for item in prepared if not item.evidence_items]
        if empty_evidence:
            raise ReferenceValidationError(
                "DISPLAY_EVIDENCE_REQUIRED", empty_evidence, "Display-approved evidence could not be prepared"
            )

        generation_id, directory = self._new_generation_directory(request_hash)
        created_at = datetime.now(timezone.utc).isoformat()
        log: dict[str, Any] = {
            "generation_id": generation_id,
            "created_at_utc": created_at,
            "request_sha256": request_hash,
            "stages": [],
        }
        self._write_json(directory / "generation_request.json", request.model_dump(mode="json"))
        try:
            pptx_path = directory / "reference_pack.pptx"
            stage_started = time.perf_counter()
            pptx_result = PowerPointGenerator(self.project_root, self.template).generate(
                pptx_path, request, prepared
            )
            log["stages"].append(
                {
                    "name": "pptx_generation_and_validation",
                    "status": "PASS",
                    "duration_ms": round((time.perf_counter() - stage_started) * 1000, 2),
                    "validation": pptx_result.validation,
                }
            )

            warnings: list[str] = []
            pdf_result = None
            if "pdf" in request.output_formats:
                stage_started = time.perf_counter()
                pdf_result = self.converter.convert(
                    pptx_path,
                    directory / "reference_pack.pdf",
                    pptx_result.slide_count,
                    [request.title, request.client_name, request.subtitle or ""],
                )
                if pdf_result.warning:
                    warnings.append(pdf_result.warning)
                log["stages"].append(
                    {
                        "name": "pdf_conversion_and_validation",
                        "status": pdf_result.validation.get("status", "FAIL"),
                        "duration_ms": round((time.perf_counter() - stage_started) * 1000, 2),
                        "command": pdf_result.command,
                        "validation": pdf_result.validation,
                    }
                )

            source_documents: dict[tuple[str, str], dict[str, Any]] = {}
            evidence_chunk_ids: list[str] = []
            source_pages: list[dict[str, Any]] = []
            for reference in references:
                for evidence in reference.evidence:
                    key = (evidence.document_id, evidence.source_sha256)
                    record = source_documents.setdefault(
                        key,
                        {
                            "document_id": evidence.document_id,
                            "source_file_name": evidence.source_file_name,
                            "source_sha256": evidence.source_sha256,
                            "pages": [],
                        },
                    )
                    if evidence.source_page not in record["pages"]:
                        record["pages"].append(evidence.source_page)
                    source_pages.append(
                        {
                            "reference_id": reference.reference_id,
                            "document_id": evidence.document_id,
                            "source_sha256": evidence.source_sha256,
                            "source_page": evidence.source_page,
                            "chunk_id": evidence.chunk_id,
                            "citation_label": evidence.citation_label,
                        }
                    )
                    evidence_chunk_ids.append(evidence.chunk_id)

            pptx_hash = sha256_file(pptx_path)
            pdf_path = directory / "reference_pack.pdf"
            pdf_hash = sha256_file(pdf_path) if pdf_path.is_file() else None
            status = "completed_with_warnings" if warnings else "completed"
            exact_command = f"POST /api/reference-packs request_sha256={request_hash}"
            manifest = {
                "schema_version": 2,
                "generation_id": generation_id,
                "created_at_utc": created_at,
                "status": status,
                "selected_reference_ids": list(request.reference_ids),
                "selected_ordering": [
                    {"position": index, "reference_id": reference_id}
                    for index, reference_id in enumerate(request.reference_ids, start=1)
                ],
                "requested_output_formats": list(request.output_formats),
                "corpus_version": self.repository.identity.version,
                "corpus_manifest_path": self.repository.identity.manifest_path.relative_to(self.project_root).as_posix(),
                "corpus_manifest_sha256": self.repository.identity.manifest_sha256,
                "corpus_artifact_hashes": {
                    "chunks": self.repository.identity.chunks_sha256,
                    "reference_catalog": self.repository.identity.reference_catalog_sha256,
                },
                "template_id": self.template["template_id"],
                "template_version": self.template["version"],
                "template_pdf_sha256": self.template["source_pdf_sha256"],
                "source_documents": list(source_documents.values()),
                "source_pages": source_pages,
                "evidence_chunk_ids": list(dict.fromkeys(evidence_chunk_ids)),
                "evidence_visuals": pptx_result.evidence_visuals,
                "slide_count": pptx_result.slide_count,
                "slide_provenance": [item.model_dump(mode="json") for item in pptx_result.slide_provenance],
                "application_version": self._application_version(),
                "outputs": {
                    "pptx": {"filename": "reference_pack.pptx", "sha256": pptx_hash, "bytes": pptx_path.stat().st_size},
                    "pdf": ({"filename": "reference_pack.pdf", "sha256": pdf_hash, "bytes": pdf_path.stat().st_size} if pdf_hash else {}),
                },
                "generation_warnings": warnings,
                "exact_generation_command": exact_command,
                "request_sha256": request_hash,
                "validation": {
                    "pptx": pptx_result.validation,
                    "pdf": pdf_result.validation if pdf_result else {"status": "NOT_REQUESTED"},
                },
                "generation_latency_ms": round((time.perf_counter() - started) * 1000, 2),
            }
            self._write_json(directory / "generation_manifest.json", manifest)
            log["status"] = status
            log["duration_ms"] = manifest["generation_latency_ms"]
            log["warnings"] = warnings
            self._write_json(directory / "generation_log.json", log)
            response = self._response_from_manifest(manifest)
            return GenerationArtifacts(response=response, directory=str(directory), manifest=manifest)
        except Exception as exc:
            log["status"] = "failed"
            log["duration_ms"] = round((time.perf_counter() - started) * 1000, 2)
            log["error_type"] = type(exc).__name__
            log["error"] = str(exc)
            self._write_json(directory / "generation_log.json", log)
            raise

    def _directory(self, generation_id: str) -> Path:
        if not GENERATION_ID_RE.fullmatch(generation_id):
            raise ValueError("Invalid generation ID")
        directory = (self.output_root / generation_id).resolve()
        self._assert_inside_project(directory)
        if not directory.is_dir():
            raise FileNotFoundError("Reference-pack generation was not found")
        return directory

    def get(self, generation_id: str) -> ReferencePackResponse:
        manifest_path = self._directory(generation_id) / "generation_manifest.json"
        if not manifest_path.is_file():
            raise FileNotFoundError("Reference-pack generation is incomplete")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("generation_id") != generation_id:
            raise RuntimeError("Generation manifest ID mismatch")
        return self._response_from_manifest(manifest)

    def download_path(self, generation_id: str, kind: str) -> Path:
        filenames = {
            "pptx": "reference_pack.pptx",
            "pdf": "reference_pack.pdf",
            "manifest": "generation_manifest.json",
        }
        if kind not in filenames:
            raise ValueError("Unsupported reference-pack download type")
        directory = self._directory(generation_id)
        path = (directory / filenames[kind]).resolve()
        if directory not in path.parents or not path.is_file():
            raise FileNotFoundError(f"Requested {kind} artifact is unavailable")
        return path
