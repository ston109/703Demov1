from __future__ import annotations

import json
from typing import Any

from llm_client import GeminiLLMClient


RISK_SCORE_SCHEMA = {
    "type": "object",
    "properties": {
        "risk_multiplier": {"type": "number"},
        "reason_code": {"type": "string"},
    },
    "required": ["risk_multiplier", "reason_code"],
}


class RiskLLMScorer:
    """Gemini-backed risk multiplier helper.

    This class is intentionally limited to score calibration. It does not
    choose AGI plans, tools, or final actions.
    """

    def __init__(self, client: GeminiLLMClient | None = None):
        self.client = client or GeminiLLMClient()

    def score_multiplier(self, context: dict[str, Any]) -> dict[str, Any]:
        prompt = self._build_prompt(context)
        result = self.client.generate_json(prompt, RISK_SCORE_SCHEMA)
        if result.status != "ok" or not result.content:
            return {"multiplier": 0.5, "source": "fallback_invalid", "reason_code": result.status}
        try:
            multiplier = float(result.content.get("risk_multiplier"))
            reason_code = str(result.content.get("reason_code") or "gemini")
        except (TypeError, ValueError):
            return {"multiplier": 0.5, "source": "fallback_invalid", "reason_code": "invalid_format"}
        if multiplier < 0.25 or multiplier > 1.0:
            return {"multiplier": 0.5, "source": "fallback_invalid", "reason_code": "out_of_range"}
        return {"multiplier": multiplier, "source": "gemini", "reason_code": reason_code}

    def _build_prompt(self, context: dict[str, Any]) -> str:
        table = {
            "current_score": context.get("current_score"),
            "event_type": context.get("event_type"),
            "page_type": context.get("page_type"),
            "cart_product_ids": context.get("cart_product_ids"),
            "product_in_cart": context.get("product_in_cart"),
            "duration_ms": context.get("duration_ms"),
            "shipping_fee": context.get("shipping_fee"),
            "recent_cart_events": context.get("recent_cart_events"),
            "max_delta": context.get("max_delta"),
        }
        return (
            "You are only a risk scoring helper for a cart abandonment demo. "
            "Choose how much of the max negative risk delta should apply. "
            "Return JSON only with risk_multiplier between 0.25 and 1.0. "
            "Use 0.25 for weak evidence, 0.5 for normal evidence, 1.0 for very strong evidence. "
            "Do not recommend actions. Do not include prose.\n"
            f"SCORING_TABLE={json.dumps(table, ensure_ascii=False)}"
        )
