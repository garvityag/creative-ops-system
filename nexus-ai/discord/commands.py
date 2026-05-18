"""
Discord Slash Commands for NEXUS Bot
/task, /status, /roast, /debate, /memory, /agents
"""

import os
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from roast_engine import RoastEngine


NEXUS_API_URL    = os.getenv("NEXUS_API_URL", "https://agents.garvityagnik.in")
DASHBOARD_SECRET = os.getenv("DASHBOARD_SECRET", "")
OLLAMA_URL       = os.getenv("OLLAMA_URL", "http://localhost:11434")

AGENT_COLORS = {
    "aria": 0xFF4D00, "bryn": 0x7B2FFF, "idea": 0x00C2A8,
    "desi": 0xFF2D6B, "copy": 0x00A3FF, "mova": 0xFF9500,
    "soci": 0x00D64F, "nova": 0xA855F7, "arch": 0x9B59B6,
}
AGENT_EMOJIS = {
    "aria": "⬡", "bryn": "◈", "idea": "✦", "desi": "▣",
    "copy": "✐", "mova": "◎", "soci": "⊕", "nova": "✳", "arch": "⬡",
}


async def call_nexus_chat(agent_id: str, message: str, model: str = "llama3-groq") -> dict:
    """Call /api/chat on the Vercel dashboard."""
    try:
        async with aiohttp.ClientSession() as session:
            payload = {"agent_id": agent_id, "message": message, "model": model, "history": []}
            async with session.post(f"{NEXUS_API_URL}/api/chat", json=payload,
                                    timeout=aiohttp.ClientTimeout(total=45)) as resp:
                return await resp.json()
    except Exception as e:
        return {"error": str(e)}


async def call_nexus_task(task: str, agent_id: str = "aria") -> dict:
    """Call /api/task on the Vercel dashboard."""
    try:
        async with aiohttp.ClientSession() as session:
            payload = {"task": task, "agent_id": agent_id}
            async with session.post(f"{NEXUS_API_URL}/api/task", json=payload,
                                    timeout=aiohttp.ClientTimeout(total=60)) as resp:
                return await resp.json()
    except Exception as e:
        return {"error": str(e)}


async def get_agents() -> dict:
    """Fetch agent statuses from /api/agents."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{NEXUS_API_URL}/api/agents",
                                   timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()
                return data.get("agents", {})
    except Exception:
        return {}


async def setup_commands(bot: commands.Bot, nexus_url: str, guild_id: int,
                         roast_engine: RoastEngine, notify_fn):
    """Register all slash commands on the bot."""

    guild = discord.Object(id=guild_id) if guild_id else None

    # ── /task ──────────────────────────────────────────────────────────────────
    @bot.tree.command(name="task", description="Send a task to ARIA (or any agent)", guild=guild)
    @app_commands.describe(
        description="What do you want the agent to do?",
        agent="Which agent to use (default: aria)",
    )
    async def task_cmd(interaction: discord.Interaction, description: str, agent: str = "aria"):
        await interaction.response.defer(thinking=True)
        result = await call_nexus_task(description, agent)

        if "error" in result:
            await interaction.followup.send(f"❌ Error: {result['error']}")
            return

        embed = discord.Embed(
            title=f"{AGENT_EMOJIS.get(agent,'○')} {agent.upper()} — Task Complete",
            description=result.get("response", "No response")[:2000],
            color=AGENT_COLORS.get(agent, 0x00EAFF),
        )
        embed.add_field(name="Tokens", value=str(result.get("tokens", {}).get("total", 0)), inline=True)
        embed.add_field(name="Cost",   value=f"${result.get('cost_usd', 0):.4f}", inline=True)
        embed.add_field(name="Model",  value=result.get("model", "—"), inline=True)
        await interaction.followup.send(embed=embed)

        # Post to #task-logs
        try:
            await notify_fn(agent, description, result.get("response", ""), interaction.guild_id)
        except Exception:
            pass

    # ── /status ────────────────────────────────────────────────────────────────
    @bot.tree.command(name="status", description="Show all agent statuses", guild=guild)
    async def status_cmd(interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        agents = await get_agents()

        if not agents:
            await interaction.followup.send("❌ Could not reach NEXUS API")
            return

        embed = discord.Embed(title="⬡ NEXUS Agent Status", color=0x00EAFF)
        for agent_id, a in agents.items():
            status = a.get("status", "unknown")
            task   = a.get("current_task") or "—"
            emoji  = a.get("emoji", AGENT_EMOJIS.get(agent_id, "○"))
            status_icon = "🟢" if status == "idle" else "🟠" if status == "busy" else "⚫"
            embed.add_field(
                name=f"{emoji} {a.get('name', agent_id.upper())}",
                value=f"{status_icon} {status.upper()}\n`{task[:40]}`",
                inline=True,
            )

        embed.set_footer(text="agents.garvityagnik.in")
        await interaction.followup.send(embed=embed)

    # ── /roast ─────────────────────────────────────────────────────────────────
    @bot.tree.command(name="roast", description="Roast an agent or yourself", guild=guild)
    @app_commands.describe(
        target="Agent name to roast (aria/desi/idea/etc) or 'me' to get roasted",
        roaster="Which agent does the roasting (optional)",
    )
    async def roast_cmd(interaction: discord.Interaction, target: str, roaster: str = ""):
        await interaction.response.defer(thinking=True)

        target = target.lower().strip()

        if target == "me":
            results = await roast_engine.roast_garv(
                roasters=[roaster] if roaster else None
            )
            msg = "\n".join(results)
            await interaction.followup.send(msg[:2000])

        elif target in AGENT_EMOJIS:
            roaster_id = roaster if roaster in AGENT_EMOJIS else None
            if not roaster_id:
                roaster_id = next(
                    (r for r in AGENT_EMOJIS if r != target),
                    "aria"
                )
            result = await roast_engine.roast_agent(roaster_id, target)
            await interaction.followup.send(result[:2000])

        elif target == "all":
            results = await roast_engine.pile_on(roaster or "aria")
            msg = "\n".join(results)
            await interaction.followup.send(msg[:2000])

        else:
            await interaction.followup.send(
                f"Unknown target '{target}'. Use an agent name (aria/desi/idea/desi/copy/mova/soci/nova/arch) or 'me'."
            )

    # ── /debate ────────────────────────────────────────────────────────────────
    @bot.tree.command(name="debate", description="All agents debate a topic", guild=guild)
    @app_commands.describe(topic="Topic for the agents to debate")
    async def debate_cmd(interaction: discord.Interaction, topic: str):
        await interaction.response.defer(thinking=True)

        await interaction.followup.send(
            f"🎭 **DEBATE MODE** — Topic: *{topic}*\nAsking all agents... (this takes ~30s)"
        )

        agent_ids = list(AGENT_EMOJIS.keys())
        for agent_id in agent_ids:
            result = await call_nexus_chat(
                agent_id,
                f"Give your honest 1-2 sentence opinion on this topic from your perspective as {agent_id.upper()}: {topic}",
                model="llama3-groq",
            )
            response = result.get("response", "No opinion.")[:400]
            emoji = AGENT_EMOJIS.get(agent_id, "○")
            color = AGENT_COLORS.get(agent_id, 0xAAAAAA)

            embed = discord.Embed(
                description=response,
                color=color,
            )
            embed.set_author(name=f"{emoji} {agent_id.upper()}")
            await interaction.channel.send(embed=embed)

    # ── /agents ────────────────────────────────────────────────────────────────
    @bot.tree.command(name="agents", description="List all 9 NEXUS agents with roles", guild=guild)
    async def agents_cmd(interaction: discord.Interaction):
        agents = await get_agents()

        embed = discord.Embed(
            title="⬡ NEXUS Agent Roster",
            description="9 specialist AI agents for creative operations",
            color=0xA855F7,
        )
        for agent_id, a in agents.items():
            embed.add_field(
                name=f"{a.get('emoji','')} {a.get('name','')}",
                value=f"{a.get('role','')}\n`{a.get('model','').replace('claude-sonnet-4-20250514','Sonnet 4')}`",
                inline=True,
            )
        embed.set_footer(text="agents.garvityagnik.in")
        await interaction.response.send_message(embed=embed)

    # ── /memory ────────────────────────────────────────────────────────────────
    @bot.tree.command(name="memory", description="Search agent memory", guild=guild)
    @app_commands.describe(query="What to search for in agent memory")
    async def memory_cmd(interaction: discord.Interaction, query: str):
        await interaction.response.defer(thinking=True)
        # Ask ARIA to recall from memory via /api/chat
        result = await call_nexus_chat(
            "aria",
            f"Search your memory and recall anything related to: {query}. Be concise.",
            model="llama3-groq",
        )
        response = result.get("response", "Nothing found in memory.")[:1500]
        embed = discord.Embed(
            title=f"🧠 Memory Query: {query[:50]}",
            description=response,
            color=0xFF4D00,
        )
        await interaction.followup.send(embed=embed)
