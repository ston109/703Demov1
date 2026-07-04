from __future__ import annotations

import json
from typing import Any

from llm_client import BaseLLMClient, REASONING_SCHEMA, create_llm_client
from safety_guard import SafetyGuard


class ReasoningModule:
    def __init__(self, llm_client: BaseLLMClient | None = None, safety_guard: SafetyGuard | None = None):
        self.llm_client = llm_client or create_llm_client()
        self.safety_guard = safety_guard or SafetyGuard()

    def reason(
        self,
        world_state: dict[str, Any],
        belief_state: dict[str, Any],
        memories: list[dict[str, Any]],
        goals: list[str],
        tools: list[str],
        constraints: list[str],
    ) -> dict[str, Any]:
        llm_input = self.build_reasoning_input(world_state, belief_state, memories, goals, tools, constraints)
        prompt = (
            "You are a reasoning helper inside a compound AI shopping agent. "
            "Return JSON only. Do not choose or execute final actions. "
            "Do not request private data. Reason only from the provided redacted state.\n\n"
            f"Input:\n{json.dumps(llm_input, ensure_ascii=False, indent=2)}"
        )
        result = self.llm_client.generate_json(prompt, REASONING_SCHEMA)
        if result.status == "ok" and result.content:
            parsed = self.parse_reasoning_output(result.content)
            if parsed:
                parsed["llm"] = {
                    "provider": result.provider,
                    "model": result.model,
                    "status": result.status,
                    "latency_ms": result.latency_ms,
                }
                parsed["llm_input_summary"] = llm_input
                parsed["llm_output"] = result.content
                parsed["llm_reasoning"] = result.content
                parsed["used_fallback"] = False
                return parsed

        fallback = self.fallback_reasoning(world_state, belief_state)
        fallback["llm"] = {
            "provider": result.provider,
            "model": result.model,
            "status": result.status,
            "latency_ms": result.latency_ms,
            "error": result.error,
        }
        fallback["llm_input_summary"] = llm_input
        fallback["llm_output"] = result.content
        fallback["llm_reasoning"] = None
        fallback["used_fallback"] = True
        return fallback

    def build_reasoning_input(
        self,
        world_state: dict[str, Any],
        belief_state: dict[str, Any],
        memories: list[dict[str, Any]],
        goals: list[str],
        tools: list[str],
        constraints: list[str],
    ) -> dict[str, Any]:
        memory_summaries = []
        for item in memories[:5]:
            content = item.get("content") or {}
            memory_summaries.append(
                {
                    "memory_type": item.get("memory_type"),
                    "reward": item.get("reward"),
                    "summary": {
                        "plan": content.get("plan"),
                        "action": content.get("action"),
                        "reflection": content.get("reflection"),
                    },
                }
            )
        redacted = self.safety_guard.redact_sensitive_data(
            {
                "world_state": world_state,
                "belief_state": belief_state,
                "memories": memory_summaries,
                "goals": goals,
                "available_tools": tools,
                "safety_constraints": constraints,
            }
        )
        redacted["redaction_applied"] = True
        return redacted

    def parse_reasoning_output(self, raw_output: dict[str, Any]) -> dict[str, Any] | None:
        try:
            return {
                "situation_summary": str(raw_output["situation_summary"]),
                "main_hypothesis": str(raw_output["main_hypothesis"]),
                "alternative_hypotheses": list(raw_output.get("alternative_hypotheses") or []),
                "evidence_for": list(raw_output.get("evidence_for") or []),
                "evidence_against": list(raw_output.get("evidence_against") or []),
                "uncertainty": float(raw_output.get("uncertainty", 0.5)),
                "recommended_planning_direction": str(raw_output["recommended_planning_direction"]),
                "llm_confidence": float(raw_output.get("llm_confidence", 0.5)),
            }
        except (KeyError, TypeError, ValueError):
            return None

    def fallback_reasoning(self, world_state: dict[str, Any], belief_state: dict[str, Any]) -> dict[str, Any]:
        blockers = belief_state.get("blocker_belief") or {}
        main_blocker = max(blockers, key=blockers.get) if blockers else "unknown"
        direction_by_blocker = {
            "shipping_concern": "reduce_shipping_uncertainty",
            "price_concern": "reduce_price_uncertainty",
            "product_uncertainty": "increase_product_confidence",
            "comparison_hesitation": "support_product_comparison",
            "checkout_friction": "reduce_checkout_friction",
            "trust_concern": "increase_checkout_trust",
        }
        return {
            "situation_summary": (
                f"Session is in {world_state.get('current_stage')} with intent "
                f"{world_state.get('inferred_user_intent')}."
            ),
            "main_hypothesis": main_blocker,
            "alternative_hypotheses": [
                blocker for blocker, value in sorted(blockers.items(), key=lambda item: item[1], reverse=True)[1:3]
            ],
            "evidence_for": [item.get("type") for item in world_state.get("possible_blockers") or []],
            "evidence_against": [],
            "uncertainty": world_state.get("uncertainty", 0.5),
            "recommended_planning_direction": direction_by_blocker.get(main_blocker, "observe_more"),
            "llm_confidence": 0.0,
        }
