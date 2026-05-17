"""BRYN — Brief Analyst & Creative Strategist"""

import json
import re
from .base_agent import BaseAgent
from core.router import TaskType


class BrynAgent(BaseAgent):
    agent_id  = "bryn"
    task_type = TaskType.REASONING
    model_key = None  # uses claude-sonnet from YAML

    def parse_output(self, response: str):
        """Try to extract structured brief as JSON/YAML block, else return raw."""
        # Look for a JSON or YAML block in the response
        json_match = re.search(r"```(?:json|yaml)\s*([\s\S]+?)```", response)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                return json_match.group(1)  # Return raw YAML string
        return response

    async def analyze_brief(self, raw_input: str, project: str = "") -> dict:
        """Main entry — transform raw input into a structured creative brief."""
        task = (
            "Analyze the following brief/input and produce a structured Creative Brief Document. "
            "Output as JSON with fields: project_name, objective, audience, tone, key_message, "
            "deliverables, constraints, timeline, references, success_metrics, clarifying_questions.\n\n"
            f"Input:\n{raw_input}"
        )
        return await self.run(task=task, project=project)
