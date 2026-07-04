from __future__ import annotations

from typing import Any


class ToolRegistry:
    def get_available_tools(self, world_state: dict[str, Any]) -> list[str]:
        return list(world_state.get("available_agent_actions") or self.get_tool_schema().keys())

    def get_tool_schema(self) -> dict[str, dict[str, Any]]:
        return {
            "show_shipping_info": {"type": "banner", "supported_claim": "Shipping is free for orders over $150."},
            "show_return_policy": {"type": "banner", "supported_claim": "Demo returns are supported for course simulation."},
            "show_product_reviews": {"type": "banner", "supported_claim": "Product ratings are shown from catalog data."},
            "show_product_comparison": {"type": "banner", "supported_claim": "Comparison uses catalog price/rating signals."},
            "show_coupon": {"type": "banner", "supported_claim": "Coupon help can mention the demo SAVE10 coupon only."},
            "offer_small_discount": {"type": "cart_incentive", "supported_claim": "Demo cart incentive is capped at 5% off."},
            "highlight_support": {"type": "support", "supported_claim": "On-site support panel only; no external messages."},
            "show_related_recommendations": {"type": "recommendation", "supported_claim": "Recommendations use catalog similar/cheaper product data."},
            "show_trust_message": {"type": "banner", "supported_claim": "Checkout is a simulation and no real payment is charged."},
            "do_nothing": {"type": "none", "supported_claim": "No intervention."},
        }

    def execute(self, tool_name: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        builders = {
            "show_shipping_info": self._shipping,
            "show_return_policy": self._returns,
            "show_product_reviews": self._reviews,
            "show_product_comparison": self._comparison,
            "show_coupon": self._coupon,
            "offer_small_discount": self._small_discount,
            "highlight_support": self._support,
            "show_related_recommendations": self._recommendations,
            "show_trust_message": self._trust,
            "do_nothing": self._nothing,
        }
        return builders.get(tool_name, self._nothing)(payload)

    def _shipping(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "action_type": "banner",
            "tool_name": "show_shipping_info",
            "message": "Shipping is free for orders over $150. Your cart summary shows the current shipping cost before checkout.",
            "target_page": payload.get("target_page", "cart_or_checkout"),
            "priority": "medium",
        }

    def _returns(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "action_type": "banner",
            "tool_name": "show_return_policy",
            "message": "You can review the demo return policy before deciding, so you do not need to rush the purchase.",
            "target_page": payload.get("target_page", "product_detail"),
            "priority": "low",
        }

    def _reviews(self, payload: dict[str, Any]) -> dict[str, Any]:
        rating = payload.get("rating")
        message = "Check the product rating and feature list before you continue."
        if rating:
            message = f"This product is rated {rating}/5 in the demo catalog. Review the features before checkout."
        return {
            "action_type": "banner",
            "tool_name": "show_product_reviews",
            "message": message,
            "target_page": payload.get("target_page", "product_detail"),
            "priority": "medium",
        }

    def _comparison(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "action_type": "banner",
            "tool_name": "show_product_comparison",
            "message": "Compare similar products by price, rating, and features before returning to checkout.",
            "target_page": payload.get("target_page", "product_detail"),
            "priority": "medium",
        }

    def _coupon(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "action_type": "banner",
            "tool_name": "show_coupon",
            "message": "For this demo, you can try coupon SAVE10 in the cart. Final prices remain controlled by the checkout system.",
            "target_page": payload.get("target_page", "cart"),
            "priority": "low",
        }

    def _small_discount(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "action_type": "cart_incentive",
            "tool_name": "offer_small_discount",
            "message": "A 5% demo cart incentive is available if it helps you continue checkout.",
            "target_page": payload.get("target_page", "cart"),
            "priority": "medium",
            "discountMultiplier": 0.95,
            "demoIncentive": True,
        }

    def _support(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "action_type": "support_highlight",
            "tool_name": "highlight_support",
            "message": "Need help? The on-site support panel can answer shipping, checkout, and return questions.",
            "target_page": payload.get("target_page", "cart_or_checkout"),
            "priority": "high",
            "externalContact": False,
        }

    def _recommendations(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "action_type": "recommendation_strip",
            "tool_name": "show_related_recommendations",
            "message": "Compare related catalog products without leaving your current flow.",
            "target_page": payload.get("target_page", "product_detail"),
            "priority": "medium",
            "source": "catalog_similar_or_cheaper",
        }

    def _trust(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "action_type": "banner",
            "tool_name": "show_trust_message",
            "message": "This is a simulated checkout for the course demo; no real payment is processed.",
            "target_page": payload.get("target_page", "checkout"),
            "priority": "low",
        }

    def _nothing(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "action_type": "none",
            "tool_name": "do_nothing",
            "message": "",
            "target_page": payload.get("target_page", "any"),
            "priority": "none",
        }
