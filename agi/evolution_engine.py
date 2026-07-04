from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from memory_store import MemoryStore


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class EvolutionEngine:
    def __init__(self, db: str | Path):
        self.db = str(db)
        self.memory = MemoryStore(db)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db)
        conn.row_factory = sqlite3.Row
        return conn

    def evolve_from_feedback(self, feedback: dict[str, Any], decision: dict[str, Any] | None) -> dict[str, Any]:
        if not decision:
            return {}
        plan = decision.get("plan") or {}
        belief = decision.get("belief_state") or {}
        blocker = plan.get("target_blocker") or self._top_blocker(belief)
        tool = plan.get("tool_required") or decision.get("selected_tool")
        reward = float(feedback.get("reward") or 0)
        tool_update = self.update_tool_policy(blocker, tool, reward) if blocker and tool else {}
        weight_update = self.update_world_model_weights(belief, feedback)
        reflection = self.generate_reflection(decision, feedback)
        self.memory.save_reflection(reflection)
        update = {
            "session_id": feedback.get("session_id"),
            "tool_policy": tool_update,
            "world_model_weights": weight_update,
            "reflection": reflection,
        }
        self.save_strategy_update(update)
        return update

    def update_tool_policy(self, blocker_type: str, tool_name: str, reward: float) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM tool_policy WHERE blocker_type = ? AND tool_name = ?",
                (blocker_type, tool_name),
            ).fetchone()
            before = dict(row) if row else {"score": 0.5, "usage_count": 0, "average_reward": 0}
            usage = int(before.get("usage_count") or 0) + 1
            avg_reward = ((float(before.get("average_reward") or 0) * (usage - 1)) + reward) / usage
            score = max(0, min(1, float(before.get("score") or 0.5) + reward * 0.03))
            conn.execute(
                """
                INSERT INTO tool_policy (blocker_type, tool_name, score, usage_count, average_reward, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(blocker_type, tool_name)
                DO UPDATE SET score = excluded.score, usage_count = excluded.usage_count,
                    average_reward = excluded.average_reward, updated_at = excluded.updated_at
                """,
                (blocker_type, tool_name, score, usage, avg_reward, now_iso()),
            )
        return {"before": before, "after": {"score": score, "usage_count": usage, "average_reward": avg_reward}}

    def update_world_model_weights(self, belief_state: dict[str, Any], feedback: dict[str, Any]) -> dict[str, Any]:
        blocker = self._top_blocker(belief_state)
        reward = float(feedback.get("reward") or 0)
        if not blocker or reward == 0:
            return {}
        signal_name = "feedback_positive" if reward > 0 else "feedback_negative"
        delta = 0.03 if reward > 0 else -0.02
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM world_model_weights WHERE signal_name = ? AND blocker_type = ?",
                (signal_name, blocker),
            ).fetchone()
            before_weight = float(row["weight"]) if row else 0.1
            after_weight = max(0, min(1, before_weight + delta))
            conn.execute(
                """
                INSERT INTO world_model_weights (signal_name, blocker_type, weight, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(signal_name, blocker_type)
                DO UPDATE SET weight = excluded.weight, updated_at = excluded.updated_at
                """,
                (signal_name, blocker, after_weight, now_iso()),
            )
        return {"signal_name": signal_name, "blocker_type": blocker, "before": before_weight, "after": after_weight}

    def generate_reflection(self, decision: dict[str, Any], feedback: dict[str, Any]) -> dict[str, Any]:
        plan = decision.get("plan") or {}
        reward = float(feedback.get("reward") or 0)
        outcome = "succeeded" if reward > 0 else "failed_or_uncertain"
        return {
            "session_id": feedback.get("session_id"),
            "decision_id": feedback.get("decision_id"),
            "outcome": outcome,
            "reward": reward,
            "reflection": (
                f"Plan {plan.get('plan_id')} using {plan.get('tool_required')} {outcome} "
                f"for blocker {plan.get('target_blocker')}."
            ),
            "importance": 0.9 if abs(reward) >= 1 else 0.5,
        }

    def save_strategy_update(self, update: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO agent_evolution (update_type, before_json, after_json, reason, timestamp)
                VALUES ('feedback_policy_update', ?, ?, ?, ?)
                """,
                ("{}", json.dumps(update, ensure_ascii=False), "feedback_driven_self_evolution", now_iso()),
            )

    def _top_blocker(self, belief_state: dict[str, Any]) -> str:
        blockers = belief_state.get("blocker_belief") or {}
        return max(blockers, key=blockers.get) if blockers else ""
