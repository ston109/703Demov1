from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any


REASONING_SCHEMA = {
    "type": "object",
    "properties": {
        "situation_summary": {"type": "string"},
        "main_hypothesis": {"type": "string"},
        "alternative_hypotheses": {"type": "array", "items": {"type": "string"}},
        "evidence_for": {"type": "array", "items": {"type": "string"}},
        "evidence_against": {"type": "array", "items": {"type": "string"}},
        "uncertainty": {"type": "number"},
        "recommended_planning_direction": {"type": "string"},
        "llm_confidence": {"type": "number"},
    },
    "required": [
        "situation_summary",
        "main_hypothesis",
        "alternative_hypotheses",
        "evidence_for",
        "evidence_against",
        "uncertainty",
        "recommended_planning_direction",
        "llm_confidence",
    ],
}


@dataclass
class LLMResult:
    provider: str
    model: str
    status: str
    content: dict[str, Any] | None
    latency_ms: int
    error: str | None = None


class BaseLLMClient:
    provider = "base"
    model = "none"

    def generate_json(self, prompt: str, schema: dict[str, Any]) -> LLMResult:
        raise NotImplementedError


class NullLLMClient(BaseLLMClient):
    provider = "none"
    model = "none"

    def generate_json(self, prompt: str, schema: dict[str, Any]) -> LLMResult:
        return LLMResult(
            provider=self.provider,
            model=self.model,
            status="disabled_or_missing_key",
            content=None,
            latency_ms=0,
        )


class GeminiLLMClient(BaseLLMClient):
    """Server-side Gemini adapter.

    The current demo wires Gemini only through risk_llm_scorer.py. AGI planning
    uses deterministic world-model, belief, planner, tool, and safety modules.
    """

    provider = "gemini"

    def __init__(self) -> None:
        self.api_key = os.getenv("GEMINI_API_KEY", "").strip()
        self.model = os.getenv("AGI_GEMINI_MODEL", "gemini-3.5-flash").strip()
        self.timeout_seconds = float(os.getenv("AGI_LLM_TIMEOUT_SECONDS", "8") or 8)
        self.max_output_tokens = int(os.getenv("AGI_LLM_MAX_OUTPUT_TOKENS", "10") or 10)

    def generate_json(self, prompt: str, schema: dict[str, Any]) -> LLMResult:
        started = time.perf_counter()
        if not self.api_key:
            return LLMResult(
                provider=self.provider,
                model=self.model,
                status="disabled_or_missing_key",
                content=None,
                latency_ms=0,
            )

        try:
            from google import genai
            from google.genai import types
        except Exception as exc:  # pragma: no cover - depends on optional package
            return self._error(started, "sdk_unavailable", exc)

        try:
            client = genai.Client(api_key=self.api_key)
            response = client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=schema,
                    temperature=0.2,
                    max_output_tokens=self.max_output_tokens,
                ),
            )
            text = getattr(response, "text", "") or ""
            content = json.loads(text)
            return LLMResult(
                provider=self.provider,
                model=self.model,
                status="ok",
                content=content,
                latency_ms=self._latency(started),
            )
        except Exception as exc:  # pragma: no cover - network/API dependent
            return self._error(started, "error", exc)

    def _error(self, started: float, status: str, exc: Exception) -> LLMResult:
        return LLMResult(
            provider=self.provider,
            model=self.model,
            status=status,
            content=None,
            latency_ms=self._latency(started),
            error=str(exc),
        )

    @staticmethod
    def _latency(started: float) -> int:
        return int((time.perf_counter() - started) * 1000)


def create_llm_client() -> BaseLLMClient:
    provider = os.getenv("AGI_LLM_PROVIDER", "gemini").strip().lower()
    if provider == "gemini":
        return GeminiLLMClient()
    return NullLLMClient()
