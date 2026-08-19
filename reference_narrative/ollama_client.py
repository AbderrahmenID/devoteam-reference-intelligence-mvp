from __future__ import annotations

from threading import Lock
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx

from .settings import ReferenceNarrativeSettings


class NarrativeProviderError(RuntimeError):
    """Base error for a local narrative provider failure."""


class NarrativeProviderDisabledError(NarrativeProviderError):
    pass


class NarrativeProviderUnavailableError(NarrativeProviderError):
    pass


class NarrativeProviderTimeoutError(NarrativeProviderError):
    pass


class NarrativeModelUnavailableError(NarrativeProviderError):
    pass


class NarrativeProviderResponseError(NarrativeProviderError):
    pass


class NarrativeProvider(Protocol):
    provider_name: str
    model_name: str

    def generate(self, messages: list[dict[str, str]], response_schema: dict[str, Any]) -> str:
        ...


class DisabledNarrativeProvider:
    provider_name = "disabled"
    model_name = ""

    def generate(self, messages: list[dict[str, str]], response_schema: dict[str, Any]) -> str:
        del messages, response_schema
        raise NarrativeProviderDisabledError(
            "Reference narrative generation is disabled. Set REFERENCE_NARRATIVE_PROVIDER=ollama "
            "and configure REFERENCE_NARRATIVE_MODEL to enable it."
        )


class UnavailableOllamaProvider:
    provider_name = "ollama"

    def __init__(self, model_name: str, message: str, *, missing_model: bool):
        self.model_name = model_name
        self.message = message
        self.missing_model = missing_model

    def generate(self, messages: list[dict[str, str]], response_schema: dict[str, Any]) -> str:
        del messages, response_schema
        error_type = NarrativeModelUnavailableError if self.missing_model else NarrativeProviderUnavailableError
        raise error_type(self.message)


class OllamaNarrativeClient:
    provider_name = "ollama"
    keep_alive = "10m"

    def __init__(
        self,
        base_url: str,
        model: str,
        connect_timeout_seconds: float,
        generation_timeout_seconds: float = 300.0,
    ):
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("REFERENCE_NARRATIVE_OLLAMA_URL must use a loopback host")
        if not model.strip():
            raise ValueError("An Ollama model must be configured")
        self.base_url = base_url.rstrip("/")
        self.model_name = model.strip()
        self.connect_timeout_seconds = min(float(connect_timeout_seconds), 10.0)
        self.generation_timeout_seconds = min(max(float(generation_timeout_seconds), 30.0), 900.0)
        # A bounded read prevents one local model call from hanging the entire
        # selected-reference deck indefinitely.
        self.timeout = httpx.Timeout(
            self.generation_timeout_seconds,
            connect=self.connect_timeout_seconds,
        )
        self.generation_stats: list[dict[str, int | float | None]] = []
        self._warm_lock = Lock()
        self._model_warmed = False

    def _raise_for_status(self, response: httpx.Response, operation: str) -> None:
        if response.status_code == 404:
            raise NarrativeModelUnavailableError(
                f"The configured Ollama model is unavailable: {self.model_name}"
            )
        if response.status_code >= 400:
            raise NarrativeProviderUnavailableError(
                f"Ollama returned HTTP {response.status_code} for the {operation} request"
            )

    def _warm_model(self) -> None:
        if self._model_warmed:
            return
        with self._warm_lock:
            if self._model_warmed:
                return
            try:
                response = httpx.get(f"{self.base_url}/api/ps", timeout=self.timeout)
                self._raise_for_status(response, "model-status")
                body = response.json()
            except (ValueError, KeyError, TypeError):
                body = {"models": []}
            except httpx.RequestError as exc:
                raise NarrativeProviderUnavailableError("The local Ollama server is unavailable") from exc

            loaded_models = {
                str(value)
                for item in body.get("models", [])
                if isinstance(item, dict)
                for value in (item.get("name"), item.get("model"))
                if value
            }
            if self.model_name not in loaded_models:
                try:
                    response = httpx.post(
                        f"{self.base_url}/api/generate",
                        json={
                            "model": self.model_name,
                            "prompt": "",
                            "stream": False,
                            "keep_alive": self.keep_alive,
                        },
                        timeout=self.timeout,
                    )
                except httpx.TimeoutException as exc:
                    raise NarrativeProviderTimeoutError("Connecting to the local Ollama server timed out") from exc
                except httpx.RequestError as exc:
                    raise NarrativeProviderUnavailableError("The local Ollama server is unavailable") from exc
                self._raise_for_status(response, "model warm-up")
            self._model_warmed = True

    def generate(self, messages: list[dict[str, str]], response_schema: dict[str, Any]) -> str:
        self._warm_model()
        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
            "think": False,
            "keep_alive": self.keep_alive,
            "format": response_schema,
            "options": {
                "temperature": 0,
                "num_ctx": 8192,
                "num_predict": 768,
            },
        }
        try:
            response = httpx.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=self.timeout,
            )
        except httpx.TimeoutException as exc:
            raise NarrativeProviderTimeoutError(
                f"Local model generation exceeded {self.generation_timeout_seconds:g} seconds"
            ) from exc
        except httpx.RequestError as exc:
            raise NarrativeProviderUnavailableError("The local Ollama server is unavailable") from exc

        self._raise_for_status(response, "generation")
        try:
            body = response.json()
            content = body["message"]["content"]
        except (ValueError, KeyError, TypeError) as exc:
            raise NarrativeProviderResponseError("Ollama returned a malformed response envelope") from exc
        if not isinstance(content, str) or not content.strip():
            raise NarrativeProviderResponseError("Ollama returned an empty structured response")
        self.generation_stats.append(
            {
                "prompt_token_count": body.get("prompt_eval_count"),
                "generated_token_count": body.get("eval_count"),
                "total_duration_ns": body.get("total_duration"),
                "load_duration_ns": body.get("load_duration"),
                "prompt_eval_duration_ns": body.get("prompt_eval_duration"),
                "eval_duration_ns": body.get("eval_duration"),
            }
        )
        return content


def create_narrative_provider(settings: ReferenceNarrativeSettings) -> NarrativeProvider:
    if settings.provider == "disabled":
        return DisabledNarrativeProvider()
    if settings.provider == "ollama":
        if not settings.model:
            return UnavailableOllamaProvider(
                "",
                "REFERENCE_NARRATIVE_MODEL is required when the provider is ollama",
                missing_model=True,
            )
        try:
            return OllamaNarrativeClient(
                settings.ollama_url,
                settings.model,
                settings.connect_timeout_seconds,
                settings.generation_timeout_seconds,
            )
        except ValueError as exc:
            return UnavailableOllamaProvider(
                settings.model,
                str(exc),
                missing_model=False,
            )
    raise ValueError(f"Unsupported reference narrative provider: {settings.provider}")
