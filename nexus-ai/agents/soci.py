"""SOCI — Social Media & Campaign Agent (OpenRouter openhermes)"""

import json
import re
from .base_agent import BaseAgent
from core.router import TaskType


class SociAgent(BaseAgent):
    agent_id  = "soci"
    task_type = TaskType.CREATIVE
    model_key = "openhermes"  # OpenRouter, Claude fallback

    def parse_output(self, response: str):
        json_match = re.search(r"```(?:json|yaml)\s*([\s\S]+?)```", response)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                return json_match.group(1)
        return response

    async def build_calendar(self, desi_output: dict | str, copy_output: dict | str, project: str = "") -> dict:
        """Build a content calendar from DESI + COPY output."""
        desi_text = json.dumps(desi_output, indent=2) if isinstance(desi_output, dict) else str(desi_output)
        copy_text = json.dumps(copy_output, indent=2) if isinstance(copy_output, dict) else str(copy_output)
        task = (
            "Build a monthly social media content calendar from the available assets and copy. "
            "Output as JSON with: calendar (array of posts with {date, platform, content_type, "
            "asset_ref, caption, hashtags, cta, campaign_tag}), posting_strategy, rollout_phases.\n\n"
            f"Design Assets:\n{desi_text}\n\nCopy:\n{copy_text}"
        )
        return await self.run(task=task, project=project)
