from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


class EvaluationLogger:
    def __init__(self, db: str | Path):
        self.db = str(db)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db)
        conn.row_factory = sqlite3.Row
        return conn

    def log_decision(self, decision: dict[str, Any]) -> None:
        return None

    def log_feedback(self, feedback: dict[str, Any]) -> None:
        return None

    def compute_metrics(self) -> dict[str, Any]:
        with self.connect() as conn:
            decisions = conn.execute("SELECT COUNT(*) AS c FROM agent_decisions").fetchone()["c"]
            safe = conn.execute(
                "SELECT COUNT(*) AS c FROM agent_decisions WHERE safety_status = 'approved'"
            ).fetchone()["c"]
            feedback_count = conn.execute("SELECT COUNT(*) AS c FROM agent_feedback").fetchone()["c"]
            avg_reward = conn.execute("SELECT AVG(reward) AS v FROM agent_feedback").fetchone()["v"]
            positive = conn.execute("SELECT COUNT(*) AS c FROM agent_feedback WHERE reward > 0").fetchone()["c"]
            annoyance = conn.execute(
                "SELECT COUNT(*) AS c FROM agent_feedback WHERE reward < 0 AND feedback_event_json LIKE '%popup_closed%'"
            ).fetchone()["c"]
            violations = conn.execute(
                "SELECT COUNT(*) AS c FROM agent_decisions WHERE safety_status != 'approved'"
            ).fetchone()["c"]
            avg_latency = conn.execute("SELECT AVG(llm_latency_ms) AS v FROM agent_decisions").fetchone()["v"]
            evolutions = conn.execute("SELECT COUNT(*) AS c FROM agent_evolution").fetchone()["c"]
            action_feedback = conn.execute("SELECT COUNT(*) AS c FROM action_feedback").fetchone()["c"]
            action_clicked = conn.execute(
                "SELECT COUNT(*) AS c FROM action_feedback WHERE feedback_type = 'action_clicked'"
            ).fetchone()["c"]
            action_shown = conn.execute(
                "SELECT COUNT(*) AS c FROM action_feedback WHERE feedback_type = 'action_shown'"
            ).fetchone()["c"]
            action_dismissed = conn.execute(
                "SELECT COUNT(*) AS c FROM action_feedback WHERE feedback_type = 'action_dismissed'"
            ).fetchone()["c"]
            action_blocked = conn.execute(
                "SELECT COUNT(*) AS c FROM action_feedback WHERE feedback_type = 'action_blocked_by_safety'"
            ).fetchone()["c"]
            errors = conn.execute("SELECT COUNT(*) AS c FROM error_logs").fetchone()["c"]
            tool_rows = conn.execute(
                """
                SELECT
                    COALESCE(tool_name, 'unknown') AS tool_name,
                    COUNT(*) AS feedback_count,
                    SUM(CASE WHEN feedback_type = 'action_shown' THEN 1 ELSE 0 END) AS shown,
                    SUM(CASE WHEN feedback_type = 'action_clicked' THEN 1 ELSE 0 END) AS clicked,
                    SUM(CASE WHEN feedback_type = 'action_dismissed' THEN 1 ELSE 0 END) AS dismissed,
                    SUM(CASE WHEN feedback_type = 'action_blocked_by_safety' THEN 1 ELSE 0 END) AS blocked,
                    AVG(reward) AS average_reward
                FROM action_feedback
                GROUP BY COALESCE(tool_name, 'unknown')
                ORDER BY feedback_count DESC, tool_name
                """
            ).fetchall()
            recent_feedback = conn.execute(
                "SELECT * FROM action_feedback ORDER BY id DESC LIMIT 20"
            ).fetchall()
        return {
            "action_success_rate": round((positive / feedback_count), 2) if feedback_count else 0,
            "conversion_recovery_rate": round((positive / max(decisions, 1)), 2) if decisions else 0,
            "average_reward": round(float(avg_reward or 0), 2),
            "tool_usage_accuracy": round((safe / decisions), 2) if decisions else 0,
            "safety_violation_count": violations,
            "average_latency": round(float(avg_latency or 0), 2),
            "user_annoyance_rate": round((annoyance / feedback_count), 2) if feedback_count else 0,
            "world_model_prediction_accuracy": 0,
            "belief_confidence_calibration": 0,
            "self_evolution_improvement_rate": round((evolutions / max(feedback_count, 1)), 2)
            if feedback_count
            else 0,
            "decision_count": decisions,
            "feedback_count": feedback_count,
            "action_feedback_count": action_feedback,
            "action_show_count": action_shown,
            "action_click_rate": round(action_clicked / action_shown, 2) if action_shown else 0,
            "action_dismiss_rate": round(action_dismissed / action_shown, 2) if action_shown else 0,
            "action_blocked_rate": round(action_blocked / max(action_feedback, 1), 2) if action_feedback else 0,
            "error_count": errors,
            "tool_performance": [
                {
                    "tool_name": row["tool_name"],
                    "feedback_count": row["feedback_count"],
                    "shown": row["shown"] or 0,
                    "clicked": row["clicked"] or 0,
                    "dismissed": row["dismissed"] or 0,
                    "blocked": row["blocked"] or 0,
                    "click_rate": round((row["clicked"] or 0) / (row["shown"] or 1), 2) if row["shown"] else 0,
                    "average_reward": round(float(row["average_reward"] or 0), 2),
                }
                for row in tool_rows
            ],
            "recent_action_feedback": [dict(row) for row in recent_feedback],
        }
