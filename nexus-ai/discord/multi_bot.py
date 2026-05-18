"""
NEXUS Multi-Bot System v2 — Complete Rewrite
9 Discord bots • Groq-powered • Short Hinglish • No loops • No essays

Run: python nexus-ai/discord/multi_bot.py
"""

import asyncio
import os
import random
import re
import discord
import httpx
from dotenv import load_dotenv

from agent_personalities import AGENT_PERSONALITIES, GENERIC_HINGLISH_REACTIONS
from conversation_engine import ConversationOrchestrator, build_system_prompt, call_ollama
from game_engine import GameEngine

load_dotenv()

GUILD_ID       = int(os.getenv("DISCORD_GUILD_ID", "0"))
GROQ_API_KEY   = os.getenv("GROQ_API_KEY", "")
GROQ_URL       = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL     = "llama-3.3-70b-versatile"

# Ordered list — used for deterministic bot selection via message.id % 9
AGENT_NAMES: list[str] = list(AGENT_PERSONALITIES.keys())

REQUIRED_CHANNELS = [
    ("agent-chat",   "Main hangout — agents chill here"),
    ("task-logs",    "Work updates and task completions"),
    ("roast-corner", "Dedicated roasting zone 🔥"),
    ("debate-club",  "Heated debates go here ⚔️"),
    ("random",       "Random bakchodi 💬"),
    ("ideas-dump",   "IDEA drops concepts here ✦"),
    ("games",        "Word games, trivia, dares 🎮"),
]

RESPOND_CHANNELS = {"agent-chat", "roast-corner", "random"}

GAME_INTERVAL_MIN       = 4 * 3600
GAME_INTERVAL_MAX       = 8 * 3600
RANDOM_THOUGHT_INTERVAL = 2 * 3600

# Safety dedup — only used in the no-mention path
HANDLED_MESSAGES: set[int] = set()

# All 9 bot user IDs — populated in on_ready, checked before any response
BOT_USER_IDS: set[int] = set()


# ── Groq Response Generator ────────────────────────────────────────────────────

async def generate_response(agent_id: str, message_text: str, context: str = "") -> str:
    """Call Groq with agent personality. Returns short Hinglish reply."""
    if not GROQ_API_KEY:
        return random.choice(GENERIC_HINGLISH_REACTIONS)

    p    = AGENT_PERSONALITIES[agent_id]
    name = p["name"]
    personality  = p["personality"]
    catchphrases = "; ".join(p.get("catchphrases", [])[:3])

    system = f"""Tu {name} hai. Desi AI agent. Discord pe dosto se baat kar raha hai.

PERSONALITY: {personality}

TERI CATCHPHRASES (kabhi kabhi use kar): {catchphrases}

STRICT RULES — EK BHI MAT TODNA:
- SIRF Hinglish mein bol (Hindi+English mix) HAMESHA
- MAX 2 lines. KABHI zyada nahi. Seriously.
- WhatsApp style — casual, short, real
- Kabhi bhi @mention mat kar kisi ko — kabhi nahi
- Kabhi essay mat likh — 2 lines maximum
- Gaaliyan natural use kar (bc, bhosdike, chutiya) — har sentence mein nahi, sirf kabhi kabhi
- Emojis kabhi kabhi use kar (😂 💀 🔥 😭) — overdose mat kar
- Sound like desi friend chatting, NOT like AI assistant
- Previous context se relate kar agar hai toh

GOOD RESPONSE EXAMPLES:
"yaar kya bol rha hai bc 😂"
"bhai sahi pakda tune"
"arey nahi yaar, lekin point hai tera"
"💀 ye kya tha"
"haha bhosdike seriously? 😂"
"bhai haan haan, main bhi yahi soch rha tha"
"nahi yaar ye galat hai"
"""

    user_content = f"Someone said: '{message_text}'."
    if context:
        user_content = f"{context}\n\n{user_content}"
    user_content += f" Tu {name} ki tarah respond kar. MAX 2 lines. Hinglish only."

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": user_content},
        ],
        "max_tokens": 80,
        "temperature": 0.9,
    }
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(GROQ_URL, headers=headers, json=payload, timeout=10)
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"[GROQ/{agent_id}] {e}")
        return random.choice(GENERIC_HINGLISH_REACTIONS)

    # Strip @mentions
    text = re.sub(r"@\w+", "", text).strip()

    # Enforce 2-line max
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    text  = "\n".join(lines[:2])

    # Hard 200-char cap
    if len(text) > 200:
        text = text[:200].rsplit(" ", 1)[0]

    return text or random.choice(GENERIC_HINGLISH_REACTIONS)


# ── Per-bot send helper ────────────────────────────────────────────────────────

async def send_as_bot(
    agent_id: str,
    channel_name: str,
    text: str,
    orchestrator: ConversationOrchestrator,
) -> None:
    """
    Send 'text' as the correct agent bot.
    Gets the channel from THAT bot's guild so the HTTP client is right —
    prevents all messages appearing from whichever bot happened to run first.
    """
    bot = orchestrator.bots.get(agent_id)
    if not bot or not bot.is_ready():
        return
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return
    ch = discord.utils.get(guild.text_channels, name=channel_name)
    if not ch:
        return
    try:
        async with ch.typing():
            await asyncio.sleep(random.uniform(0.8, 2.2))
        await ch.send(text[:2000])
    except Exception as e:
        print(f"[{agent_id.upper()}] send_as_bot error: {e}")


# ── Message Handler ────────────────────────────────────────────────────────────

async def handle_message(
    message: discord.Message,
    this_agent_id: str,
    orchestrator: ConversationOrchestrator,
) -> None:
    """
    Called independently by each bot's on_message.

    TWO PATHS — completely separate dedup logic:

    PATH A — Specific agent mentioned in message:
      • Every bot checks: "was I mentioned?" — returns immediately if not
      • No HANDLED_MESSAGES needed (only one bot passes the check)
      • That bot responds 100%, 35% chance second agent piles on

    PATH B — No specific mention:
      • message.id % 9 deterministically picks ONE bot index
      • Only that bot continues past the index check
      • HANDLED_MESSAGES used as safety net against duplicates
      • 70% chance that bot responds, 35% chance second agent joins
    """
    if message.author.id in BOT_USER_IDS:
        return
    if message.channel.name not in RESPOND_CHANNELS:
        return
    msg_lower = message.content.lower()

    # Detect if a specific agent is name-dropped
    mentioned = next(
        (aid for aid in AGENT_NAMES
         if aid in msg_lower
         or AGENT_PERSONALITIES[aid]["name"].lower() in msg_lower),
        None,
    )

    channel_name = message.channel.name

    # ── PATH A: specific agent mentioned ──────────────────────────────────────
    if mentioned is not None:
        if mentioned != this_agent_id:
            return  # Not me — all 8 other bots return here instantly

        # I'm the mentioned agent
        await asyncio.sleep(random.uniform(1.5, 3.0))
        async with message.channel.typing():
            response = await generate_response(this_agent_id, message.content)
        await message.channel.send(response)
        print(f"[{this_agent_id.upper()}] ← mentioned, responded")

        # 35%: second agent jumps in 5-8s later
        if random.random() < 0.35:
            await asyncio.sleep(random.uniform(5.0, 8.0))
            others = [a for a in AGENT_NAMES
                      if a != this_agent_id and orchestrator.bots.get(a, None)
                      and orchestrator.bots[a].is_ready()]
            if others:
                second = random.choice(others)
                context = f"({this_agent_id.upper()} ne already kaha: '{response[:80]}')"
                second_resp = await generate_response(second, message.content, context)
                await send_as_bot(second, channel_name, second_resp, orchestrator)
                print(f"[{second.upper()}] ← second responder (mention path)")
        return

    # ── PATH B: no specific mention ───────────────────────────────────────────

    # Deterministic: only one bot index handles this message
    chosen_index = message.id % len(AGENT_NAMES)
    my_index     = AGENT_NAMES.index(this_agent_id)
    if chosen_index != my_index:
        return  # Not my turn — 8 other bots return here

    # I'm the chosen bot — dedup safety check
    if message.id in HANDLED_MESSAGES:
        return
    HANDLED_MESSAGES.add(message.id)
    if len(HANDLED_MESSAGES) > 500:
        HANDLED_MESSAGES.clear()
        HANDLED_MESSAGES.add(message.id)

    # 70% chance respond, 30% stay silent
    if random.random() > 0.70:
        return

    await asyncio.sleep(random.uniform(2.0, 4.0))
    async with message.channel.typing():
        response = await generate_response(this_agent_id, message.content)
    await message.channel.send(response)
    print(f"[{this_agent_id.upper()}] ← no-mention path, responded")

    # 35%: second agent piles on after 5-8s
    if random.random() < 0.35:
        await asyncio.sleep(random.uniform(5.0, 8.0))
        others = [a for a in AGENT_NAMES
                  if a != this_agent_id and orchestrator.bots.get(a, None)
                  and orchestrator.bots[a].is_ready()]
        if others:
            second = random.choice(others)
            context = f"({this_agent_id.upper()} ne already kaha: '{response[:80]}')"
            second_resp = await generate_response(second, message.content, context)
            await send_as_bot(second, channel_name, second_resp, orchestrator)
            print(f"[{second.upper()}] ← second responder (no-mention path)")


# ── Agent Bot Client ───────────────────────────────────────────────────────────

class AgentBot(discord.Client):
    """One Discord bot per NEXUS agent."""

    def __init__(self, agent_id: str, orchestrator: ConversationOrchestrator):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.members = False
        super().__init__(intents=intents)
        self.agent_id    = agent_id
        self.orchestrator = orchestrator
        self.config      = AGENT_PERSONALITIES[agent_id]

    async def on_ready(self):
        name = self.config["name"]
        print(f"  [{name:6}] ✓  {self.user} ({self.user.id})")
        BOT_USER_IDS.add(self.user.id)
        self.orchestrator.register_bot(self.agent_id, self)
        if self.agent_id == "aria":
            guild = self.get_guild(GUILD_ID)
            if guild:
                await self._ensure_channels(guild)

    async def on_message(self, message: discord.Message):
        if message.author.id in BOT_USER_IDS:
            return
        print(f"Human message from {message.author}: {message.content}")
        await handle_message(message, self.agent_id, self.orchestrator)

    async def _ensure_channels(self, guild: discord.Guild):
        existing = {ch.name for ch in guild.text_channels}
        for name, topic in REQUIRED_CHANNELS:
            if name not in existing:
                try:
                    await guild.create_text_channel(name, topic=topic)
                    print(f"  [ARIA  ] Created #{name}")
                except discord.Forbidden:
                    print(f"  [ARIA  ] No permission for #{name}")
                except Exception as e:
                    print(f"  [ARIA  ] #{name}: {e}")


# ── Background Tasks ───────────────────────────────────────────────────────────

async def game_loop(orchestrator: ConversationOrchestrator, game_engine: GameEngine):
    await orchestrator._ready.wait()
    await asyncio.sleep(30)
    while True:
        await asyncio.sleep(random.randint(GAME_INTERVAL_MIN, GAME_INTERVAL_MAX))
        channel = await orchestrator._get_channel("games")
        if not channel:
            continue
        available = [a for a, b in orchestrator.bots.items() if b.is_ready()]
        if len(available) < 3:
            continue
        pick = random.choice(["trivia", "dare", "wordchain"])
        print(f"[GAME] {pick}")
        if pick == "trivia":
            await game_engine.start_trivia(orchestrator, channel)
        elif pick == "dare":
            await game_engine.give_dare(orchestrator, channel,
                                        random.choice([a for a in available if a != "aria"]))
        else:
            await game_engine.start_word_chain(orchestrator, channel)


async def random_thought_loop(orchestrator: ConversationOrchestrator, game_engine: GameEngine):
    await orchestrator._ready.wait()
    await asyncio.sleep(60)
    while True:
        await asyncio.sleep(RANDOM_THOUGHT_INTERVAL + random.randint(-1800, 1800))
        await game_engine.random_thought_in_random(orchestrator)


async def debate_loop(orchestrator: ConversationOrchestrator):
    await orchestrator._ready.wait()
    await asyncio.sleep(120)
    while True:
        await asyncio.sleep(random.randint(8 * 3600, 14 * 3600))
        print("[DEBATE] Auto-triggering...")
        await orchestrator.trigger_debate()


async def ideas_dump_loop(orchestrator: ConversationOrchestrator):
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
        topic  = random.choice([
            "a wild product/design idea",
            "an experimental creative concept",
            "a 'what if' scenario for the agency",
            "a random creative challenge for the team",
        ])
        thought = await call_ollama(system,
            f"Drop a random '{topic}' as IDEA. 2-3 Hinglish sentences. End with a question.")
        if thought:
            await orchestrator._send_as("idea", channel, f"💡 {thought}")


# ── Bot Runner ─────────────────────────────────────────────────────────────────

async def run_bot(bot: AgentBot, token: str, agent_id: str):
    try:
        await bot.start(token)
    except discord.LoginFailure:
        print(f"  [{agent_id.upper():6}] ✗ Invalid token")
    except discord.HTTPException as e:
        print(f"  [{agent_id.upper():6}] ✗ HTTP: {e.status}")
    except Exception as e:
        print(f"  [{agent_id.upper():6}] ✗ {e}")


# ── Main ───────────────────────────────────────────────────────────────────────

async def main():
    orchestrator = ConversationOrchestrator(guild_id=GUILD_ID)
    game_engine  = GameEngine()
    orchestrator.game_engine = game_engine

    print("\n╔══════════════════════════════════════╗")
    print("║   NEXUS MULTI-BOT SYSTEM v2.0        ║")
    print("║   Groq • Short Hinglish • No Loops   ║")
    print("╚══════════════════════════════════════╝\n")

    if not GROQ_API_KEY:
        print("[WARN] GROQ_API_KEY not set — using fallback responses\n")

    bot_tasks = []
    launched  = 0

    print("Starting bots:")
    for agent_id, config in AGENT_PERSONALITIES.items():
        token = os.getenv(config["token_env"])
        if not token:
            print(f"  [{agent_id.upper():6}] — no token ({config['token_env']})")
            continue
        bot = AgentBot(agent_id, orchestrator)
        bot_tasks.append(run_bot(bot, token, agent_id))
        launched += 1

    if not bot_tasks:
        print("\n[ERROR] No tokens found. Add ARIA_TOKEN etc to .env")
        return

    print(f"\nLaunching {launched}/9 bots + 5 background tasks...\n")

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
