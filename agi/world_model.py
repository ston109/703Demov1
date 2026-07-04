from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(value: str | None, fallback: Any = None) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


class WorldModel:
    def __init__(self, db: str | Path):
        self.db = str(db)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db)
        conn.row_factory = sqlite3.Row
        return conn

    def update_from_event(self, event: dict[str, Any]) -> None:
        session_id = ((event.get("user") or {}).get("sessionId")) or event.get("session_id")
        if not session_id:
            return
        self.build_world_state(session_id)

    def get_recent_trajectory(self, session_id: str, limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM events
                WHERE session_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        trajectory = []
        for row in reversed(rows):
            raw = load_json(row["raw_payload_json"], {})
            trajectory.append(
                {
                    "event_type": row["event_type"],
                    "page_type": row["page_type"],
                    "url": row["url"],
                    "timestamp": row["timestamp"],
                    "product": load_json(row["product_json"], None),
                    "cart": load_json(row["cart_json"], None),
                    "raw_payload": raw,
                }
            )
        return trajectory

    def infer_stage(self, trajectory: list[dict[str, Any]]) -> str:
        if not trajectory:
            return "unknown"
        latest = trajectory[-1]
        event_type = latest.get("event_type")
        page_type = latest.get("page_type")
        if event_type == "order_complete":
            return "converted"
        if page_type == "checkout" or event_type in {"checkout_start", "checkout_exit"}:
            return "checkout"
        if page_type == "cart" or event_type in {"add_to_cart", "cart_view", "remove_from_cart"}:
            return "cart"
        if page_type == "product_detail" or event_type in {"product_view", "similar_product_view"}:
            return "product_consideration"
        return "browsing"

    def infer_intent(self, trajectory: list[dict[str, Any]]) -> str:
        events = [item["event_type"] for item in trajectory]
        if "order_complete" in events:
            return "converted"
        if "checkout_start" in events and events[-1] != "checkout_exit":
            return "ready_to_buy"
        if "add_to_cart" in events:
            return "high_purchase_intent_but_uncertain"
        if any(evt in events for evt in ("similar_product_view", "cheaper_alternative_view", "coupon_attempt")):
            return "comparing"
        return "exploring"

    def infer_blockers(
        self,
        trajectory: list[dict[str, Any]],
        risk_signal: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        weights = self._load_world_weights()
        scores = {
            "shipping_concern": 0.05,
            "price_concern": 0.05,
            "trust_concern": 0.04,
            "product_uncertainty": 0.08,
            "checkout_friction": 0.04,
            "comparison_hesitation": 0.04,
        }
        evidence: dict[str, list[str]] = {key: [] for key in scores}

        for item in trajectory:
            event = item.get("event_type", "")
            page = item.get("page_type", "")
            cart = item.get("cart") or {}
            shipping = float(cart.get("shippingFee") or cart.get("shipping") or 0)
            signal_names = [event, page]
            if shipping > 0 and page in {"cart", "checkout"}:
                signal_names.append("shipping_fee_visible")
            if event == "coupon_attempt":
                signal_names.append("coupon_attempt")
            if event in {"similar_product_view", "cheaper_alternative_view"}:
                signal_names.append("comparison")
            if event == "checkout_exit":
                signal_names.append("checkout_exit")
            if event in {"product_view", "dwell_update", "page_exit"} and page == "product_detail":
                signal_names.append("product_uncertainty_signal")

            for signal in signal_names:
                for blocker, weight in weights.get(signal, {}).items():
                    scores[blocker] = scores.get(blocker, 0) + weight
                    evidence.setdefault(blocker, []).append(signal)

        risk_score = int((risk_signal or {}).get("score", 100))
        risk_boost = clamp((55 - risk_score) / 100)
        for blocker in scores:
            scores[blocker] += risk_boost * 0.25

        blockers = []
        for blocker, score in scores.items():
            probability = round(clamp(score), 2)
            if probability >= 0.15:
                blockers.append(
                    {
                        "type": blocker,
                        "probability": probability,
                        "evidence": sorted(set(evidence.get(blocker) or [])),
                    }
                )
        blockers.sort(key=lambda item: item["probability"], reverse=True)
        return blockers

    def predict_next_action(
        self,
        trajectory: list[dict[str, Any]],
        belief_state: dict[str, Any] | None,
    ) -> dict[str, Any]:
        stage = self.infer_stage(trajectory)
        risk = float((belief_state or {}).get("abandonment_risk") or 0)
        if stage == "checkout" and risk > 0.55:
            return {"action": "leave_checkout", "probability": round(clamp(risk), 2)}
        if stage == "cart" and risk > 0.5:
            return {"action": "delay_or_leave_cart", "probability": round(clamp(risk), 2)}
        if stage in {"cart", "checkout"}:
            return {"action": "continue_checkout", "probability": round(1 - risk * 0.5, 2)}
        return {"action": "continue_browsing", "probability": 0.55}

    def build_world_state(
        self,
        session_id: str,
        risk_signal: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        trajectory = self.get_recent_trajectory(session_id)
        latest = trajectory[-1] if trajectory else {}
        latest_cart = next((item.get("cart") for item in reversed(trajectory) if item.get("cart")), None) or {}
        cart_items = []
        cart_product_ids = []
        raw_items = latest_cart.get("items") if isinstance(latest_cart, dict) else None
        if isinstance(raw_items, list):
            cart_items = [((item.get("product") or {}).get("id")) for item in raw_items if item.get("product")]
            cart_product_ids = [item for item in cart_items if item]
        elif latest_cart.get("cartProductIds"):
            cart_product_ids = list(latest_cart.get("cartProductIds") or [])
            cart_items = cart_product_ids
        elif latest_cart.get("itemCount"):
            cart_items = [f"{latest_cart.get('itemCount')} item(s)"]

        stage = self.infer_stage(trajectory)
        intent = self.infer_intent(trajectory)
        blockers = self.infer_blockers(trajectory, risk_signal)
        uncertainty = round(clamp(0.55 - (blockers[0]["probability"] if blockers else 0.2) * 0.35), 2)
        belief_stub = {"abandonment_risk": clamp((100 - int((risk_signal or {}).get("score", 100))) / 100)}
        state = {
            "session_id": session_id,
            "environment": "online_shopping_web",
            "current_page": latest.get("url") or latest.get("page_type") or "unknown",
            "current_stage": stage,
            "current_product": (latest.get("product") or {}).get("productId"),
            "cart_items": [item for item in cart_items if item],
            "cart_product_ids": cart_product_ids,
            "current_product_in_cart": ((latest.get("product") or {}).get("productId") in cart_product_ids)
            if cart_product_ids
            else False,
            "recent_events": [item["event_type"] for item in trajectory[-10:]],
            "inferred_user_intent": intent,
            "possible_blockers": blockers,
            "predicted_next_action": self.predict_next_action(trajectory, belief_stub),
            "environment_constraints": [
                "cannot_modify_real_price",
                "cannot_auto_purchase",
                "cannot_collect_sensitive_payment_data",
                "cannot_send_private_user_data_to_llm",
                "cannot_show_fake_discounts",
            ],
            "available_agent_actions": [
                "show_shipping_info",
                "show_return_policy",
                "show_product_reviews",
                "show_product_comparison",
                "show_coupon",
                "offer_small_discount",
                "highlight_support",
                "show_related_recommendations",
                "show_trust_message",
                "do_nothing",
            ],
            "risk_signal": risk_signal or {},
            "uncertainty": uncertainty,
            "updated_at": now_iso(),
        }
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO world_states (session_id, world_state_json, timestamp) VALUES (?, ?, ?)",
                (session_id, json.dumps(state, ensure_ascii=False), state["updated_at"]),
            )
        return state

    def serialize(self, world_state: dict[str, Any]) -> dict[str, Any]:
        return world_state

    def _load_world_weights(self) -> dict[str, dict[str, float]]:
        defaults = {
            "shipping_fee_visible": {"shipping_concern": 0.45},
            "checkout": {"shipping_concern": 0.12, "checkout_friction": 0.18},
            "cart": {"price_concern": 0.12},
            "coupon_attempt": {"price_concern": 0.45},
            "comparison": {"comparison_hesitation": 0.34, "product_uncertainty": 0.18, "price_concern": 0.16},
            "checkout_exit": {"checkout_friction": 0.45, "shipping_concern": 0.18},
            "product_uncertainty_signal": {"product_uncertainty": 0.16},
        }
        with self.connect() as conn:
            rows = conn.execute("SELECT signal_name, blocker_type, weight FROM world_model_weights").fetchall()
        for row in rows:
            defaults.setdefault(row["signal_name"], {})[row["blocker_type"]] = float(row["weight"])
        return defaults
