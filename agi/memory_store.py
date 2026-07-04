from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def loads(value: str | None, fallback: Any = None) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


class MemoryStore:
    def __init__(self, db: str | Path):
        self.db = str(db)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db)
        conn.row_factory = sqlite3.Row
        return conn

    def save_event(self, event: dict[str, Any]) -> None:
        user = event.get("user") or {}
        source = event.get("source") or {}
        body = event.get("event") or {}
        product = event.get("product") or {}
        cart = event.get("cart") or {}
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO user_events (
                    session_id, event_type, page, product_id, metadata_json, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    user.get("sessionId"),
                    body.get("type", "unknown"),
                    source.get("url") or source.get("pageType"),
                    product.get("productId"),
                    dumps({"source": source, "event": body, "cart": cart, "product": product}),
                    event.get("timestamp") or now_iso(),
                ),
            )
            conn.execute(
                """
                INSERT INTO agent_memory (
                    session_id, memory_type, content_json, importance, reward, timestamp
                ) VALUES (?, 'sensory', ?, ?, 0, ?)
                """,
                (user.get("sessionId"), dumps(event), 0.3, event.get("timestamp") or now_iso()),
            )

    def save_decision(self, decision: dict[str, Any]) -> int:
        action = decision.get("action") or {}
        plan = decision.get("plan") or {}
        reasoning = decision.get("reasoning") or {}
        llm = reasoning.get("llm") or {}
        safety = decision.get("safety") or {}
        timestamp = now_iso()
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO agent_decisions (
                    session_id, world_state_json, belief_state_json, reasoning_json,
                    plan_json, selected_tool, action_payload_json, confidence,
                    safety_status, llm_provider, llm_model, llm_status,
                    llm_latency_ms, llm_reasoning_json, llm_input_summary_json,
                    llm_output_json, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision.get("session_id"),
                    dumps(decision.get("world_state")),
                    dumps(decision.get("belief_state")),
                    dumps(reasoning),
                    dumps(plan),
                    plan.get("tool_required") or action.get("tool_name"),
                    dumps(action.get("payload") or action),
                    float(plan.get("confidence") or decision.get("belief_state", {}).get("confidence") or 0),
                    safety.get("status", "unknown"),
                    llm.get("provider", "none"),
                    llm.get("model", "none"),
                    llm.get("status", "unknown"),
                    int(llm.get("latency_ms") or 0),
                    dumps(reasoning.get("llm_reasoning")),
                    dumps(reasoning.get("llm_input_summary")),
                    dumps(reasoning.get("llm_output")),
                    timestamp,
                ),
            )
            decision_id = int(cur.lastrowid)
            conn.execute(
                """
                INSERT INTO agent_memory (
                    session_id, memory_type, content_json, importance, reward, timestamp
                ) VALUES (?, 'decision', ?, ?, 0, ?)
                """,
                (decision.get("session_id"), dumps({**decision, "decision_id": decision_id}), 0.7, timestamp),
            )
        return decision_id

    def save_feedback(self, feedback: dict[str, Any]) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO agent_feedback (
                    session_id, decision_id, feedback_event_json, reward, timestamp
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    feedback.get("session_id"),
                    feedback.get("decision_id"),
                    dumps(feedback.get("event") or feedback),
                    float(feedback.get("reward") or 0),
                    feedback.get("timestamp") or now_iso(),
                ),
            )
            return int(cur.lastrowid)

    def retrieve_similar_cases(self, belief_state: dict[str, Any], top_k: int = 5) -> list[dict[str, Any]]:
        blockers = belief_state.get("blocker_belief") or {}
        top_blocker = max(blockers, key=blockers.get) if blockers else ""
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM agent_memory
                WHERE memory_type IN ('decision', 'reflection')
                ORDER BY ABS(COALESCE(reward, 0)) DESC, id DESC
                LIMIT ?
                """,
                (max(top_k * 4, top_k),),
            ).fetchall()
        matches = []
        for row in rows:
            content = loads(row["content_json"], {})
            text = dumps(content).lower()
            if not top_blocker or top_blocker in text or len(matches) < top_k:
                matches.append({**dict(row), "content": content})
            if len(matches) >= top_k:
                break
        return matches

    def retrieve_successful_strategies(self, blocker_type: str, top_k: int = 5) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM agent_memory
                WHERE memory_type IN ('decision', 'reflection') AND reward > 0
                ORDER BY reward DESC, id DESC
                LIMIT ?
                """,
                (top_k * 3,),
            ).fetchall()
        return [
            {**dict(row), "content": loads(row["content_json"], {})}
            for row in rows
            if blocker_type.lower() in (row["content_json"] or "").lower()
        ][:top_k]

    def save_reflection(self, reflection: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO agent_memory (
                    session_id, memory_type, content_json, importance, reward, timestamp
                ) VALUES (?, 'reflection', ?, ?, ?, ?)
                """,
                (
                    reflection.get("session_id"),
                    dumps(reflection),
                    float(reflection.get("importance") or 0.8),
                    float(reflection.get("reward") or 0),
                    now_iso(),
                ),
            )

    def get_decision(self, decision_id: int | str | None) -> dict[str, Any] | None:
        if not decision_id:
            return None
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM agent_decisions WHERE id = ?", (decision_id,)).fetchone()
        if not row:
            return None
        item = dict(row)
        for key in ("world_state_json", "belief_state_json", "reasoning_json", "plan_json", "action_payload_json"):
            item[key.replace("_json", "")] = loads(item.get(key), {})
        return item
