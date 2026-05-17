"""COPY — Content & Copywriting Agent (OpenRouter openhermes, Claude fallback)"""

import json
import re
from .base_agent import BaseAgent
from core.router import TaskType


class CopyAgent(BaseAgent):
    agent_id  = "copy"
    task_type = TaskType.CREATIVE
    # Try openhermes via OpenRouter; router falls back to Claude if unavailable
    model_key = "openhermes"

    def parse_output(self, response: str):
        json_match = re.search(r"```(?:json|yaml)\s*([\s\S]+?)```", response)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                return json_match.group(1)
        return response

    async def write_copy(self, brief: dict | str, direction: dict | str = "", platforms: list = None, project: str = "") -> dict:
        """Write copy for all required touchpoints from brief + direction."""
        brief_text = json.dumps(brief, indent=2) if isinstance(brief, dict) else str(brief)
        dir_text = json.dumps(direction, indent=2) if isinstance(direction, dict) else str(direction)
        plat_list = ", ".join(platforms or ["instagram", "linkedin", "design_assets"])
        task = (
            f"Write copy for the following platforms: {plat_list}. "
            "Output as JSON array where each item has: type, platform, variant_a, variant_b, variant_c, rationale. "
            "Include: headlines, captions, CTAs, hashtags, scripts as applicable.\n\n"
            f"Brief:\n{brief_text}\n\nCreative Direction:\n{dir_text}"
        )
        return await self.run(task=task, project=project)
