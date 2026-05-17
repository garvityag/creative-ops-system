"""NOVA — New Agent Onboarding & Validation Agent (phi3:mini via Ollama)"""

import json
import re
from .base_agent import BaseAgent
from core.router import TaskType


class NovaAgent(BaseAgent):
    agent_id  = "nova"
    task_type = TaskType.REASONING
    model_key = "phi3-mini"  # Ollama local

    def parse_output(self, response: str):
        json_match = re.search(r"```(?:json|yaml)\s*([\s\S]+?)```", response)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                return json_match.group(1)
        return response

    async def detect_gap(self, task_description: str, existing_agents: list = None) -> dict:
        """
        Analyze a task for capability gaps not covered by existing agents.
        Sends a notification to the dashboard if a gap is found.
        """
        agents_str = ", ".join(existing_agents or ["aria","bryn","idea","desi","copy","mova","soci","nova","arch"])
        task = (
            f"Existing agents: {agents_str}.\n"
            f"New task: {task_description}\n\n"
            "Analyze: is this task covered by an existing agent? "
            "If a capability gap exists, output JSON with: gap_detected (bool), gap_description, "
            "proposed_agent_name, proposed_role, proposed_tools (array), proposed_triggers (array), "
            "justification. If no gap, output: {gap_detected: false}."
        )
        result = await self.run(task=task)

        # If gap detected, notify dashboard
        if isinstance(result.get("output"), dict) and result["output"].get("gap_detected"):
            await self._notify_dashboard(result["output"])

        return result

    async def _notify_dashboard(self, gap_data: dict):
        import httpx, os
        from datetime import datetime
        payload = {
            "secret": os.getenv("DASHBOARD_SECRET", ""),
            "type":   "nova_alert",
            "data": {
                "message":    f"NOVA detected gap: {gap_data.get('proposed_agent_name','?')} — {gap_data.get('proposed_role','')}",
                "agent_name": gap_data.get("proposed_agent_name"),
                "gap":        gap_data.get("gap_description"),
                "timestamp":  datetime.now().isoformat(),
            }
        }
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(f"{self._dashboard_url()}/api/agents", json=payload)
        except Exception:
            pass

    def _dashboard_url(self):
        import os
        return os.getenv("DASHBOARD_URL", "https://agents.garvityagnik.in")
