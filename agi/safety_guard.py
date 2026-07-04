from __future__ import annotations

import copy
import re
from typing import Any


SENSITIVE_KEYS = {
    "card",
    "card_number",
    "cardnumber",
    "payment",
    "expiry",
    "cvv",
    "address",
    "full_name",
    "fullname",
    "email",
    "phone",
    "password",
    "api_key",
}


class SafetyGuard:
    def get_constraints(self) -> list[str]:
        return [
            "cannot_auto_purchase",
            "cannot_modify_real_price",
            "cannot_collect_sensitive_payment_data",
            "cannot_send_private_user_data_to_llm",
            "cannot_show_fake_discounts",
            "avoid_repeated_popups",
            "claims_must_be_supported_by_catalog_or_policy",
        ]

    def check_plan(
        self,
        plan: dict[str, Any] | None,
        world_state: dict[str, Any],
        belief_state: dict[str, Any],
    ) -> dict[str, Any]:
        if not plan:
            return {"allowed": False, "status": "blocked", "reason": "missing_plan"}
        forbidden_text = " ".join(str(value).lower() for value in plan.values())
        forbidden_markers = [
            "auto_purchase",
            "modify_price",
            "real discount",
            "credit card",
            "collect_payment",
            "send_email",
            "send_sms",
            "external_contact",
        ]
        for marker in forbidden_markers:
            if marker in forbidden_text:
                return {"allowed": False, "status": "blocked", "reason": f"forbidden_marker:{marker}"}
        tool = plan.get("tool_required")
        if tool not in (world_state.get("available_agent_actions") or []):
            return {"allowed": False, "status": "blocked", "reason": "tool_not_available"}
        if plan.get("annoyance_risk", 0) > 0.75:
            return {"allowed": False, "status": "blocked", "reason": "annoyance_risk_too_high"}
        return {"allowed": True, "status": "approved", "reason": "constraints_satisfied"}

    def check_action_payload(self, action_payload: dict[str, Any]) -> dict[str, Any]:
        text = str(action_payload).lower()
        if action_payload.get("tool_name") == "offer_small_discount" or action_payload.get("action_type") == "cart_incentive":
            multiplier = float(action_payload.get("discountMultiplier") or action_payload.get("discount_multiplier") or 1)
            if multiplier < 0.95 or not action_payload.get("demoIncentive"):
                return {"allowed": False, "status": "blocked", "reason": "unsafe_discount"}
        if "fake" in text or "guaranteed discount" in text or "we changed the price" in text:
            return {"allowed": False, "status": "blocked", "reason": "unsupported_or_fake_claim"}
        if "auto_purchase" in text or "modify_price" in text or "externalcontact': true" in text:
            return {"allowed": False, "status": "blocked", "reason": "forbidden_action"}
        if "card" in text and "simulated checkout" not in text:
            return {"allowed": False, "status": "blocked", "reason": "payment_data_claim"}
        return {"allowed": True, "status": "approved", "reason": "payload_safe"}

    def redact_sensitive_data(self, data: Any) -> Any:
        redacted = copy.deepcopy(data)
        return self._redact_value(redacted)

    def should_require_human_approval(self, plan: dict[str, Any]) -> bool:
        return float(plan.get("safety_risk") or 0) > 0.35

    def _redact_value(self, value: Any) -> Any:
        if isinstance(value, dict):
            cleaned = {}
            for key, child in value.items():
                key_norm = re.sub(r"[^a-z0-9_]", "", str(key).lower())
                if any(sensitive in key_norm for sensitive in SENSITIVE_KEYS):
                    cleaned[key] = "[REDACTED]"
                else:
                    cleaned[key] = self._redact_value(child)
            return cleaned
        if isinstance(value, list):
            return [self._redact_value(item) for item in value]
        if isinstance(value, str):
            value = re.sub(r"\b(?:\d[ -]*?){12,19}\b", "[REDACTED_CARD]", value)
            value = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "[REDACTED_EMAIL]", value)
            return value
        return value
