"""
Qwen3-via-Ollama engine adapter. Same generate(prompt) -> str interface
as gemini.py. This is the local fallback engine -- see Chapter 3's
migration justification for why Qwen3 specifically.
"""
from __future__ import annotations

import ollama

from app import config


class OllamaUnavailableError(Exception):
    pass


class OllamaEngine:
    name = "ollama"

    def __init__(self) -> None:
        self._client = ollama.Client(host=config.OLLAMA_HOST)
        self._model = config.OLLAMA_MODEL

    def generate(self, prompt: str, *, timeout_s: float = 30.0) -> str:
        """
        Local inference is slower than Gemini (hence the longer default
        timeout) but has no rate limit and no network dependency. Any
        failure here (Ollama not running, model not pulled, etc.) is
        collapsed into OllamaUnavailableError -- if BOTH engines fail,
        the router surfaces this to the user rather than silently
        hanging, per Constitution Rule 2 (no inventing content).
        """
        try:
            response = self._client.generate(
                model=self._model,
                prompt=prompt,
                format="json",
                options={"temperature": 0.1},
            )
        except Exception as exc:
            raise OllamaUnavailableError(str(exc)) from exc

        text = response.get("response", "") if isinstance(response, dict) else getattr(response, "response", "")
        if not text:
            raise OllamaUnavailableError("Empty response from Ollama")
        return text
