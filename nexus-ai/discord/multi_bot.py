"""
NEXUS Multi-Bot System
9 Discord bots running simultaneously — one per agent
Each bot has its own token, personality, and voice.

Run: python nexus-ai/discord/multi_bot.py
"""

import asyncio
import os
import random
import discord
from dotenv import load_dotenv

from agent_personalities import AGENT_PERSONALITIES
from conversation_engine import ConversationOrchestrator, build_system_prompt, call_ollama
from game_engine import GameEngine

load_dotenv()

GUILD_ID = int(os.getenv("DISCORD_GUILD_ID", "0"))

REQUIRED_CHANNELS = [
    ("agent-chat",   "Main hangout — agents chill here"),
    ("task-logs",    "Work updates and task completions"),
    ("roast-corner", "Dedicated roasting zone 🔥"),
    ("debate-club",  "Heated debates go here ⚔️"),
    ("random",       "Random bakchodi 💬"),
    ("ideas-dump",   "IDEA drops concepts here ✦"),
    ("games",        "Word games, trivia, dares 🎮"),
]

# How often to run game events (seconds)
GAME_INTERVAL_MIN = 4 * 3600   # 4 hours
GAME_INTERVAL_MAX = 8 * 3600   # 8 hours
RANDOM_THOUGHT_INTERVAL = 2 * 3600  # every 2 hours


# ── Agent Bot Client ───────────────────────────────────────────────────────────

class AgentBot(discord.Client):
    """One Discord bot per NEXUS agent."""

    def __init__(self, agent_id: str, orchestrator: ConversationOrchestrator):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.members = False  # Don't need member events
        super().__init__(intents=intents)
        self.agent_id = agent_id
        self.orchestrator = orchestrator
        self.config = AGENT_PERSONALITIES[agent_id]

    async def on_ready(self):
        name = self.config["name"]
        print(f"  [{name:6}] ✓ Online as {self.user} ({self.user.id})")
        self.orchestrator.register_bot(self.agent_id, self)

        # ARIA sets up channels on first ready
        if self.agent_id == "aria":
            guild = self.get_guild(GUILD_ID)
            if guild:
                await self._ensure_channels(guild)
                print(f"  [ARIA  ] Channels checked for '{guild.name}'")

    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        # Respond when directly mentioned by a human
        if self.user and self.user.mentioned_in(message):
            await self.orchestrator.handle_human_mention(self.agent_id, message)

    async def _ensure_channels(self, guild: discord.Guild):
        existing = {ch.name for ch in guild.text_channels}
        for name, topic in REQUIRED_CHANNELS:
            if name not in existing:
                try:
                    await guild.create_text_channel(name, topic=topic)
                    print(f"  [SETUP] Created #{name}")
                except discord.Forbidden:
                    print(f"  [SETUP] No permission to create #{name}")
                except Exception as e:
                    print(f"  [SETUP] #{name} error: {e}")


# ── Background tasks ───────────────────────────────────────────────────────────

async def game_loop(orchestrator: ConversationOrchestrator, game_engine: GameEngine):
    """Periodically trigger games in #games channel."""
    await orchestrator._ready.wait()
    await asyncio.sleep(30)  # Let things settle

    while True:
        delay = random.randint(GAME_INTERVAL_MIN, GAME_INTERVAL_MAX)
        await asyncio.sleep(delay)

        channel = await orchestrator._get_channel("games")
        if not channel:
            continue

        available = [a for a, b in orchestrator.bots.items() if b.is_ready()]
        if len(available) < 3:
            continue

        game_choice = random.choice(["trivia", "dare", "wordchain"])
        print(f"[GAME] Starting: {game_choice}")

        if game_choice == "trivia":
            await game_engine.start_trivia(orchestrator, channel)
        elif game_choice == "dare":
            target = random.choice([a for a in available if a != "aria"])
            await game_engine.give_dare(orchestrator, channel, target)
        elif game_choice == "wordchain":
            await game_engine.start_word_chain(orchestrator, channel)


async def random_thought_loop(orchestrator: ConversationOrchestrator, game_engine: GameEngine):
    """Drop random agent thoughts in #random periodically."""
    await orchestrator._ready.wait()
    await asyncio.sleep(60)

    while True:
        await asyncio.sleep(RANDOM_THOUGHT_INTERVAL + random.randint(-1800, 1800))
        await game_engine.random_thought_in_random(orchestrator)


async def debate_loop(orchestrator: ConversationOrchestrator):
    """Trigger auto debates in #debate-club a few times per week."""
    await orchestrator._ready.wait()
    await asyncio.sleep(120)

    while True:
        # ~2 debates per day
        await asyncio.sleep(random.randint(8 * 3600, 14 * 3600))
        print("[DEBATE] Auto-triggering debate...")
        await orchestrator.trigger_debate()


async def ideas_dump_loop(orchestrator: ConversationOrchestrator):
    """IDEA randomly dumps concepts in #ideas-dump."""
    await orchestrator._ready.wait()
    await asyncio.sleep(90)

    while True:
        await asyncio.sleep(random.randint(3 * 3600, 7 * 3600))

        if "idea" not in orchestrator.bots or not orchestrator.bots["idea"].is_ready():
            continue

        channel = await orchestrator._get_channel("ideas-dump")
        if not channel:
            continue

        system = build_system_prompt("idea")
        topic = random.choice([
            "a wild product/design idea",
            "an experimental creative concept",
            "a 'what if' scenario for the agency",
            "a random creative challenge for the team",
        ])
        prompt = (
            f"Drop a random '{topic}' as IDEA. Be enthusiastic and chaotic. "
            f"2-3 sentences. Hinglish. End with a question to get others' thoughts."
        )
        thought = await call_ollama(system, prompt)
        if thought:
            await orchestrator._send_as("idea", channel, f"💡 {thought}")
            print("[IDEAS] IDEA dumped a concept")


# ── Bot runner ─────────────────────────────────────────────────────────────────

async def run_bot(bot: AgentBot, token: str, agent_id: str):
    """Start a single bot with error handling."""
    try:
        await bot.start(token)
    except discord.LoginFailure:
        print(f"  [{agent_id.upper():6}] ✗ Invalid token — skipped")
    except discord.HTTPException as e:
        print(f"  [{agent_id.upper():6}] ✗ HTTP error: {e}")
    except Exception as e:
        print(f"  [{agent_id.upper():6}] ✗ Error: {e}")


# ── Main ───────────────────────────────────────────────────────────────────────

async def main():
    orchestrator = ConversationOrchestrator(guild_id=GUILD_ID)
    game_engine = GameEngine()
    orchestrator.game_engine = game_engine

    bot_tasks = []
    launched = 0

    print("\n╔══════════════════════════════════════╗")
    print("║     NEXUS MULTI-BOT SYSTEM v1.0      ║")
    print("╚══════════════════════════════════════╝\n")
    print("Starting bots:")

    for agent_id, config in AGENT_PERSONALITIES.items():
        token = os.getenv(config["token_env"])
        if not token:
            print(f"  [{agent_id.upper():6}] — no token ({config['token_env']} not set)")
            continue
        bot = AgentBot(agent_id, orchestrator)
        bot_tasks.append(run_bot(bot, token, agent_id))
        launched += 1

    if not bot_tasks:
        print("\n[ERROR] No bot tokens found in .env")
        print("Add ARIA_TOKEN, DESI_TOKEN etc to nexus-ai/.env")
        return

    print(f"\nLaunching {launched}/9 bots + orchestrator...\n")

    await asyncio.gather(
        *bot_tasks,
        orchestrator.run(),
        game_loop(orchestrator, game_engine),
        random_thought_loop(orchestrator, game_engine),
        debate_loop(orchestrator),
        ideas_dump_loop(orchestrator),
        return_exceptions=True,
    )


if __name__ == "__main__":
    if not GUILD_ID:
        print("[ERROR] DISCORD_GUILD_ID not set in .env")
        exit(1)
    asyncio.run(main())
