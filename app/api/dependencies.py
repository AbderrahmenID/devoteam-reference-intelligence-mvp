from __future__ import annotations

from functools import lru_cache

from retrieval.service import RetrievalService

from .settings import PROJECT_ROOT, load_config


@lru_cache(maxsize=1)
def get_retrieval_service() -> RetrievalService:
    return RetrievalService(PROJECT_ROOT, load_config())


def service_is_loaded() -> bool:
    return get_retrieval_service.cache_info().currsize > 0

