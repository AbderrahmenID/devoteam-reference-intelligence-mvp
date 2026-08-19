from __future__ import annotations

from typing import Any

import httpx
import pytest

from reference_narrative.ollama_client import (
    NarrativeModelUnavailableError,
    NarrativeProviderTimeoutError,
    OllamaNarrativeClient,
    create_narrative_provider,
)
from reference_narrative.settings import ReferenceNarrativeSettings


class FakeResponse:
    def __init__(self, status_code: int, body: dict[str, Any]):
        self.status_code = status_code
        self.body = body

    def json(self) -> dict[str, Any]:
        return self.body


def test_ollama_client_sends_bounded_non_thinking_structured_request(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_post(url: str, **kwargs: Any) -> FakeResponse:
        captured.update({"url": url, **kwargs})
        return FakeResponse(200, {"message": {"content": '{"ok":true}'}})

    monkeypatch.setattr(
        httpx,
        "get",
        lambda *args, **kwargs: FakeResponse(200, {"models": [{"name": "local-test-model"}]}),
    )
    monkeypatch.setattr(httpx, "post", fake_post)
    client = OllamaNarrativeClient("http://localhost:11434", "local-test-model", 12)
    result = client.generate([{"role": "user", "content": "test"}], {"type": "object"})
    assert result == '{"ok":true}'
    assert captured["url"] == "http://localhost:11434/api/chat"
    assert captured["json"]["stream"] is False
    assert captured["json"]["think"] is False
    assert captured["json"]["keep_alive"] == "10m"
    assert captured["json"]["options"]["temperature"] == 0
    assert captured["json"]["options"]["num_ctx"] == 8192
    assert captured["json"]["options"]["num_predict"] == 768
    assert captured["json"]["format"] == {"type": "object"}
    assert captured["timeout"].connect == 10
    assert captured["timeout"].read == 300


def test_ollama_client_warms_cold_model_once_and_keeps_it_loaded(monkeypatch) -> None:
    posts: list[dict[str, Any]] = []
    gets = 0

    def fake_get(*args: Any, **kwargs: Any) -> FakeResponse:
        nonlocal gets
        gets += 1
        return FakeResponse(200, {"models": []})

    def fake_post(url: str, **kwargs: Any) -> FakeResponse:
        posts.append({"url": url, **kwargs})
        if url.endswith("/api/generate"):
            return FakeResponse(200, {})
        return FakeResponse(200, {"message": {"content": '{"ok":true}'}})

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(httpx, "post", fake_post)
    client = OllamaNarrativeClient("http://127.0.0.1:11434", "local-test-model", 180)
    assert client.generate([], {"type": "object"}) == '{"ok":true}'
    assert client.generate([], {"type": "object"}) == '{"ok":true}'
    assert gets == 1
    assert [item["url"].rsplit("/", 1)[-1] for item in posts] == ["generate", "chat", "chat"]
    assert posts[0]["json"] == {
        "model": "local-test-model",
        "prompt": "",
        "stream": False,
        "keep_alive": "10m",
    }
    assert all(item["timeout"].connect == 10 for item in posts)
    assert all(item["timeout"].read == 300 for item in posts)


def test_ollama_client_reports_missing_model(monkeypatch) -> None:
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *args, **kwargs: FakeResponse(200, {"models": [{"name": "missing"}]}),
    )
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: FakeResponse(404, {"error": "not found"}))
    client = OllamaNarrativeClient("http://127.0.0.1:11434", "missing", 10)
    with pytest.raises(NarrativeModelUnavailableError):
        client.generate([], {"type": "object"})


def test_ollama_client_reports_timeout_without_retrying_transport(monkeypatch) -> None:
    calls = 0

    def timeout(*args: Any, **kwargs: Any) -> FakeResponse:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("timeout")

    monkeypatch.setattr(
        httpx,
        "get",
        lambda *args, **kwargs: FakeResponse(200, {"models": [{"name": "model"}]}),
    )
    monkeypatch.setattr(httpx, "post", timeout)
    client = OllamaNarrativeClient("http://[::1]:11434", "model", 10)
    with pytest.raises(NarrativeProviderTimeoutError):
        client.generate([], {"type": "object"})
    assert calls == 1


def test_ollama_client_rejects_non_loopback_url() -> None:
    with pytest.raises(ValueError, match="loopback"):
        OllamaNarrativeClient("https://example.test", "model", 10)


def test_missing_model_configuration_is_a_graceful_provider_error() -> None:
    provider = create_narrative_provider(
        ReferenceNarrativeSettings(provider="ollama", model="")
    )
    with pytest.raises(NarrativeModelUnavailableError, match="REFERENCE_NARRATIVE_MODEL"):
        provider.generate([], {"type": "object"})


def test_narrative_uses_bounded_timeout_defaults_and_environment_overrides(monkeypatch) -> None:
    monkeypatch.delenv("REFERENCE_NARRATIVE_CONNECT_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("REFERENCE_NARRATIVE_GENERATION_TIMEOUT_SECONDS", raising=False)
    assert ReferenceNarrativeSettings().connect_timeout_seconds == 10
    assert ReferenceNarrativeSettings().generation_timeout_seconds == 300
    monkeypatch.setenv("REFERENCE_NARRATIVE_CONNECT_TIMEOUT_SECONDS", "7")
    monkeypatch.setenv("REFERENCE_NARRATIVE_GENERATION_TIMEOUT_SECONDS", "240")
    assert ReferenceNarrativeSettings().connect_timeout_seconds == 7
    assert ReferenceNarrativeSettings().generation_timeout_seconds == 240


def test_provider_uses_configured_backend_timeout() -> None:
    provider = create_narrative_provider(
        ReferenceNarrativeSettings(
            provider="ollama",
            model="local-test-model",
            connect_timeout_seconds=10,
        )
    )
    assert isinstance(provider, OllamaNarrativeClient)
    assert provider.timeout.connect == 10
    assert provider.timeout.read == 300
