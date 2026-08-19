from __future__ import annotations

from functools import lru_cache
from threading import Lock

from reference_narrative.ollama_client import create_narrative_provider
from reference_narrative.presentation_service import NarrativePresentationService
from reference_narrative.service import ReferenceNarrativeService
from reference_narrative.settings import get_reference_narrative_settings
from reference_pack.service import ReferencePackService
from reference_pack.validation import TrustedV2Repository
from retrieval.service import RetrievalService

from .settings import PROJECT_ROOT, load_config


_retrieval_service: RetrievalService | None = None
_retrieval_service_lock = Lock()


def get_retrieval_service() -> RetrievalService:
    global _retrieval_service
    if _retrieval_service is None:
        with _retrieval_service_lock:
            if _retrieval_service is None:
                _retrieval_service = RetrievalService(PROJECT_ROOT, load_config())
    return _retrieval_service


def service_is_loaded() -> bool:
    return _retrieval_service is not None


@lru_cache(maxsize=1)
def get_reference_pack_service() -> ReferencePackService:
    return ReferencePackService(PROJECT_ROOT, load_config())


@lru_cache(maxsize=1)
def get_reference_narrative_service() -> ReferenceNarrativeService:
    settings = get_reference_narrative_settings()
    repository = TrustedV2Repository(PROJECT_ROOT, load_config())
    return ReferenceNarrativeService(repository, create_narrative_provider(settings))


@lru_cache(maxsize=1)
def get_narrative_presentation_service() -> NarrativePresentationService:
    narrative_service = get_reference_narrative_service()
    return NarrativePresentationService(
        PROJECT_ROOT,
        load_config(),
        repository=narrative_service.repository,
        validator=narrative_service,
    )
