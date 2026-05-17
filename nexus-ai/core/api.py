"""
NEXUS — FastAPI Server
Connects everything: orchestrator, memory, usage tracking.
Dashboard reads from here. Claude web/app can hit these endpoints.
"""

import asyncio
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from core.orchestrator import aria
from core.memory import memory
from core.router import tracker
from config.models import MODELS, TaskType


app = FastAPI(title="NEXUS AI API", version="1.0.0")

# Allow dashboard + Claude to connect
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── REQUEST MODELS ────────────────────────────────────────────

class TaskRequest(BaseModel):
    task: str
    context: str = ""
    auto_execute: bool = False


class ApproveRequest(BaseModel):
    task_id: str


class StatusUpdateRequest(BaseModel):
    secret: str
    agent_id: str
    updates: dict


# ── ROUTES ────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {
        "system": "NEXUS AI",
        "version": "1.0.0",
        "status": "online",
        "phase": "1 — Core Engine",
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/status")
async def get_status():
    """Main status endpoint — dashboard reads this."""
    stats = tracker.get_agent_stats()
    mem_stats = memory.get_stats()
    recent = tracker.get_recent(10)

    # Build agent status from recent activity
    agent_status = {}
    for s in stats:
        agent_status[s["agent"]] = {
            "tasks": s["tasks"],
            "tokens": s["tokens"],
            "cost": round(s["cost"], 4),
            "model": s["model"],
        }

    return {
        "system": {
            "online": True,
            "phase": 1,
            "timestamp": datetime.now().isoformat(),
        },
        "usage": {
            "daily_cost_usd": round(tracker.get_daily_cost(), 4),
            "monthly_cost_usd": round(tracker.get_monthly_cost(), 4),
            "recent_tasks": recent,
        },
        "memory": mem_stats,
        "agents": agent_status,
        "active_tasks": aria.get_active_tasks(),
        "models_available": {
            k: {
                "name": v.name,
                "provider": v.provider.value,
                "cost_per_1k": v.cost_per_1k_tokens,
                "local": v.local,
                "available": v.available,
            }
            for k, v in MODELS.items()
        },
    }


@app.post("/task")
async def create_task(req: TaskRequest):
    """Submit a task to ARIA."""
    plan = await aria.process(req.task, req.context, req.auto_execute)
    return plan


@app.post("/approve")
async def approve_task(req: ApproveRequest):
    """Approve a paused pipeline step."""
    result = aria.approve_step(req.task_id)
    return result


@app.get("/tasks")
async def get_tasks():
    """Get all active tasks."""
    return {"tasks": aria.get_active_tasks()}


@app.get("/usage")
async def get_usage():
    """Token usage + cost tracking for dashboard."""
    return {
        "daily_usd": round(tracker.get_daily_cost(), 4),
        "monthly_usd": round(tracker.get_monthly_cost(), 4),
        "by_agent": tracker.get_agent_stats(),
        "recent": tracker.get_recent(20),
    }


@app.get("/memory/search")
async def search_memory(q: str, collection: str = "projects"):
    """Search agent memory."""
    results = memory.recall(q, collection)
    return {"query": q, "results": results}


@app.get("/memory/stats")
async def memory_stats():
    """Memory collection stats."""
    return memory.get_stats()


@app.post("/agent/update")
async def update_agent(req: StatusUpdateRequest):
    """Update agent status (from dashboard quick-update)."""
    import os
    secret = os.getenv("DASHBOARD_SECRET", "nexus-garv-2026")
    if req.secret != secret:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return {"success": True, "agent": req.agent_id, "updates": req.updates}


@app.get("/models")
async def get_models():
    """All available models + their status."""
    return {
        k: {
            "name": v.name,
            "provider": v.provider.value,
            "cost_per_1k_usd": v.cost_per_1k_tokens,
            "local": v.local,
            "available": v.available,
            "best_for": [t.value for t in v.best_for],
        }
        for k, v in MODELS.items()
    }


# ── RUN ───────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run("core.api:app", host="0.0.0.0", port=8000, reload=True)
