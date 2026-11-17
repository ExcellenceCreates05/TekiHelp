"""
Tests FIX #1: failure taxonomy and session stickiness, using fakes in
place of real network calls to Gemini/Ollama.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from app.ai.gemini import GeminiRateLimitError, GeminiUnavailableError
from app.ai.router import BothEnginesFailedError, InferenceRouter
from app.ai.ollama_engine import OllamaUnavailableError
from app.ai.gemini import GeminiEngine, GeminiTimeoutError
from app.ai.ollama_engine import OllamaEngine


@pytest.fixture
def router_with_fakes():
    router = InferenceRouter.__new__(InferenceRouter)  # bypass __init__ (no real clients)
    router._gemini = MagicMock()
    router._ollama = MagicMock()
    router._sticky_fallback = {}
    return router


def test_gemini_success_no_fallback(router_with_fakes):
    router_with_fakes._gemini.generate.return_value = json.dumps({"title": "X"})
    result = router_with_fakes.generate_structured("s1", "prompt")
    assert result.engine_used == "gemini"
    assert result.fell_back is False
    router_with_fakes._ollama.generate.assert_not_called()


def test_gemini_rate_limit_triggers_fallback(router_with_fakes):
    router_with_fakes._gemini.generate.side_effect = GeminiRateLimitError("429")
    router_with_fakes._ollama.generate.return_value = json.dumps({"title": "Y"})
    result = router_with_fakes.generate_structured("s2", "prompt")
    assert result.engine_used == "ollama"
    assert result.fell_back is True


def test_sticky_fallback_persists_within_session(router_with_fakes):
    """Once a session falls back, subsequent calls in the SAME session go
    straight to Ollama without retrying Gemini."""
    router_with_fakes._gemini.generate.side_effect = GeminiUnavailableError("down")
    router_with_fakes._ollama.generate.return_value = json.dumps({"title": "Z"})

    router_with_fakes.generate_structured("s3", "prompt one")
    assert router_with_fakes._gemini.generate.call_count == 1

    router_with_fakes.generate_structured("s3", "prompt two")
    # Gemini should NOT have been called a second time for the same session.
    assert router_with_fakes._gemini.generate.call_count == 1
    assert router_with_fakes._ollama.generate.call_count == 2


def test_new_session_starts_fresh_on_gemini(router_with_fakes):
    """A DIFFERENT session_key must try Gemini first even if another
    session already fell back."""
    router_with_fakes._gemini.generate.side_effect = [
        GeminiUnavailableError("down"),  # session A fails
        json.dumps({"title": "fresh"}),  # session B succeeds
    ]
    router_with_fakes._ollama.generate.return_value = json.dumps({"title": "fallback"})

    result_a = router_with_fakes.generate_structured("sessionA", "prompt")
    assert result_a.engine_used == "ollama"

    result_b = router_with_fakes.generate_structured("sessionB", "prompt")
    assert result_b.engine_used == "gemini"


def test_malformed_json_retries_same_engine_before_fallback(router_with_fakes):
    router_with_fakes._gemini.generate.side_effect = ["not json", json.dumps({"title": "ok"})]
    result = router_with_fakes.generate_structured("s4", "prompt")
    assert result.engine_used == "gemini"
    assert router_with_fakes._gemini.generate.call_count == 2
    router_with_fakes._ollama.generate.assert_not_called()


def test_both_engines_fail_raises(router_with_fakes):
    router_with_fakes._gemini.generate.side_effect = GeminiUnavailableError("down")
    router_with_fakes._ollama.generate.side_effect = OllamaUnavailableError("down too")
    with pytest.raises(BothEnginesFailedError):
        router_with_fakes.generate_structured("s5", "prompt")


def test_gemini_config_passes_real_http_timeout(monkeypatch):
    engine = GeminiEngine.__new__(GeminiEngine)
    engine._model = "test-model"
    engine._client = MagicMock()
    engine._client.models.generate_content.return_value.text = '{"title":"X"}'

    engine.generate("prompt", timeout_s=7.5)

    call = engine._client.models.generate_content.call_args
    config = call.kwargs["config"]
    assert config.http_options.timeout == 7500


@pytest.mark.parametrize("message", ["503", "502 Server Error", "504", "request timed out"])
def test_gemini_service_status_maps_to_timeout(message):
    engine = GeminiEngine.__new__(GeminiEngine)
    engine._model = "test-model"
    engine._client = MagicMock()
    engine._client.models.generate_content.side_effect = RuntimeError(message)

    with pytest.raises(GeminiTimeoutError):
        engine.generate("prompt")


def test_ollama_generate_disables_thinking_and_uses_json():
    engine = OllamaEngine.__new__(OllamaEngine)
    engine._model = "qwen3:4b"
    engine._client = MagicMock()
    engine._client.generate.return_value = {"response": '{"title":"X"}'}

    result = engine.generate("prompt")

    assert result == '{"title":"X"}'
    call = engine._client.generate.call_args
    assert call.kwargs["think"] is False
    assert call.kwargs["format"] == "json"
