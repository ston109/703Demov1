from __future__ import annotations

from typing import Any


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


class BeliefStateBuilder:
    def build(
        self,
        world_state: dict[str, Any],
        risk_signal: dict[str, Any] | None,
        memory_matches: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        stage = world_state.get("current_stage", "browsing")
        intent = world_state.get("inferred_user_intent", "exploring")
        risk_score = int((risk_signal or world_state.get("risk_signal") or {}).get("score", 100))
        abandonment_risk = clamp((100 - risk_score) / 100)

        stage_belief = {
            "browsing": 0.08,
            "product_consideration": 0.08,
            "cart": 0.08,
            "checkout": 0.08,
            "converted": 0.02,
        }
        stage_belief[stage] = stage_belief.get(stage, 0.08) + 0.7

        intent_belief = {
            "exploring": 0.08,
            "comparing": 0.12,
            "ready_to_buy": 0.12,
            "high_purchase_intent_but_uncertain": 0.12,
            "converted": 0.02,
        }
        intent_belief[intent] = intent_belief.get(intent, 0.08) + 0.65

        blocker_belief = {
            "shipping_concern": 0.05,
            "price_concern": 0.05,
            "trust_concern": 0.05,
            "product_uncertainty": 0.05,
            "checkout_friction": 0.05,
            "comparison_hesitation": 0.05,
        }
        for blocker in world_state.get("possible_blockers") or []:
            blocker_belief[blocker["type"]] = max(
                blocker_belief.get(blocker["type"], 0.05),
                float(blocker.get("probability") or 0),
            )

        for match in memory_matches or []:
            reward = float(match.get("reward") or 0)
            if reward > 0:
                abandonment_risk = clamp(abandonment_risk - 0.02)
            elif reward < 0:
                abandonment_risk = clamp(abandonment_risk + 0.02)

        belief = {
            "session_id": world_state.get("session_id"),
            "stage_belief": self.normalize_probabilities(stage_belief),
            "intent_belief": self.normalize_probabilities(intent_belief),
            "blocker_belief": {key: round(clamp(value), 2) for key, value in blocker_belief.items()},
            "abandonment_risk": round(abandonment_risk, 2),
        }
        belief["confidence"] = self.estimate_confidence(belief)
        return belief

    def normalize_probabilities(self, belief: dict[str, float]) -> dict[str, float]:
        total = sum(max(value, 0) for value in belief.values()) or 1
        return {key: round(max(value, 0) / total, 2) for key, value in belief.items()}

    def estimate_confidence(self, belief: dict[str, Any]) -> float:
        stage_peak = max((belief.get("stage_belief") or {}).values() or [0])
        intent_peak = max((belief.get("intent_belief") or {}).values() or [0])
        blocker_peak = max((belief.get("blocker_belief") or {}).values() or [0])
        risk = float(belief.get("abandonment_risk") or 0)
        return round(clamp((stage_peak + intent_peak + blocker_peak + (1 - abs(0.5 - risk))) / 4), 2)
