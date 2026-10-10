"""
Gemini engine adapter. Wraps the google-genai client behind the same
generate(prompt) -> str interface that ollama.py exposes, so the router
and everything above it never needs to know which engine is in play.
"""
from __future__ import annotations

from google import genai
from google.genai import types as genai_types

from app import config


class GeminiTimeoutError(Exception):
    pass


class GeminiRateLimitError(Exception):
    pass


class GeminiUnavailableError(Exception):
    pass


class GeminiEngine:
    name = "gemini"

    def __init__(self) -> None:
        if not config.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is not set in .env")
        self._client = genai.Client(api_key=config.GEMINI_API_KEY)
        self._model = config.GEMINI_MODEL

    def generate(self, prompt: str, *, timeout_s: float = 15.0) -> str:
        """
        Raises one of the typed errors above on failure so the router
        can decide, by error type, whether to retry-same-engine or
        fall back -- see FIX #1 in app/ai/router.py.
        """
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    temperature=0.1,  # low temperature: we want consistent extraction, not creativity
                    response_mime_type="application/json",
                ),
            )
        except Exception as exc:  # google-genai raises various exception types
            msg = str(exc).lower()
            if "429" in msg or "quota" in msg or "rate" in msg:
                raise GeminiRateLimitError(str(exc)) from exc
            if "timeout" in msg or "deadline" in msg:
                raise GeminiTimeoutError(str(exc)) from exc
            raise GeminiUnavailableError(str(exc)) from exc

        if not response or not response.text:
            raise GeminiUnavailableError("Empty response from Gemini")

        return response.text
