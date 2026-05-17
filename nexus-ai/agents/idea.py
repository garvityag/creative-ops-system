"""IDEA — Ideation & Design Exploration Agent"""

import json
import re
from .base_agent import BaseAgent
from core.router import TaskType


class IdeaAgent(BaseAgent):
    agent_id  = "idea"
    task_type = TaskType.CREATIVE
    model_key = None  # claude-sonnet

    def parse_output(self, response: str):
        """Extract 3 creative directions as structured data."""
        json_match = re.search(r"```(?:json|yaml)\s*([\s\S]+?)```", response)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                return json_match.group(1)
        return response

    async def generate_directions(self, brief: dict | str, project: str = "") -> dict:
        """Generate 3 creative directions from an approved brief."""
        brief_text = json.dumps(brief, indent=2) if isinstance(brief, dict) else str(brief)
        task = (
            "Based on the following approved creative brief, generate exactly 3 distinct creative directions. "
            "Output as JSON array where each item has: direction_name, concept, visual_language, "
            "motion_language, tone, references (array), rationale, recommended (bool).\n\n"
            f"Brief:\n{brief_text}"
        )
        return await self.run(task=task, project=project)
