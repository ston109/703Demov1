from __future__ import annotations

from typing import Any


class Planner:
    TOOL_BY_DIRECTION = {
        "reduce_shipping_uncertainty": ("shipping_concern", "show_shipping_info"),
        "reduce_price_uncertainty": ("price_concern", "offer_small_discount"),
        "increase_product_confidence": ("product_uncertainty", "show_product_reviews"),
        "support_product_comparison": ("comparison_hesitation", "show_related_recommendations"),
        "reduce_checkout_friction": ("checkout_friction", "highlight_support"),
        "increase_checkout_trust": ("trust_concern", "highlight_support"),
    }

    def generate_candidate_plans(
        self,
        reasoning_result: dict[str, Any],
        belief_state: dict[str, Any],
        tools: list[str],
    ) -> list[dict[str, Any]]:
        blockers = belief_state.get("blocker_belief") or {}
        candidates: list[dict[str, Any]] = []
        direction = reasoning_result.get("recommended_planning_direction")
        if direction in self.TOOL_BY_DIRECTION:
            blocker, tool = self.TOOL_BY_DIRECTION[direction]
            candidates.append(self._plan(blocker, tool, blockers.get(blocker, 0.2)))

        mapping = {
            "shipping_concern": "show_shipping_info",
            "price_concern": "offer_small_discount",
            "trust_concern": "show_trust_message",
            "product_uncertainty": "show_product_reviews",
            "checkout_friction": "highlight_support",
            "comparison_hesitation": "show_related_recommendations",
        }
        for blocker, probability in sorted(blockers.items(), key=lambda item: item[1], reverse=True):
            tool = mapping.get(blocker, "do_nothing")
            if tool in tools:
                candidates.append(self._plan(blocker, tool, probability))

        candidates.append(self._plan("none", "do_nothing", 0.3))
        deduped = {}
        for plan in candidates:
            if plan["tool_required"] in tools:
                deduped.setdefault((plan["target_blocker"], plan["tool_required"]), plan)
        return list(deduped.values())

    def score_plan(
        self,
        plan: dict[str, Any],
        goals: list[str],
        memory_matches: list[dict[str, Any]],
    ) -> dict[str, Any]:
        reward_hint = 0.0
        for match in memory_matches or []:
            content = match.get("content") or {}
            if plan["tool_required"] in str(content):
                reward_hint += float(match.get("reward") or 0) * 0.03
        plan["score"] = round(
            max(
                0,
                min(
                    1,
                    plan["estimated_success"]
                    - plan["annoyance_risk"] * 0.35
                    - plan["safety_risk"] * 0.5
                    + reward_hint,
                ),
            ),
            2,
        )
        plan["confidence"] = plan["score"]
        return plan

    def select_best_plan(self, candidate_plans: list[dict[str, Any]]) -> dict[str, Any]:
        if not candidate_plans:
            return self.create_safe_fallback_plan({"reason": "no_candidates"})
        return max(candidate_plans, key=lambda plan: plan.get("score", plan.get("estimated_success", 0)))

    def create_safe_fallback_plan(self, safety_result: dict[str, Any]) -> dict[str, Any]:
        return {
            "plan_id": "safe_fallback",
            "target_blocker": "none",
            "steps": ["do_nothing", "observe_next_user_action"],
            "tool_required": "do_nothing",
            "expected_effect": "avoid unsafe or unsupported intervention",
            "estimated_success": 0.2,
            "annoyance_risk": 0.0,
            "safety_risk": 0.0,
            "score": 0.2,
            "confidence": 0.2,
            "fallback_reason": safety_result.get("reason"),
        }

    def _plan(self, blocker: str, tool: str, probability: float) -> dict[str, Any]:
        effect = {
            "show_shipping_info": "reduce uncertainty about shipping cost",
            "show_coupon": "help user understand available demo coupon path without changing prices",
            "offer_small_discount": "offer a capped demo cart incentive without changing catalog prices",
            "show_product_reviews": "increase product confidence using catalog rating/features",
            "show_product_comparison": "support comparison using catalog product data",
            "show_related_recommendations": "surface related catalog recommendations without blocking checkout",
            "highlight_support": "make on-site support easier to find without external contact",
            "show_trust_message": "reduce checkout trust friction",
            "do_nothing": "avoid unnecessary interruption",
        }.get(tool, "observe")
        return {
            "plan_id": f"{blocker}:{tool}",
            "target_blocker": blocker,
            "steps": [f"prepare_{tool}", tool, "observe_next_user_action"],
            "tool_required": tool,
            "expected_effect": effect,
            "estimated_success": round(min(0.85, 0.25 + float(probability) * 0.65), 2),
            "annoyance_risk": 0.05 if tool == "do_nothing" else round(0.12 + float(probability) * 0.12, 2),
            "safety_risk": 0.0 if tool in {"do_nothing", "show_shipping_info", "show_product_reviews"} else 0.03,
        }
