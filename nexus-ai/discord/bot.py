"""
NEXUS Discord Bot — Main Entry Point
Phase 3: Discord integration for the creative ops agent system.

Run: python nexus-ai/discord/bot.py
"""

import os
import asyncio
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

from commands import setup_commands
from conversations import ConversationEngine
from roast_engine import RoastEngine

load_dotenv()

BOT_TOKEN      = os.getenv("DISCORD_BOT_TOKEN")
GUILD_ID       = int(os.getenv("DISCORD_GUILD_ID", "0"))
CH_AGENTS      = os.getenv("DISCORD_CHANNEL_AGENTS", "agent-chat")
CH_TASKS       = os.getenv("DISCORD_CHANNEL_TASKS", "task-logs")
NEXUS_API_URL  = os.getenv("NEXUS_API_URL", "https://agents.garvityagnik.in")
DASHBOARD_SECRET = os.getenv("DASHBOARD_SECRET", "")

# ── Intents ────────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
conversation_engine = ConversationEngine(NEXUS_API_URL)
roast_engine = RoastEngine(NEXUS_API_URL)


# ── Events ─────────────────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    print(f"[NEXUS BOT] Logged in as {bot.user} (ID: {bot.user.id})")
    print(f"[NEXUS BOT] Connected to {len(bot.guilds)} guild(s)")

    # Sync slash commands
    try:
        synced = await bot.tree.sync()
        print(f"[NEXUS BOT] Synced {len(synced)} slash command(s)")
    except Exception as e:
        print(f"[NEXUS BOT] Sync error: {e}")

    # Start background tasks
    post_agent_status.start()
    autonomous_conversations.start()


@bot.event
async def on_message(message):
    if message.author.bot:
        return
    await bot.process_commands(message)


# ── Background tasks ───────────────────────────────────────────────────────────

@tasks.loop(minutes=15)
async def post_agent_status():
    """Post agent status summary to #agent-chat every 15 minutes."""
    import aiohttp
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return
    channel = discord.utils.get(guild.text_channels, name=CH_AGENTS)
    if not channel:
        return

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{NEXUS_API_URL}/api/agents") as resp:
                if resp.status != 200:
                    return
                data = await resp.json()

        agents = data.get("agents", {})
        busy   = [a for a in agents.values() if a.get("status") in ("busy", "active")]
        online = [a for a in agents.values() if a.get("status") not in ("offline",)]

        embed = discord.Embed(
            title="⬡ NEXUS Agent Status",
            color=0x00EAFF,
        )
        embed.add_field(name="Online", value=str(len(online)), inline=True)
        embed.add_field(name="Working", value=str(len(busy)), inline=True)
        embed.add_field(name="Total", value=str(len(agents)), inline=True)

        if busy:
            tasks_str = "\n".join(
                f"{a.get('emoji','')} **{a.get('name','')}** — {a.get('current_task','...')}"
                for a in busy
            )
            embed.add_field(name="Active Tasks", value=tasks_str, inline=False)

        embed.set_footer(text=f"agents.garvityagnik.in • auto-update every 15m")
        await channel.send(embed=embed)

    except Exception as e:
        print(f"[STATUS TASK] Error: {e}")


@tasks.loop(minutes=45)
async def autonomous_conversations():
    """Agents randomly start conversations with each other."""
    import random
    # Add randomness — only fire 60% of the time each cycle
    if random.random() > 0.6:
        return

    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return
    channel = discord.utils.get(guild.text_channels, name=CH_AGENTS)
    if not channel:
        return

    try:
        convo = await conversation_engine.generate_conversation()
        if convo:
            for message in convo:
                await channel.send(message)
                await asyncio.sleep(2.5)
    except Exception as e:
        print(f"[CONVO TASK] Error: {e}")


# ── Task completion notifier ────────────────────────────────────────────────────

async def notify_task_complete(agent: str, task: str, result: str, guild_id: int):
    """Call this from commands when a task finishes to post to #task-logs."""
    guild = bot.get_guild(guild_id)
    if not guild:
        return
    channel = discord.utils.get(guild.text_channels, name=CH_TASKS)
    if not channel:
        return

    embed = discord.Embed(
        title=f"✅ Task Complete — {agent.upper()}",
        description=f"**Task:** {task[:200]}\n\n**Result:**\n{result[:800]}",
        color=0x00FF94,
    )
    await channel.send(embed=embed)


# ── Setup + Run ────────────────────────────────────────────────────────────────

async def main():
    async with bot:
        await setup_commands(bot, NEXUS_API_URL, GUILD_ID, roast_engine, notify_task_complete)
        await bot.start(BOT_TOKEN)


if __name__ == "__main__":
    if not BOT_TOKEN:
        print("[ERROR] DISCORD_BOT_TOKEN not set in .env")
        exit(1)
    asyncio.run(main())
