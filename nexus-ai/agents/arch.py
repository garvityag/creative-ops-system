"""ARCH — Workflow & Agent Architecture Agent (phi3:mini via Ollama)"""

import json
import re
from .base_agent import BaseAgent
from core.router import TaskType


class ArchAgent(BaseAgent):
    agent_id  = "arch"
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

    async def design_workflow(self, task_description: str, project: str = "") -> dict:
        """Design a workflow for a new type of project."""
        task = (
            f"Design a workflow for: {task_description}\n\n"
            "Output as JSON with: workflow_name, trigger, end_state, steps (array of "
            "{step, agent, input, output, approval_required}), "
            "approval_gates (array), autonomy_zones (array)."
        )
        return await self.run(task=task, project=project)

    async def audit_agent(self, agent_id: str, performance_notes: str = "") -> dict:
        """Audit an agent's instructions and suggest improvements."""
        task = (
            f"Audit agent '{agent_id}' with these performance notes: {performance_notes or 'None provided'}.\n\n"
            "Output as JSON with: agent_id, issues_found (array), improvements (array of "
            "{field, current_value, suggested_value, reason}), priority (high/medium/low), "
            "estimated_impact."
        )
        return await self.run(task=task)

    async def monthly_review(self, usage_stats: dict) -> dict:
        """Run a monthly system review from usage statistics."""
        stats_str = json.dumps(usage_stats, indent=2)
        task = (
            f"Run a monthly system review from these usage stats:\n{stats_str}\n\n"
            "Output as JSON with: most_used_agents, least_used_agents, bottlenecks, "
            "manual_tasks_to_automate, outdated_agents, new_tool_recommendations, "
            "summary (2–3 sentence narrative)."
        )
        return await self.run(task=task)
