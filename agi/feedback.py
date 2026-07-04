from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from memory_store import MemoryStore


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class FeedbackCollector:
    REWARDS = {
        "purchase_completed": 3,
        "order_complete": 3,
        "checkout_continued": 1,
        "cart_retained": 0.5,
        "ignored_action": -0.2,
        "popup_closed": -1,
        "site_exit": -2,
        "checkout_exit": -2,
        "safety_violation": -5,
        "action_shown": 0.1,
        "action_clicked": 1,
        "action_dismissed": -0.3,
        "action_expired": -0.2,
        "discount_applied": 1.2,
        "action_blocked_by_safety": -0.5,
        "action_render_failed": -0.8,
    }

    def __init__(self, db: str | Path | None = None):
        self.memory = MemoryStore(db) if db else None

    def calculate_reward(self, feedback_event: dict[str, Any]) -> float:
        event_type = feedback_event.get("feedback_type") or feedback_event.get("type") or feedback_event.get("event_type")
        return float(self.REWARDS.get(event_type, 0))

    def save_feedback(self, feedback_event: dict[str, Any]) -> dict[str, Any]:
        reward = self.calculate_reward(feedback_event)
        record = {
            "session_id": feedback_event.get("session_id") or feedback_event.get("sessionId"),
            "decision_id": feedback_event.get("decision_id") or feedback_event.get("decisionId"),
            "event": feedback_event,
            "reward": reward,
            "timestamp": now_iso(),
        }
        if self.memory:
            record["id"] = self.memory.save_feedback(record)
        return record
