from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from action_executor import ActionExecutor
from belief_state import BeliefStateBuilder
from evaluation import EvaluationLogger
from evolution_engine import EvolutionEngine
from feedback import FeedbackCollector
from goal_manager import GoalManager
from llm_client import NullLLMClient
from memory_store import MemoryStore
from planner import Planner
from reasoning_module import ReasoningModule
from safety_guard import SafetyGuard
from tools import ToolRegistry
from world_model import WorldModel


class AGIAgent:
    def __init__(self, db: str | Path):
        self.db = str(db)
        self.world_model = WorldModel(db)
        self.belief_builder = BeliefStateBuilder()
        self.memory = MemoryStore(db)
        self.goal_manager = GoalManager()
        self.safety = SafetyGuard()
        self.reasoner = ReasoningModule(NullLLMClient(), self.safety)
        self.planner = Planner()
        self.tools = ToolRegistry()
        self.executor = ActionExecutor(self.tools)
        self.feedback = FeedbackCollector(db)
        self.evaluator = EvaluationLogger(db)
        self.evolution = EvolutionEngine(db)

    def observe(self, event: dict[str, Any]) -> None:
        self.memory.save_event(event)
        self.world_model.update_from_event(event)

    def think(self, session_id: str) -> dict[str, Any]:
        risk_signal = self.get_risk_signal(session_id)
        world_state = self.world_model.build_world_state(session_id, risk_signal)
        preliminary_belief = self.belief_builder.build(world_state, risk_signal, [])
        memory_matches = self.memory.retrieve_similar_cases(preliminary_belief)
        belief_state = self.belief_builder.build(world_state, risk_signal, memory_matches)
        self._save_belief_state(session_id, belief_state)

        goals = self.goal_manager.get_active_goals()
        tools = self.tools.get_available_tools(world_state)
        constraints = self.safety.get_constraints()
        reasoning = self.reasoner.reason(world_state, belief_state, memory_matches, goals, tools, constraints)
        candidate_plans = self.planner.generate_candidate_plans(reasoning, belief_state, tools)
        scored_plans = [
            self.planner.score_plan(plan, goals, memory_matches)
            for plan in candidate_plans
        ]
        best_plan = self.planner.select_best_plan(scored_plans)
        best_plan["goal_alignment"] = self.goal_manager.score_goal_alignment(best_plan, belief_state)
        best_plan["score"] = round((best_plan.get("score", 0) + best_plan["goal_alignment"]) / 2, 2)

        safety_result = self.safety.check_plan(best_plan, world_state, belief_state)
        if not safety_result["allowed"]:
            best_plan = self.planner.create_safe_fallback_plan(safety_result)

        action_result = self.executor.execute_plan(best_plan)
        payload_safety = self.safety.check_action_payload(action_result.get("payload") or {})
        if not payload_safety["allowed"]:
            best_plan = self.planner.create_safe_fallback_plan(payload_safety)
            action_result = self.executor.execute_plan(best_plan)
            safety_result = payload_safety

        decision = {
            "session_id": session_id,
            "world_state": world_state,
            "belief_state": belief_state,
            "reasoning": reasoning,
            "candidate_plans": scored_plans,
            "plan": best_plan,
            "action": action_result,
            "safety": safety_result,
        }
        decision_id = self.memory.save_decision(decision)
        decision["decision_id"] = decision_id
        self.evaluator.log_decision(decision)
        return decision

    def receive_feedback(self, feedback_event: dict[str, Any]) -> dict[str, Any]:
        feedback_record = self.feedback.save_feedback(feedback_event)
        related_decision = self.memory.get_decision(feedback_record.get("decision_id"))
        evolution = self.evolution.evolve_from_feedback(feedback_record, related_decision)
        feedback_record["evolution"] = evolution
        self.evaluator.log_feedback(feedback_record)
        return feedback_record

    def get_risk_signal(self, session_id: str) -> dict[str, Any]:
        with sqlite3.connect(self.db) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT current_score, current_state FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if not row:
            return {"score": 100, "state": "unknown"}
        return {"score": int(row["current_score"]), "state": row["current_state"]}

    def _save_belief_state(self, session_id: str, belief_state: dict[str, Any]) -> None:
        import json
        from datetime import datetime, timezone

        with sqlite3.connect(self.db) as conn:
            conn.execute(
                "INSERT INTO belief_states (session_id, belief_state_json, timestamp) VALUES (?, ?, ?)",
                (session_id, json.dumps(belief_state, ensure_ascii=False), datetime.now(timezone.utc).isoformat()),
            )
