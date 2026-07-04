from __future__ import annotations

from typing import Any


class GoalManager:
    def get_active_goals(self) -> list[str]:
        return [
            "help_user_make_confident_purchase",
            "reduce_cart_abandonment",
            "avoid_user_annoyance",
            "preserve_privacy",
            "follow_action_constraints",
            "learn_from_feedback",
        ]

    def score_goal_alignment(self, candidate_action: dict[str, Any], belief_state: dict[str, Any]) -> float:
        tool = candidate_action.get("tool_required") or candidate_action.get("tool_name")
        risk = float(belief_state.get("abandonment_risk") or 0)
        blockers = belief_state.get("blocker_belief") or {}
        score = 0.3
        if tool == "do_nothing":
            return 0.25 if risk > 0.45 else 0.7
        if risk > 0.45:
            score += 0.25
        if tool == "show_shipping_info" and blockers.get("shipping_concern", 0) > 0.25:
            score += 0.25
        if tool == "show_product_reviews" and blockers.get("product_uncertainty", 0) > 0.25:
            score += 0.22
        if tool == "show_product_comparison" and blockers.get("comparison_hesitation", 0) > 0.25:
            score += 0.2
        if tool == "show_coupon" and blockers.get("price_concern", 0) > 0.35:
            score += 0.14
        if tool == "show_trust_message" and blockers.get("trust_concern", 0) > 0.2:
            score += 0.16
        return round(min(score, 1.0), 2)
