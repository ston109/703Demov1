from __future__ import annotations

from typing import Any

from tools import ToolRegistry


class ActionExecutor:
    def __init__(self, tool_registry: ToolRegistry):
        self.tool_registry = tool_registry

    def execute_plan(self, plan: dict[str, Any]) -> dict[str, Any]:
        tool_name = plan.get("tool_required", "do_nothing")
        payload = self.tool_registry.execute(
            tool_name,
            {
                "target_page": plan.get("target_page"),
                "rating": plan.get("rating"),
            },
        )
        return {
            "tool_name": tool_name,
            "payload": payload,
            "status": "executed",
        }
