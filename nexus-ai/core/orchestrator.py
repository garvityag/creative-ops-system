"""
NEXUS — ARIA Orchestrator
The main brain. Reads any task, decides routing, builds pipeline.
"""

import asyncio
import json
import uuid
from datetime import datetime
from typing import Optional

from core.router import router
from core.memory import memory
from config.models import TaskType


ARIA_SYSTEM = """You are ARIA, the master orchestrator of NEXUS — an autonomous creative AI system.
You are the brain. Your job:
1. Understand any incoming task completely
2. Decide which specialist agent handles it
3. Build a step-by-step pipeline
4. Return a structured JSON plan

Available agents:
- BRYN: Brief analysis, brand parsing, strategy
- IDEA: Creative concepts, moodboards, 3 directions
- DESI: Design production, Figma/Canva automation
- COPY: Copywriting, captions, scripts
- MOVA: Motion design planning, storyboards
- SOCI: Social media strategy, content calendars
- NOVA: HR — detects gaps, designs new agents
- ARCH: Workflow design, system improvements

You always respond in valid JSON. No extra text. Just JSON."""


ARIA_TASK_PROMPT = """
Analyze this task and return a pipeline plan:

TASK: {task}
CONTEXT: {context}
MEMORY: {memory_context}

Respond ONLY with this JSON structure:
{{
  "task_id": "unique_id",
  "task_summary": "one line summary",
  "task_type": "reasoning|creative|design|copy|motion|social|system",
  "priority": "high|medium|low",
  "pipeline": [
    {{
      "step": 1,
      "agent": "AGENT_NAME",
      "action": "what this agent does",
      "model": "claude-sonnet|phi3-mini|tinydolphin|openhermes",
      "input": "what input this agent needs",
      "output": "what this agent produces",
      "requires_approval": true/false
    }}
  ],
  "estimated_cost_usd": 0.01,
  "estimated_time_minutes": 5,
  "requires_human_approval": true/false,
  "approval_reason": "why approval needed or null"
}}
"""


class ARIAOrchestrator:
    """ARIA — The master orchestrator."""

    def __init__(self):
        self.active_tasks = {}

    async def process(self, task: str, context: str = "",
                      auto_execute: bool = False) -> dict:
        """
        Main entry point. Takes a task, returns execution plan.
        If auto_execute=True, runs the pipeline immediately.
        """
        task_id = f"task_{uuid.uuid4().hex[:8]}"

        # Recall relevant memory
        mem_results = memory.recall(task, "projects", n_results=3)
        memory_context = "\n".join([m["content"][:200] for m in mem_results]) or "No relevant memory"

        # Build prompt
        prompt = ARIA_TASK_PROMPT.format(
            task=task,
            context=context,
            memory_context=memory_context
        )

        # Call Claude for orchestration
        result = await router.run(
            prompt=prompt,
            task_type=TaskType.REASONING,
            agent="aria",
            system=ARIA_SYSTEM,
            force_model="claude-sonnet"
        )

        try:
            plan = json.loads(result["response"])
            plan["task_id"] = task_id
            plan["created_at"] = datetime.now().isoformat()
            plan["status"] = "planned"
            plan["router_info"] = {
                "model_used": result["model"],
                "tokens": result["tokens"],
                "cost_usd": result["cost"],
                "provider": result["provider"],
            }
        except json.JSONDecodeError:
            plan = {
                "task_id": task_id,
                "task_summary": task[:100],
                "status": "parse_error",
                "raw_response": result["response"],
                "router_info": result,
            }

        # Store in memory
        memory.remember_project(task_id, plan)
        self.active_tasks[task_id] = plan

        # Auto-execute if requested
        if auto_execute and plan.get("status") != "parse_error":
            if not plan.get("requires_human_approval", True):
                await self.execute_pipeline(plan)

        return plan

    async def execute_pipeline(self, plan: dict) -> dict:
        """Execute each step in the pipeline."""
        results = []
        plan["status"] = "running"

        for step in plan.get("pipeline", []):
            agent_name = step["agent"]
            action = step["action"]

            # Import and run agent
            result = await self._run_agent_step(agent_name, action, step, plan)
            results.append({
                "step": step["step"],
                "agent": agent_name,
                "result": result,
            })

            # Approval gate
            if step.get("requires_approval"):
                plan["status"] = "awaiting_approval"
                plan["paused_at_step"] = step["step"]
                plan["results_so_far"] = results
                return plan

        plan["status"] = "completed"
        plan["results"] = results
        return plan

    async def _run_agent_step(self, agent_name: str, action: str,
                               step: dict, plan: dict) -> str:
        """Run a single agent step."""
        # For Phase 1 — basic agent execution
        # Phase 2 will use full CrewAI agents

        system_prompts = {
            "BRYN": "You are BRYN, a creative strategist. Parse briefs and extract structured info.",
            "IDEA": "You are IDEA, a creative concepter. Generate 3 bold, distinct creative directions.",
            "DESI": "You are DESI, a design production specialist. Create detailed asset plans.",
            "COPY": "You are COPY, a copywriter. Write precise, platform-appropriate copy.",
            "MOVA": "You are MOVA, a motion designer. Plan animation specs and storyboards.",
            "SOCI": "You are SOCI, a social media strategist. Build content strategies.",
            "NOVA": "You are NOVA, an HR agent. Identify gaps and design new agents.",
            "ARCH": "You are ARCH, a workflow architect. Design and improve workflows.",
        }

        task_type_map = {
            "BRYN": TaskType.REASONING,
            "IDEA": TaskType.CREATIVE,
            "DESI": TaskType.CREATIVE,
            "COPY": TaskType.CHAT,
            "MOVA": TaskType.CREATIVE,
            "SOCI": TaskType.CHAT,
            "NOVA": TaskType.REASONING,
            "ARCH": TaskType.REASONING,
        }

        model_map = {
            "BRYN": "claude-sonnet",
            "IDEA": "claude-sonnet",
            "DESI": "claude-sonnet",
            "COPY": "openhermes",
            "MOVA": "claude-sonnet",
            "SOCI": "openhermes",
            "NOVA": "phi3-mini",
            "ARCH": "phi3-mini",
        }

        system = system_prompts.get(agent_name, "You are a helpful AI agent.")
        task_type = task_type_map.get(agent_name, TaskType.REASONING)
        model = step.get("model") or model_map.get(agent_name, "claude-haiku")

        prompt = f"""
Task: {plan.get('task_summary', '')}
Your job: {action}
Input: {step.get('input', '')}
Expected output: {step.get('output', '')}

Do your job. Be specific and actionable.
"""

        result = await router.run(
            prompt=prompt,
            task_type=task_type,
            agent=agent_name.lower(),
            system=system,
            force_model=model,
        )

        # Agent learns from this
        memory.agent_learned(
            agent_name.lower(),
            f"Completed task: {action}. Result quality: good.",
            "task_execution"
        )

        return result["response"]

    def get_active_tasks(self) -> list:
        return list(self.active_tasks.values())

    def approve_step(self, task_id: str) -> dict:
        """Human approves a paused pipeline step."""
        plan = self.active_tasks.get(task_id)
        if plan:
            plan["status"] = "approved"
            return plan
        return {"error": "Task not found"}


# Global orchestrator
aria = ARIAOrchestrator()
