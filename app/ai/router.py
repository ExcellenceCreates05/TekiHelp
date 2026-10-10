"""
Inference Router -- FIX #1.

Implements the failure taxonomy agreed on before building this:

  - Timeout or rate-limit (429) on Gemini  -> fall back to Ollama immediately.
  - Malformed/invalid JSON response from either engine -> ONE retry on the
    SAME engine first (transient glitches happen); only fall back if that
    retry also fails.
  - Session stickiness: once a session has fallen back to Ollama, it stays
    on Ollama for the rest of THAT conversation. The next new session
    always starts back on Gemini. This avoids inconsistent extraction
    behaviour from bouncing between two models mid-conversation.

The router has no knowledge of Telegram, Discord, or the agent loop --
it only knows "give me a JSON string back for this prompt, and tell me
honestly which engine produced it."
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from app.ai.gemini import GeminiEngine, GeminiRateLimitError, GeminiTimeoutError, GeminiUnavailableError
from app.ai.ollama_engine import OllamaEngine, OllamaUnavailableError

logger = logging.getLogger("tekihelp.router")


class BothEnginesFailedError(Exception):
    """Raised when neither Gemini nor Ollama could produce a usable response."""


@dataclass
class InferenceResult:
    raw_text: str
    parsed: dict
    engine_used: str  # "gemini" | "ollama"
    fell_back: bool


class InferenceRouter:
    def __init__(self) -> None:
        self._gemini = GeminiEngine()
        self._ollama = OllamaEngine()
        # session_key -> True once that session has fallen back to Ollama
        self._sticky_fallback: dict[str, bool] = {}

    def _is_sticky(self, session_key: str) -> bool:
        return self._sticky_fallback.get(session_key, False)

    def _mark_sticky(self, session_key: str) -> None:
        self._sticky_fallback[session_key] = True

    def reset_stickiness(self, session_key: str) -> None:
        """Call this when a session ends/completes so its NEXT new
        conversation starts fresh on Gemini again."""
        self._sticky_fallback.pop(session_key, None)

    def _try_parse_json(self, text: str) -> dict | None:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    def generate_structured(self, session_key: str, prompt: str) -> InferenceResult:
        """
        Main entry point. Always returns an InferenceResult or raises
        BothEnginesFailedError -- callers never need to catch
        engine-specific exceptions themselves.
        """
        if self._is_sticky(session_key):
            return self._generate_on_ollama(prompt, fell_back=True)

        try:
            return self._generate_on_gemini(prompt, session_key)
        except (GeminiRateLimitError, GeminiTimeoutError, GeminiUnavailableError) as exc:
            logger.warning("Gemini failed for session %s (%s): %s -- falling back to Ollama", session_key, type(exc).__name__, str(exc))
            self._mark_sticky(session_key)
            return self._generate_on_ollama(prompt, fell_back=True)

    def _generate_on_gemini(self, prompt: str, session_key: str) -> InferenceResult:
        text = self._gemini.generate(prompt)
        parsed = self._try_parse_json(text)
        if parsed is None:
            # Malformed JSON: one retry on the SAME engine before giving up on it.
            logger.info("Gemini returned malformed JSON for session %s, retrying once", session_key)
            text = self._gemini.generate(prompt)
            parsed = self._try_parse_json(text)
            if parsed is None:
                raise GeminiUnavailableError("Gemini returned malformed JSON twice in a row")
        return InferenceResult(raw_text=text, parsed=parsed, engine_used="gemini", fell_back=False)

    def _generate_on_ollama(self, prompt: str, fell_back: bool) -> InferenceResult:
        try:
            text = self._ollama.generate(prompt)
            parsed = self._try_parse_json(text)
            if parsed is None:
                text = self._ollama.generate(prompt)
                parsed = self._try_parse_json(text)
                if parsed is None:
                    raise OllamaUnavailableError("Ollama returned malformed JSON twice in a row")
            return InferenceResult(raw_text=text, parsed=parsed, engine_used="ollama", fell_back=fell_back)
        except OllamaUnavailableError as exc:
            raise BothEnginesFailedError(
                "Both Gemini and Ollama failed to produce a usable response."
            ) from exc
