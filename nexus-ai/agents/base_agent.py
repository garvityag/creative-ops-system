"""
Base agent class — all NEXUS agents inherit from this.
Loads system prompt from the YAML in agents/{agent_id}.yaml,
routes through core/router.py, logs to core/memory.py,
and posts status updates to the Vercel dashboard.
"""

import os
import yaml
import httpx
import asyncio
from pathlib import Path
from typing import Optional
from datetime import datetime

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.router import router, TaskType
from core.memory import memory


# Path to the YAML agent definitions (two levels up from nexus-ai/agents/)
YAML_DIR = Path(__file__).parent.parent.parent / "agents"
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "https://agents.garvityagnik.in")
DASHBOARD_SECRET = os.getenv("DASHBOARD_SECRET", "")


def load_yaml_prompt(agent_id: str) -> dict:
    """Load agent config + system_prompt from agents/{agent_id}.yaml"""
    yaml_path = YAML_DIR / f"{agent_id}.yaml"
    if not yaml_path.exists():
        raise FileNotFoundError(f"YAML not found: {yaml_path}")
    with open(yaml_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class BaseAgent:
    """
    Base class for all NEXUS agents.
    Subclasses only need to define: agent_id, task_type, model_key
    and optionally override: parse_output()
    """

    agent_id: str = "base"
    task_type: TaskType = TaskType.REASONING
    model_key: Optional[str] = None  # None = router decides

    def __init__(self):
        config = load_yaml_prompt(self.agent_id)
        self.name = config.get("name", self.agent_id.upper())
        self.full_name = config.get("full_name", self.name)
        self.role = config.get("role", "")
        self.emoji = config.get("emoji", "○")
        self.model_id = config.get("model", "claude-sonnet-4-20250514")
        self.system_prompt: str = config.get("system_prompt", "")
        self.downstream: list = config.get("downstream_agents", [])

    # ── Public API ──────────────────────────────────────────────────────────

    async def run(self, task: str, context: str = "", project: str = "") -> dict:
        """
        Run a task through this agent.
        Returns: { response, model, tokens, cost, agent, success }
        """
        print(f"\n[{self.emoji} {self.name}] Starting: {task[:80]}...")
        await self._set_status("busy", task, project)

        prompt = f"{context}\n\nTask: {task}".strip() if context else task

        try:
            result = await router.run(
                prompt=prompt,
                task_type=self.task_type,
                agent=self.agent_id,
                system=self.system_prompt,
                force_model=self.model_key,
            )

            output = self.parse_output(result["response"])
            await memory.save_task(self.agent_id, task, result["response"], project)
            await self._post_dashboard_usage(result)
            await self._set_status("idle")

            print(f"[{self.emoji} {self.name}] Done — {result.get('tokens', 0)} tokens, ${result.get('cost', 0):.4f}")

            return {
                "success":  True,
                "agent":    self.agent_id,
                "task":     task,
                "response": result["response"],
                "output":   output,
                "model":    result.get("model", ""),
                "tokens":   result.get("tokens", 0),
                "cost":     result.get("cost", 0.0),
                "provider": result.get("provider", ""),
            }

        except Exception as e:
            await self._set_status("idle")
            print(f"[{self.emoji} {self.name}] Error: {e}")
            return {
                "success":  False,
                "agent":    self.agent_id,
                "error":    str(e),
                "response": "",
                "output":   None,
            }

    def parse_output(self, response: str):
        """
        Override in subclasses to parse structured output.
        Default: return raw string.
        """
        return response

    # ── Dashboard integration ───────────────────────────────────────────────

    async def _set_status(self, status: str, task: str = "", project: str = ""):
        if not DASHBOARD_SECRET:
            return
        payload = {
            "secret":   DASHBOARD_SECRET,
            "agent_id": self.agent_id,
            "updates": {
                "status":          status,
                "current_task":    task or None,
                "current_project": project or None,
                "last_active":     datetime.now().isoformat(),
            }
        }
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(f"{DASHBOARD_URL}/api/agents", json=payload)
        except Exception:
            pass  # Non-fatal

    async def _post_dashboard_usage(self, result: dict):
        if not DASHBOARD_SECRET:
            return
        tokens_in  = result.get("tokens", 0) // 2  # approximate split
        tokens_out = result.get("tokens", 0) - tokens_in
        payload = {
            "secret":       DASHBOARD_SECRET,
            "agent":        self.agent_id,
            "model":        result.get("model_id", self.model_id),
            "provider":     result.get("provider", "anthropic"),
            "tokens_in":    tokens_in,
            "tokens_out":   tokens_out,
            "cost_usd":     result.get("cost", 0.0),
            "task_summary": result.get("task_summary", "")[:100],
        }
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(f"{DASHBOARD_URL}/api/usage", json=payload)
        except Exception:
            pass  # Non-fatal

    async def _advance_pipeline(self, output_summary: str = ""):
        if not DASHBOARD_SECRET:
            return
        payload = {
            "secret":         DASHBOARD_SECRET,
            "action":         "step",
            "output_summary": output_summary[:200],
        }
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(f"{DASHBOARD_URL}/api/pipeline", json=payload)
        except Exception:
            pass  # Non-fatal
