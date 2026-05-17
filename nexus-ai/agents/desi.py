"""DESI — Design & Asset Production Agent"""

import json
import re
from .base_agent import BaseAgent
from core.router import TaskType


class DesiAgent(BaseAgent):
    agent_id  = "desi"
    task_type = TaskType.REASONING
    model_key = None  # claude-sonnet

    def parse_output(self, response: str):
        json_match = re.search(r"```(?:json|yaml)\s*([\s\S]+?)```", response)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                return json_match.group(1)
        return response

    async def build_production_plan(self, direction: dict | str, brief: dict | str = "", project: str = "") -> dict:
        """Build a full asset production plan from an approved creative direction."""
        dir_text = json.dumps(direction, indent=2) if isinstance(direction, dict) else str(direction)
        brief_text = json.dumps(brief, indent=2) if isinstance(brief, dict) else str(brief)
        task = (
            "Based on the approved creative direction (and brief context), produce a full Asset Production Plan. "
            "Output as JSON with fields: project_overview, asset_inventory (array of {name, format, dimensions, quantity}), "
            "design_system (colors, typography, spacing, grid), file_structure, tool_assignments, "
            "production_checklist (ordered array), export_specs, quality_checks.\n\n"
            f"Creative Direction:\n{dir_text}\n\nBrief Context:\n{brief_text}"
        )
        return await self.run(task=task, project=project)
