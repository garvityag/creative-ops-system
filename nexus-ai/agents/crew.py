"""
crew.py — CrewAI full pipeline
Runs the complete brief → concept → design → copy → social pipeline.
Updates Vercel KV at each step so the dashboard shows live progress.
"""

import asyncio
import os
import httpx
from datetime import datetime

from .bryn import BrynAgent
from .idea import IdeaAgent
from .desi import DesiAgent
from .copy import CopyAgent
from .mova import MovaAgent
from .soci import SociAgent
from .nova import NovaAgent
from .arch import ArchAgent

DASHBOARD_URL = os.getenv("DASHBOARD_URL", "https://agents.garvityagnik.in")
DASHBOARD_SECRET = os.getenv("DASHBOARD_SECRET", "")


async def _api(path: str, payload: dict):
    """POST to dashboard API — non-blocking, swallows errors."""
    if not DASHBOARD_SECRET:
        return
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            await client.post(f"{DASHBOARD_URL}{path}", json={**payload, "secret": DASHBOARD_SECRET})
    except Exception:
        pass


async def start_pipeline(project_name: str, template: str = "full"):
    """Signal dashboard to start the pipeline visualization."""
    await _api("/api/pipeline", {"action": "start", "project_name": project_name, "template": template})


async def advance_pipeline(summary: str = ""):
    """Mark current step done, move to next."""
    await _api("/api/pipeline", {"action": "step", "output_summary": summary})


async def complete_pipeline():
    await _api("/api/pipeline", {"action": "complete"})


# ── Individual pipeline steps ─────────────────────────────────────────────────

async def run_brief(raw_input: str, project: str) -> dict:
    agent = BrynAgent()
    result = await agent.analyze_brief(raw_input, project=project)
    await advance_pipeline(f"Brief ready: {project}")
    return result


async def run_idea(brief_output: dict, project: str) -> dict:
    agent = IdeaAgent()
    brief_data = brief_output.get("output", brief_output.get("response", ""))
    result = await agent.generate_directions(brief_data, project=project)
    await advance_pipeline("3 creative directions generated")
    return result


async def run_desi_and_copy(idea_output: dict, brief_output: dict, project: str):
    """Run DESI and COPY in parallel — they don't depend on each other."""
    brief_data = brief_output.get("output", brief_output.get("response", ""))
    idea_data = idea_output.get("output", idea_output.get("response", ""))

    desi_agent = DesiAgent()
    copy_agent = CopyAgent()

    desi_task = desi_agent.build_production_plan(idea_data, brief_data, project=project)
    copy_task = copy_agent.write_copy(brief_data, idea_data, project=project)

    desi_result, copy_result = await asyncio.gather(desi_task, copy_task)
    await advance_pipeline("Design plan + copy ready")
    return desi_result, copy_result


async def run_mova(desi_output: dict, idea_output: dict, project: str) -> dict:
    agent = MovaAgent()
    desi_data = desi_output.get("output", desi_output.get("response", ""))
    idea_data = idea_output.get("output", idea_output.get("response", ""))
    result = await agent.build_motion_plan(desi_data, idea_data, project=project)
    await advance_pipeline("Motion plan ready")
    return result


async def run_soci(desi_output: dict, copy_output: dict, project: str) -> dict:
    agent = SociAgent()
    desi_data = desi_output.get("output", desi_output.get("response", ""))
    copy_data = copy_output.get("output", copy_output.get("response", ""))
    result = await agent.build_calendar(desi_data, copy_data, project=project)
    await advance_pipeline("Social calendar ready")
    return result


# ── Main crew runner ──────────────────────────────────────────────────────────

async def run_crew(raw_brief: str, project_name: str = "Untitled", pipeline: str = "full") -> dict:
    """
    Full pipeline: brief → concept → design+copy (parallel) → motion → social
    Updates dashboard at each step.

    Args:
        raw_brief:    The raw client brief or task description
        project_name: Human-readable project name for dashboard
        pipeline:     'full' | 'design' | 'content' | 'motion' | 'social'

    Returns:
        dict with all agent outputs keyed by agent_id
    """
    print(f"\n{'='*60}")
    print(f"  NEXUS CREW — Starting pipeline: {pipeline}")
    print(f"  Project: {project_name}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    await start_pipeline(project_name, pipeline)

    outputs = {}
    total_tokens = 0
    total_cost = 0.0

    try:
        # STEP 1 — BRYN: Brief analysis (all pipelines)
        print("[1/5] BRYN — Analyzing brief...")
        outputs["bryn"] = await run_brief(raw_brief, project_name)
        total_tokens += outputs["bryn"].get("tokens", 0)
        total_cost   += outputs["bryn"].get("cost", 0.0)

        if pipeline == "content":
            # Content-only: COPY → SOCI
            print("[2/3] COPY — Writing content...")
            copy_agent = CopyAgent()
            outputs["copy"] = await copy_agent.write_copy(
                outputs["bryn"].get("output", outputs["bryn"].get("response", "")),
                project=project_name,
            )
            await advance_pipeline("Copy ready")
            total_tokens += outputs["copy"].get("tokens", 0)
            total_cost   += outputs["copy"].get("cost", 0.0)

            print("[3/3] SOCI — Building calendar...")
            outputs["soci"] = await run_soci(outputs["copy"], outputs["copy"], project_name)
            total_tokens += outputs["soci"].get("tokens", 0)
            total_cost   += outputs["soci"].get("cost", 0.0)

        elif pipeline == "social":
            # Social only: COPY → SOCI (no design)
            print("[2/2] COPY + SOCI — Writing and scheduling...")
            copy_agent = CopyAgent()
            outputs["copy"] = await copy_agent.write_copy(
                outputs["bryn"].get("output", ""),
                project=project_name,
            )
            await advance_pipeline("Copy ready")
            outputs["soci"] = await run_soci(outputs["copy"], outputs["copy"], project_name)
            total_tokens += outputs["copy"].get("tokens", 0) + outputs["soci"].get("tokens", 0)
            total_cost   += outputs["copy"].get("cost", 0.0)  + outputs["soci"].get("cost", 0.0)

        else:
            # STEP 2 — IDEA: Creative directions
            print("[2/5] IDEA — Generating directions...")
            outputs["idea"] = await run_idea(outputs["bryn"], project_name)
            total_tokens += outputs["idea"].get("tokens", 0)
            total_cost   += outputs["idea"].get("cost", 0.0)

            # STEP 3 — DESI + COPY (parallel)
            print("[3/5] DESI + COPY — Design plan and copy (parallel)...")
            outputs["desi"], outputs["copy"] = await run_desi_and_copy(
                outputs["idea"], outputs["bryn"], project_name
            )
            for key in ("desi", "copy"):
                total_tokens += outputs[key].get("tokens", 0)
                total_cost   += outputs[key].get("cost", 0.0)

            if pipeline in ("full", "motion"):
                # STEP 4 — MOVA: Motion plan
                print("[4/5] MOVA — Building motion plan...")
                outputs["mova"] = await run_mova(outputs["desi"], outputs["idea"], project_name)
                total_tokens += outputs["mova"].get("tokens", 0)
                total_cost   += outputs["mova"].get("cost", 0.0)

            if pipeline in ("full",):
                # STEP 5 — SOCI: Content calendar
                print("[5/5] SOCI — Building content calendar...")
                outputs["soci"] = await run_soci(outputs["desi"], outputs["copy"], project_name)
                total_tokens += outputs["soci"].get("tokens", 0)
                total_cost   += outputs["soci"].get("cost", 0.0)

        await complete_pipeline()

        print(f"\n{'='*60}")
        print(f"  PIPELINE COMPLETE")
        print(f"  Total tokens: {total_tokens:,}  |  Total cost: ${total_cost:.4f}")
        print(f"  Agents run: {', '.join(outputs.keys())}")
        print(f"{'='*60}\n")

        return {
            "success":      True,
            "project":      project_name,
            "pipeline":     pipeline,
            "agents_run":   list(outputs.keys()),
            "outputs":      outputs,
            "total_tokens": total_tokens,
            "total_cost":   total_cost,
        }

    except Exception as e:
        print(f"\n[CREW ERROR] {e}")
        return {
            "success":    False,
            "project":    project_name,
            "error":      str(e),
            "outputs":    outputs,
        }


# ── CLI entry ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    brief = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Create a brand identity for a fintech startup targeting Gen Z"
    asyncio.run(run_crew(brief, project_name="Test Run", pipeline="design"))
