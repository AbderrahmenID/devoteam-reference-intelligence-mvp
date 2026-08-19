from __future__ import annotations

import hashlib
import json
import tempfile
from datetime import datetime
from pathlib import Path
from queue import Queue
from threading import Thread

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from starlette.background import BackgroundTask

from exporting.docx_export import export_docx
from extraction.pdf_extraction import extract_pdf
from reference_narrative.ollama_client import (
    NarrativeModelUnavailableError,
    NarrativeProviderDisabledError,
    NarrativeProviderResponseError,
    NarrativeProviderTimeoutError,
    NarrativeProviderUnavailableError,
)
from reference_narrative.presentation_schemas import (
    DirectPresentationRequest,
    NarrativePresentationRequest,
    NarrativePresentationResponse,
)
from reference_narrative.presentation_service import (
    NarrativePresentationExportError,
    NarrativePresentationService,
)
from reference_narrative.schemas import (
    NarrativeEditValidationRequest,
    NarrativeGenerationRequest,
    NarrativeGenerationResponse,
    NarrativeRegenerationRequest,
    NarrativeReviewResponse,
)
from reference_narrative.service import NarrativeStructuredOutputError, ReferenceNarrativeService
from reference_pack.schemas import ReferencePackRequest, ReferencePackResponse
from reference_pack.service import ReferencePackService
from reference_pack.validation import ReferenceValidationError
from retrieval.service import RetrievalService

from .dependencies import (
    get_narrative_presentation_service,
    get_reference_narrative_service,
    get_reference_pack_service,
    get_retrieval_service,
    service_is_loaded,
)
from .models import (
    ConfigSummaryResponse,
    ExportRequest,
    HealthResponse,
    SearchFilters,
    SearchRequest,
    SearchResponse,
)
from .settings import PROJECT_ROOT, load_config, resolve_data_path


config = load_config()
app = FastAPI(
    title="Devoteam Multilingual Reference Retrieval MVP",
    version="0.3.0",
    description="Filtered evidence retrieval and deterministic source-grounded document generation; this is not a chatbot.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(config["api"]["cors_origins"]),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
    expose_headers=["Content-Disposition", "X-Reference-Count", "X-Document-SHA256"],
)


def _filter_dict(filters: SearchFilters | None) -> dict | None:
    return filters.model_dump(exclude_none=True) if filters else None


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    data_paths = [
        resolve_data_path(config["data"][key])
        for key in ("chunks", "reference_catalog", "bm25_index", "bm25_vocabulary", "embeddings", "chunk_lookup")
    ]
    model_path = Path(config["model"]["local_path"]).expanduser().resolve()
    data_ready = all(path.is_file() for path in data_paths)
    model_available = model_path.is_dir()
    return HealthResponse(
        status="ok" if data_ready and model_available else "degraded",
        data_ready=data_ready,
        model_available=model_available,
        service_loaded=service_is_loaded(),
        reranker_enabled=bool(config["reranker_enabled"]),
    )


@app.get("/api/config-summary", response_model=ConfigSummaryResponse)
def config_summary() -> ConfigSummaryResponse:
    supported_filters = [
        "period",
        "country",
        "sector",
        "client",
        "offering",
        "service_nature",
        "technology",
        "status",
        "evidence_available",
        "evidence_type",
        "language",
        "themes",
        "business_unit",
        "data_quality_status",
        "attestation_available",
        "document_type",
    ]
    return ConfigSummaryResponse(
        model_id=config["model"]["id"],
        embedding_dimensions=int(config["model"]["dimensions"]),
        retrieval_mode="hybrid",
        maximum_results=int(config["search"]["safety_ceiling"]),
        default_page_size=int(config["search"]["default_page_size"]),
        page_sizes=[int(value) for value in config["search"]["page_sizes"]],
        supported_sorts=list(config["search"]["sorts"]),
        supported_languages=list(config["languages"]["supported"]),
        supported_filters=supported_filters,
        ocr_languages=config["languages"]["ocr_languages"],
        reranker_enabled=bool(config["reranker_enabled"]),
        debug_enabled=bool(config["api"]["debug"]),
    )


@app.get("/api/facets")
def facets(
    filters: str | None = Query(
        default=None,
        description="Optional URL-encoded JSON object using the same filter schema as /api/search.",
    ),
    service: RetrievalService = Depends(get_retrieval_service),
) -> dict:
    try:
        parsed = None
        if filters:
            payload = json.loads(filters)
            parsed_model = SearchFilters.model_validate(payload)
            parsed = parsed_model.model_dump(exclude_none=True)
        return service.facets(parsed)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/search", response_model=SearchResponse)
def search(
    request: SearchRequest,
    service: RetrievalService = Depends(get_retrieval_service),
) -> SearchResponse:
    try:
        return service.search(
            query=request.query,
            filters=_filter_dict(request.filters),
            page=request.page,
            page_size=request.page_size,
            sort=request.sort,
            debug=bool(request.debug and config["api"]["debug"]),
            include_facets=request.include_facets,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/export/docx")
def export_references_docx(
    request: ExportRequest,
    service: RetrievalService = Depends(get_retrieval_service),
) -> FileResponse:
    if not bool(config["export"]["enabled"]):
        raise HTTPException(status_code=503, detail="DOCX export is disabled")
    try:
        outcome = service.all_results(
            query=request.query,
            filters=_filter_dict(request.filters),
            sort=request.sort,
        )
        if outcome.abstained or not outcome.results:
            raise HTTPException(status_code=422, detail=outcome.abstention_reason)
        result_by_id = {result.reference_id: result for result in outcome.results}
        if request.export_all_filtered:
            selected = outcome.results
        else:
            invalid_ids = [
                reference_id
                for reference_id in request.selected_reference_ids
                if reference_id not in result_by_id
            ]
            if invalid_ids:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "reason": "INVALID_REFERENCE_SELECTION",
                        "reference_ids": invalid_ids,
                    },
                )
            selected = [result_by_id[reference_id] for reference_id in request.selected_reference_ids]
        maximum = int(config["export"]["maximum_references_per_export"])
        if len(selected) > maximum:
            raise HTTPException(status_code=422, detail=f"Export exceeds the {maximum}-reference ceiling")

        output_dir = (PROJECT_ROOT / config["export"]["output_dir"]).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        fingerprint = hashlib.sha256(
            (request.query + "\n" + "\n".join(result.reference_id for result in selected)).encode("utf-8")
        ).hexdigest()[:8]
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        filename = f"{config['export']['filename_prefix']}-{timestamp}-{len(selected)}-{fingerprint}.docx"
        output_path = output_dir / filename
        artifact = export_docx(
            template_path=(PROJECT_ROOT / config["export"]["template_path"]).resolve(),
            output_path=output_path,
            results=selected,
            query=request.query,
            options=request.options.model_dump(),
            expected_template_sha256=str(config["export"]["template_sha256"]),
        )
        return FileResponse(
            artifact.path,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename=filename,
            headers={
                "X-Reference-Count": str(artifact.reference_count),
                "X-Document-SHA256": artifact.sha256,
            },
            background=BackgroundTask(artifact.path.unlink, missing_ok=True),
        )
    except HTTPException:
        raise
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/reference-packs", response_model=ReferencePackResponse, status_code=201)
def generate_reference_pack(
    request: ReferencePackRequest,
    service: ReferencePackService = Depends(get_reference_pack_service),
) -> ReferencePackResponse:
    try:
        return service.generate(request).response
    except ReferenceValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.as_detail()) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=500,
            detail={"reason": "REFERENCE_PACK_GENERATION_FAILED", "message": str(exc)},
        ) from exc


@app.post("/api/reference-narrative/generate", response_model=NarrativeGenerationResponse)
def generate_reference_narrative(
    request: NarrativeGenerationRequest,
    service: ReferenceNarrativeService = Depends(get_reference_narrative_service),
) -> NarrativeGenerationResponse:
    """Generate a source-grounded draft after explicit reference selection."""
    try:
        return service.generate(request)
    except ReferenceValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.as_detail()) from exc
    except NarrativeProviderDisabledError as exc:
        raise HTTPException(
            status_code=503,
            detail={"reason": "REFERENCE_NARRATIVE_DISABLED", "message": str(exc)},
        ) from exc
    except NarrativeModelUnavailableError as exc:
        raise HTTPException(
            status_code=503,
            detail={"reason": "REFERENCE_NARRATIVE_MODEL_UNAVAILABLE", "message": str(exc)},
        ) from exc
    except NarrativeProviderTimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail={"reason": "REFERENCE_NARRATIVE_CONNECTION_TIMEOUT", "message": str(exc)},
        ) from exc
    except NarrativeProviderUnavailableError as exc:
        raise HTTPException(
            status_code=503,
            detail={"reason": "REFERENCE_NARRATIVE_PROVIDER_UNAVAILABLE", "message": str(exc)},
        ) from exc
    except (NarrativeProviderResponseError, NarrativeStructuredOutputError) as exc:
        raise HTTPException(
            status_code=502,
            detail={"reason": "REFERENCE_NARRATIVE_INVALID_RESPONSE", "message": str(exc)},
        ) from exc


@app.post("/api/reference-narrative/generate-stream")
def stream_reference_narrative(
    request: NarrativeGenerationRequest,
    service: ReferenceNarrativeService = Depends(get_reference_narrative_service),
) -> StreamingResponse:
    """Stream section-first generation progress as newline-delimited JSON."""

    def events():
        queue: Queue[dict[str, object] | None] = Queue()

        def publish(event: dict[str, object]) -> None:
            queue.put(event)

        def run_generation() -> None:
            try:
                service.generate_progressive(request, publish)
            except ReferenceValidationError as exc:
                publish({"event": "fatal", "reason": exc.reason, "message": exc.detail})
            except NarrativeProviderDisabledError as exc:
                publish({"event": "fatal", "reason": "REFERENCE_NARRATIVE_DISABLED", "message": str(exc)})
            except NarrativeModelUnavailableError as exc:
                publish({"event": "fatal", "reason": "REFERENCE_NARRATIVE_MODEL_UNAVAILABLE", "message": str(exc)})
            except NarrativeProviderTimeoutError as exc:
                publish({"event": "fatal", "reason": "REFERENCE_NARRATIVE_CONNECTION_TIMEOUT", "message": str(exc)})
            except NarrativeProviderUnavailableError as exc:
                publish({"event": "fatal", "reason": "REFERENCE_NARRATIVE_PROVIDER_UNAVAILABLE", "message": str(exc)})
            except (NarrativeProviderResponseError, NarrativeStructuredOutputError) as exc:
                publish({"event": "fatal", "reason": "REFERENCE_NARRATIVE_INVALID_RESPONSE", "message": str(exc)})
            finally:
                queue.put(None)

        Thread(target=run_generation, name="reference-narrative-stream", daemon=True).start()
        while True:
            event = queue.get()
            if event is None:
                break
            yield json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"

    return StreamingResponse(
        events(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@app.post("/api/reference-narrative/validate", response_model=NarrativeReviewResponse)
def validate_reference_narrative(
    request: NarrativeEditValidationRequest,
    service: ReferenceNarrativeService = Depends(get_reference_narrative_service),
) -> NarrativeReviewResponse:
    """Rebuild canonical provenance and validate browser-edited prose."""
    try:
        return service.validate_edit(request)
    except ReferenceValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.as_detail()) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/reference-narrative/regenerate", response_model=NarrativeReviewResponse)
def regenerate_reference_narrative(
    request: NarrativeRegenerationRequest,
    service: ReferenceNarrativeService = Depends(get_reference_narrative_service),
) -> NarrativeReviewResponse:
    """Regenerate one supported review scope and revalidate the canonical result."""
    try:
        return service.regenerate(request)
    except ReferenceValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.as_detail()) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except NarrativeProviderDisabledError as exc:
        raise HTTPException(
            status_code=503,
            detail={"reason": "REFERENCE_NARRATIVE_DISABLED", "message": str(exc)},
        ) from exc
    except NarrativeModelUnavailableError as exc:
        raise HTTPException(
            status_code=503,
            detail={"reason": "REFERENCE_NARRATIVE_MODEL_UNAVAILABLE", "message": str(exc)},
        ) from exc
    except NarrativeProviderTimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail={"reason": "REFERENCE_NARRATIVE_CONNECTION_TIMEOUT", "message": str(exc)},
        ) from exc
    except NarrativeProviderUnavailableError as exc:
        raise HTTPException(
            status_code=503,
            detail={"reason": "REFERENCE_NARRATIVE_PROVIDER_UNAVAILABLE", "message": str(exc)},
        ) from exc
    except (NarrativeProviderResponseError, NarrativeStructuredOutputError) as exc:
        raise HTTPException(
            status_code=502,
            detail={"reason": "REFERENCE_NARRATIVE_INVALID_RESPONSE", "message": str(exc)},
        ) from exc


@app.post(
    "/api/presentations/generate-stream",
)
def generate_presentation_stream(
    request: DirectPresentationRequest,
    service: NarrativePresentationService = Depends(get_narrative_presentation_service),
) -> StreamingResponse:
    """Generate presentation copy and artifacts directly from selected references."""

    def events():
        queue: Queue[dict[str, object] | None] = Queue()

        def publish(event: dict[str, object]) -> None:
            queue.put(event)

        def run_generation() -> None:
            try:
                response = service.generate_direct(request, publish)
                publish({
                    "event": "completed",
                    "message": "Your presentation is ready",
                    "response": response.model_dump(mode="json"),
                })
            except NarrativePresentationExportError as exc:
                publish({"event": "fatal", **exc.as_detail()})
            except ReferenceValidationError as exc:
                publish({"event": "fatal", **exc.as_detail()})
            except Exception as exc:
                publish({
                    "event": "fatal",
                    "reason": "PRESENTATION_GENERATION_FAILED",
                    "message": str(exc),
                })
            finally:
                queue.put(None)

        Thread(target=run_generation, name="direct-presentation-stream", daemon=True).start()
        while True:
            event = queue.get()
            if event is None:
                break
            yield json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"

    return StreamingResponse(
        events(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@app.post(
    "/api/reference-narrative/presentations",
    response_model=NarrativePresentationResponse,
    status_code=201,
)
def generate_narrative_presentation(
    request: NarrativePresentationRequest,
    service: NarrativePresentationService = Depends(get_narrative_presentation_service),
) -> NarrativePresentationResponse:
    """Map approved prose and reloaded trusted facts into editable PowerPoint objects."""
    try:
        return service.generate(request)
    except NarrativePresentationExportError as exc:
        raise HTTPException(status_code=422, detail=exc.as_detail()) from exc
    except ReferenceValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.as_detail()) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=500,
            detail={"reason": "PPTX_GENERATION_FAILED", "message": str(exc)},
        ) from exc


@app.get("/api/reference-narrative/presentations/{generation_id}/download/{kind}")
def download_narrative_presentation(
    generation_id: str,
    kind: str,
    service: NarrativePresentationService = Depends(get_narrative_presentation_service),
) -> FileResponse:
    media_types = {
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "pdf": "application/pdf",
        "manifest": "application/json",
        "reviewed": "application/json",
    }
    try:
        path = service.download_path(generation_id, kind)
        return FileResponse(path, media_type=media_types[kind], filename=path.name)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/presentations/{generation_id}/download/{kind}")
def download_direct_presentation(
    generation_id: str,
    kind: str,
    service: NarrativePresentationService = Depends(get_narrative_presentation_service),
) -> FileResponse:
    media_types = {
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "pdf": "application/pdf",
        "manifest": "application/json",
    }
    try:
        path = service.download_path(generation_id, kind)
        return FileResponse(path, media_type=media_types[kind], filename=path.name)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/reference-packs/{generation_id}", response_model=ReferencePackResponse)
def reference_pack_status(
    generation_id: str,
    service: ReferencePackService = Depends(get_reference_pack_service),
) -> ReferencePackResponse:
    try:
        return service.get(generation_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/reference-packs/{generation_id}/download/{kind}")
def download_reference_pack(
    generation_id: str,
    kind: str,
    service: ReferencePackService = Depends(get_reference_pack_service),
) -> FileResponse:
    media_types = {
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "pdf": "application/pdf",
        "manifest": "application/json",
    }
    try:
        path = service.download_path(generation_id, kind)
        return FileResponse(path, media_type=media_types[kind], filename=path.name)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/extract-preview")
async def extract_preview(file: UploadFile = File(...)) -> dict:
    if not file.filename or not file.filename.casefold().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="A PDF file is required")
    maximum = int(config["extraction"]["preview_max_bytes"])
    content = await file.read(maximum + 1)
    if len(content) > maximum:
        raise HTTPException(status_code=413, detail=f"PDF exceeds the {maximum}-byte preview limit")
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix="devoteam_preview_", suffix=".pdf", delete=False) as stream:
            stream.write(content)
            temporary_path = Path(stream.name)
        extraction_config = dict(config["extraction"])
        extraction_config["ocr_languages"] = config["languages"]["ocr_languages"]
        result = extract_pdf(
            temporary_path,
            extraction_config,
            max_pages=int(config["extraction"]["preview_max_pages"]),
        )
        source_name = Path(file.filename).name
        result["source_filename"] = source_name
        for page in result["pages"]:
            page["source_filename"] = source_name
        for chunk in result["chunks"]:
            chunk["source_filename"] = source_name
        return result
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        if temporary_path and temporary_path.is_file():
            temporary_path.unlink()
