from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from extraction.pdf_extraction import extract_pdf
from retrieval.service import RetrievalService

from .dependencies import get_retrieval_service, service_is_loaded
from .models import (
    ConfigSummaryResponse,
    HealthResponse,
    SearchRequest,
    SearchResponse,
)
from .settings import PROJECT_ROOT, load_config, resolve_data_path


config = load_config()
app = FastAPI(
    title="Devoteam Multilingual Reference Retrieval MVP",
    version="0.1.0",
    description="Evidence retrieval only; this is not a chatbot.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(config["api"]["cors_origins"]),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    data_paths = [resolve_data_path(config["data"][key]) for key in (
        "chunks", "reference_catalog", "bm25_index", "bm25_vocabulary", "embeddings", "chunk_lookup"
    )]
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
    supported_filters = sorted(
        set(config["filters"]["supported_exact"]) | set(config["filters"]["supported_ranges"])
    )
    return ConfigSummaryResponse(
        model_id=config["model"]["id"], embedding_dimensions=int(config["model"]["dimensions"]),
        retrieval_mode="hybrid", maximum_results=int(config["hybrid"]["maximum_final_results"]),
        supported_languages=list(config["languages"]["supported"]), supported_filters=supported_filters,
        ocr_languages=config["languages"]["ocr_languages"],
        reranker_enabled=bool(config["reranker_enabled"]), debug_enabled=bool(config["api"]["debug"]),
    )


@app.post("/api/search", response_model=SearchResponse)
def search(
    request: SearchRequest,
    service: RetrievalService = Depends(get_retrieval_service),
) -> SearchResponse:
    try:
        return service.search(
            request.query,
            top_k=min(request.top_k, int(config["hybrid"]["maximum_final_results"])),
            filters=request.filters.model_dump(exclude_none=True) if request.filters else None,
            debug=bool(request.debug and config["api"]["debug"]),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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
            temporary_path, extraction_config,
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
