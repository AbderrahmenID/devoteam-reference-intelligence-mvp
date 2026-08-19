from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_NARRATIVE_CONNECT_TIMEOUT_SECONDS = 10.0
DEFAULT_NARRATIVE_GENERATION_TIMEOUT_SECONDS = 300.0


class ReferenceNarrativeSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="REFERENCE_NARRATIVE_",
        extra="ignore",
        case_sensitive=False,
    )

    provider: Literal["disabled", "ollama"] = "ollama"
    ollama_url: str = "http://localhost:11434"
    model: str = "qwen3.5:9b"
    connect_timeout_seconds: float = Field(
        default=DEFAULT_NARRATIVE_CONNECT_TIMEOUT_SECONDS,
        ge=1.0,
        le=10.0,
    )
    generation_timeout_seconds: float = Field(
        default=DEFAULT_NARRATIVE_GENERATION_TIMEOUT_SECONDS,
        ge=30.0,
        le=900.0,
    )

    @field_validator("ollama_url", "model", mode="before")
    @classmethod
    def strip_strings(cls, value: object) -> str:
        return str(value or "").strip()

@lru_cache(maxsize=1)
def get_reference_narrative_settings() -> ReferenceNarrativeSettings:
    return ReferenceNarrativeSettings()
