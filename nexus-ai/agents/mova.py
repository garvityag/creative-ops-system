"""MOVA — Motion & Video Production Agent"""

import json
import re
from .base_agent import BaseAgent
from core.router import TaskType


class MovaAgent(BaseAgent):
    agent_id  = "mova"
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

    async def build_motion_plan(self, desi_output: dict | str, direction: dict | str = "", project: str = "") -> dict:
        """Build motion production plan from DESI output + approved direction."""
        desi_text = json.dumps(desi_output, indent=2) if isinstance(desi_output, dict) else str(desi_output)
        dir_text = json.dumps(direction, indent=2) if isinstance(direction, dict) else str(direction)
        task = (
            "Build a complete Motion Production Plan. "
            "Output as JSON with fields: project_overview, motion_language, storyboard_outline "
            "(array of {scene, duration, description, animation_notes}), animation_spec, "
            "sound_direction, ae_project_structure, asset_requirements, export_specs, review_milestones.\n\n"
            f"Design Assets / Plan:\n{desi_text}\n\nCreative Direction:\n{dir_text}"
        )
        return await self.run(task=task, project=project)
