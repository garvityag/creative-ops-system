"""
NEXUS — Smart Model Router
Decides which AI model handles which task.
Auto-fallback when limits hit or model unavailable.
Tracks token usage and costs.
"""

import os
import json
import time
import sqlite3
import asyncio
from datetime import datetime
from typing import Optional, AsyncGenerator
from dotenv import load_dotenv

load_dotenv()

# ── Import models config ──────────────────────────────────────
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config.models import MODELS, FALLBACK_CHAIN, TaskType, ModelProvider, get_best_model


class UsageTracker:
    """Tracks token usage + costs in SQLite."""

    def __init__(self, db_path: str = "./nexus_usage.db"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._init_db()

    def _init_db(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                agent TEXT,
                model TEXT,
                provider TEXT,
                task_type TEXT,
                prompt_tokens INTEGER,
                completion_tokens INTEGER,
                total_tokens INTEGER,
                cost_usd REAL,
                task_summary TEXT,
                status TEXT
            )
        """)
        self.conn.commit()

    def log(self, agent: str, model: str, provider: str, task_type: str,
            prompt_tokens: int, completion_tokens: int, cost_usd: float,
            task_summary: str = "", status: str = "success"):
        total = prompt_tokens + completion_tokens
        self.conn.execute("""
            INSERT INTO usage (timestamp, agent, model, provider, task_type,
                prompt_tokens, completion_tokens, total_tokens, cost_usd,
                task_summary, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (datetime.now().isoformat(), agent, model, provider, task_type,
              prompt_tokens, completion_tokens, total, cost_usd, task_summary, status))
        self.conn.commit()

    def get_daily_cost(self) -> float:
        today = datetime.now().strftime("%Y-%m-%d")
        row = self.conn.execute(
            "SELECT SUM(cost_usd) FROM usage WHERE timestamp LIKE ?", (f"{today}%",)
        ).fetchone()
        return row[0] or 0.0

    def get_monthly_cost(self) -> float:
        month = datetime.now().strftime("%Y-%m")
        row = self.conn.execute(
            "SELECT SUM(cost_usd) FROM usage WHERE timestamp LIKE ?", (f"{month}%",)
        ).fetchone()
        return row[0] or 0.0

    def get_recent(self, limit: int = 50) -> list[dict]:
        rows = self.conn.execute("""
            SELECT timestamp, agent, model, provider, task_type,
                   total_tokens, cost_usd, task_summary, status
            FROM usage ORDER BY id DESC LIMIT ?
        """, (limit,)).fetchall()
        keys = ["timestamp","agent","model","provider","task_type",
                "total_tokens","cost_usd","task_summary","status"]
        return [dict(zip(keys, r)) for r in rows]

    def get_agent_stats(self) -> list[dict]:
        rows = self.conn.execute("""
            SELECT agent, model, COUNT(*) as tasks,
                   SUM(total_tokens) as tokens, SUM(cost_usd) as cost
            FROM usage GROUP BY agent, model ORDER BY tasks DESC
        """).fetchall()
        return [{"agent":r[0],"model":r[1],"tasks":r[2],"tokens":r[3],"cost":r[4]} for r in rows]


# Global tracker
tracker = UsageTracker()


class NexusRouter:
    """
    Smart AI router — picks best model, handles fallback.
    Claude → GPT → Gemini → Ollama (in order of capability/cost).
    """

    def __init__(self):
        self.monthly_budget = float(os.getenv("MONTHLY_BUDGET_USD", "10.0"))
        self._claude_client = None
        self._openai_client = None

    def _get_claude(self):
        if not self._claude_client:
            import anthropic
            self._claude_client = anthropic.Anthropic(
                api_key=os.getenv("ANTHROPIC_API_KEY")
            )
        return self._claude_client

    def _get_openai(self):
        if not self._openai_client:
            import openai
            self._openai_client = openai.OpenAI(
                api_key=os.getenv("OPENAI_API_KEY")
            )
        return self._openai_client

    def _budget_ok(self) -> bool:
        return tracker.get_monthly_cost() < self.monthly_budget

    async def run(self, prompt: str, task_type: TaskType = TaskType.REASONING,
                  agent: str = "aria", system: str = "",
                  force_model: Optional[str] = None,
                  budget_conscious: bool = False) -> dict:
        """
        Run a prompt through the best available model.
        Returns: { response, model, tokens, cost, provider }
        """

        # Force specific model if requested
        if force_model and force_model in MODELS:
            model_config = MODELS[force_model]
        else:
            # Budget check — use free models if over budget
            bc = budget_conscious or not self._budget_ok()
            model_config = get_best_model(task_type, bc)

        # Try model, fallback if needed
        chain = FALLBACK_CHAIN.get(task_type, ["claude-haiku", "phi3-mini"])
        tried = []

        for model_key in chain:
            mc = MODELS.get(model_key)
            if not mc or not mc.available or model_key in tried:
                continue
            if not self._budget_ok() and mc.cost_per_1k_tokens > 0:
                continue  # Skip paid models if over budget

            tried.append(model_key)

            try:
                result = await self._call_model(mc, prompt, system, agent, task_type)
                return result
            except Exception as e:
                print(f"[NEXUS] {mc.name} failed: {e} — trying fallback...")
                continue

        # Ultimate fallback — Ollama phi3
        try:
            mc = MODELS["phi3-mini"]
            return await self._call_ollama(mc, prompt, system, agent, task_type)
        except Exception as e:
            return {
                "response": f"All models failed. Last error: {e}",
                "model": "none",
                "tokens": 0,
                "cost": 0.0,
                "provider": "none",
                "error": True,
            }

    async def _call_model(self, mc, prompt: str, system: str,
                           agent: str, task_type: TaskType) -> dict:
        """Route to correct provider."""
        if mc.provider == ModelProvider.CLAUDE:
            return await self._call_claude(mc, prompt, system, agent, task_type)
        elif mc.provider == ModelProvider.OLLAMA:
            return await self._call_ollama(mc, prompt, system, agent, task_type)
        elif mc.provider == ModelProvider.OPENAI:
            return await self._call_openai(mc, prompt, system, agent, task_type)
        elif mc.provider == ModelProvider.GEMINI:
            return await self._call_gemini(mc, prompt, system, agent, task_type)
        else:
            raise ValueError(f"Unknown provider: {mc.provider}")

    async def _call_claude(self, mc, prompt, system, agent, task_type) -> dict:
        client = self._get_claude()
        messages = [{"role": "user", "content": prompt}]
        kwargs = {"model": mc.model_id, "max_tokens": mc.max_tokens, "messages": messages}
        if system:
            kwargs["system"] = system

        # Run in executor (anthropic is sync)
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, lambda: client.messages.create(**kwargs))

        text = response.content[0].text
        tokens_in = response.usage.input_tokens
        tokens_out = response.usage.output_tokens
        cost = (tokens_in * mc.cost_per_1k_tokens / 1000) + (tokens_out * mc.cost_per_1k_tokens * 3 / 1000)

        tracker.log(agent, mc.model_id, "claude", task_type.value,
                    tokens_in, tokens_out, cost, prompt[:100])
        return {"response": text, "model": mc.name, "model_id": mc.model_id,
                "tokens": tokens_in + tokens_out, "cost": cost, "provider": "claude"}

    async def _call_ollama(self, mc, prompt, system, agent, task_type) -> dict:
        url = os.getenv("OLLAMA_URL", "http://localhost:11434")
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        async with __import__("aiohttp").ClientSession() as session:
            payload = {"model": mc.model_id, "messages": messages, "stream": False}
            async with session.post(f"{url}/api/chat", json=payload) as resp:
                data = await resp.json()
                text = data["message"]["content"]

        tracker.log(agent, mc.model_id, "ollama", task_type.value, 0, 0, 0.0, prompt[:100])
        return {"response": text, "model": mc.name, "model_id": mc.model_id,
                "tokens": 0, "cost": 0.0, "provider": "ollama (free)"}

    async def _call_openai(self, mc, prompt, system, agent, task_type) -> dict:
        client = self._get_openai()
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, lambda: client.chat.completions.create(
            model=mc.model_id, messages=messages, max_tokens=mc.max_tokens
        ))
        text = response.choices[0].message.content
        tokens_in = response.usage.prompt_tokens
        tokens_out = response.usage.completion_tokens
        cost = (tokens_in + tokens_out) * mc.cost_per_1k_tokens / 1000

        tracker.log(agent, mc.model_id, "openai", task_type.value,
                    tokens_in, tokens_out, cost, prompt[:100])
        return {"response": text, "model": mc.name, "model_id": mc.model_id,
                "tokens": tokens_in + tokens_out, "cost": cost, "provider": "openai"}

    async def _call_gemini(self, mc, prompt, system, agent, task_type) -> dict:
        import google.generativeai as genai
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        model = genai.GenerativeModel(mc.model_id)
        full_prompt = f"{system}\n\n{prompt}" if system else prompt

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, lambda: model.generate_content(full_prompt))
        text = response.text

        tracker.log(agent, mc.model_id, "gemini", task_type.value, 0, 0, 0.0, prompt[:100])
        return {"response": text, "model": mc.name, "model_id": mc.model_id,
                "tokens": 0, "cost": 0.0, "provider": "gemini (free)"}


# Global router instance
router = NexusRouter()
