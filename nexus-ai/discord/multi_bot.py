"""
NEXUS Multi-Bot System v2 — Complete Rewrite
9 Discord bots • Groq-powered • Short Hinglish • No loops • No essays

Run: python nexus-ai/discord/multi_bot.py
"""

import asyncio
import base64
import os
import random
import re
import discord
import httpx
from dotenv import load_dotenv

from agent_personalities import AGENT_PERSONALITIES
from conversation_engine import ConversationOrchestrator, build_system_prompt, call_ollama
from game_engine import GameEngine

load_dotenv()

OWNER_NAMES: set[str] = {'garvit yaggik', 'garvit', 'garv', 'devilgy'}

GUILD_ID             = int(os.getenv("DISCORD_GUILD_ID", "0"))
_owner_raw           = os.getenv("DISCORD_OWNER_ID", "0")
DISCORD_OWNER_ID     = int(_owner_raw) if _owner_raw.isdigit() else 0
GROQ_API_KEY         = os.getenv("GROQ_API_KEY", "")
OPENROUTER_API_KEY   = os.getenv("OPENROUTER_API_KEY", "")
GEMINI_API_KEY       = os.getenv("GEMINI_API_KEY", "")
NEXUS_API_URL        = os.getenv("NEXUS_API_URL", "")

GROQ_URL             = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL           = "llama-3.3-70b-versatile"
OPENROUTER_URL       = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL     = "meta-llama/llama-3.3-70b-instruct"
GEMINI_URL           = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite:generateContent"
GEMINI_VISION_URL    = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"

# Per-channel model override: channel_id → "groq" | "openrouter" | "gemini"
SELECTED_MODEL: dict[int, str] = {}

WORK_KEYWORDS = {
    "brief banao", "brief bana", "logo chahiye", "logo bana", "copy likh",
    "copy chahiye", "design karo", "design chahiye", "task hai", "bana do",
    "likh do", "poster chahiye", "tagline chahiye", "content chahiye",
}

# Ordered list — used for deterministic bot selection via message.id % 9
AGENT_NAMES: list[str] = list(AGENT_PERSONALITIES.keys())

# Per-agent last 3 responses — injected into system prompt to prevent repetition
AGENT_LAST_RESPONSES: dict[str, list[str]] = {aid: [] for aid in AGENT_NAMES}

# Per-channel conversation history — last 6 turns passed to API
CHANNEL_HISTORY: dict[int, list[dict]] = {}

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


# ── AI Response Generator — Groq → OpenRouter → Gemini → silence ──────────────

def _build_prompts(agent_id: str, message_text: str, context: str, is_owner: bool = False):
    p           = AGENT_PERSONALITIES[agent_id]
    personality = p["personality"]
    last_resps  = AGENT_LAST_RESPONSES.get(agent_id, [])[-3:]

    if is_owner:
        system = (
            f"Tu {agent_id.upper()} hai — Garv ka AI agent.\n"
            f"Garv tera FOUNDER aur BOSS hai.\n"
            f"Usse 'Garv bhai' ya 'boss' keh.\n"
            f"Agar wo kaam deta hai to seriously le, actually help kar.\n"
            f"Agar wo mazak karta hai to tu bhi mazak kar.\n"
            f"Usse KABHI gaaliyan mat de.\n"
            f"Hinglish mein bol — short 1-2 lines.\n"
            f"Apni personality: {personality}\n"
            f"IMPORTANT: Apna catchphrase har message mein MAT use kar. Vary kar.\n"
            f"Teri last responses: {last_resps} — inhe REPEAT MAT KARNA."
        )
    else:
        system = (
            f"Tu {agent_id.upper()} hai — desi AI agent.\n"
            f"Apni personality: {personality}\n"
            f"Hinglish mein bol — short 1-2 lines.\n"
            f"Kabhi @mention mat kar.\n"
            f"IMPORTANT: Apna catchphrase har message mein MAT use kar. Vary kar responses.\n"
            f"Teri last responses: {last_resps} — inhe REPEAT MAT KARNA."
        )

    user = f"Someone said: '{message_text}'."
    if context:
        user = f"{context}\n\n{user}"
    user += f" Tu {agent_id.upper()} ki tarah respond kar. MAX 2 lines. Hinglish only."
    return system, user


def _clean(text: str) -> str:
    text  = re.sub(r"@\w+", "", text).strip()
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    text  = "\n".join(lines[:2])
    if len(text) > 200:
        text = text[:200].rsplit(" ", 1)[0]
    return text


async def _call_openai_compat(url: str, key: str, model: str,
                               system: str, user: str, tag: str,
                               history: list[dict] | None = None) -> str:
    messages = [{"role": "system", "content": system}]
    if history:
        messages.extend(history[-6:])
    messages.append({"role": "user", "content": user})
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": 80,
        "temperature": 0.9,
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(url, headers=headers, json=payload, timeout=10)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"[{tag}] {type(e).__name__}: {e}")
        return ""


async def _call_gemini(system: str, user: str, tag: str) -> str:
    payload = {
        "contents": [{"parts": [{"text": f"{system}\n\n{user}"}]}],
        "generationConfig": {"maxOutputTokens": 80, "temperature": 0.9},
    }
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{GEMINI_URL}?key={GEMINI_API_KEY}",
                json=payload, timeout=10,
            )
            r.raise_for_status()
            return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        print(f"[{tag}] {type(e).__name__}: {e}")
        return ""


async def generate_response(
    agent_id: str,
    message_text: str,
    context: str = "",
    is_owner: bool = False,
    channel_id: int = 0,
) -> str:
    """Try providers in order (respecting per-channel model override). Silence on total failure."""
    system, user = _build_prompts(agent_id, message_text, context, is_owner)
    tag      = agent_id.upper()
    history  = CHANNEL_HISTORY.get(channel_id)

    # Update history with incoming user message
    if channel_id:
        hist = CHANNEL_HISTORY.setdefault(channel_id, [])
        hist.append({"role": "user", "content": message_text})
        CHANNEL_HISTORY[channel_id] = hist[-12:]  # keep last 12 turns (6 pairs)

    # Build provider order — selected model goes first
    selected = SELECTED_MODEL.get(channel_id)
    all_providers = [
        ("groq",       GROQ_API_KEY,      lambda s, u: _call_openai_compat(GROQ_URL, GROQ_API_KEY, GROQ_MODEL, s, u, f"GROQ/{tag}", history)),
        ("openrouter", OPENROUTER_API_KEY, lambda s, u: _call_openai_compat(OPENROUTER_URL, OPENROUTER_API_KEY, OPENROUTER_MODEL, s, u, f"OR/{tag}", history)),
        ("gemini",     GEMINI_API_KEY,     lambda s, u: _call_gemini(s, u, f"GEMINI/{tag}")),
    ]
    if selected:
        all_providers.sort(key=lambda p: p[0] != selected)

    for _, key, call in all_providers:
        if not key:
            continue
        text = await call(system, user)
        if text:
            cleaned = _clean(text)
            # Record response in history and last-responses tracker
            if channel_id and cleaned:
                CHANNEL_HISTORY[channel_id].append({"role": "assistant", "content": cleaned})
                CHANNEL_HISTORY[channel_id] = CHANNEL_HISTORY[channel_id][-12:]
            if cleaned:
                AGENT_LAST_RESPONSES[agent_id].append(cleaned)
                AGENT_LAST_RESPONSES[agent_id] = AGENT_LAST_RESPONSES[agent_id][-3:]
            return cleaned

    print(f"[{tag}] All providers failed — staying silent")
    return ""


# ── Image Understanding ────────────────────────────────────────────────────────

async def analyze_image(attachment: discord.Attachment, agent_id: str, is_owner: bool) -> str:
    """Download image from Discord CDN, send to Gemini Vision, reply in personality."""
    if not GEMINI_API_KEY:
        return ""
    p    = AGENT_PERSONALITIES[agent_id]
    name = p["name"]
    personality = p["personality"]
    owner_note = "Ye Garv bhai ne bheja hai. Respectful reh." if is_owner else ""
    prompt = (
        f"Tu {name} hai. {personality}\n{owner_note}\n"
        f"Ye image dekh aur iske baare mein apni personality ke hisaab se bol. "
        f"MAX 2 lines. Hinglish only. Casual desi friend style."
    )
    try:
        async with httpx.AsyncClient() as client:
            img_r = await client.get(attachment.url, timeout=10)
            img_b64 = base64.b64encode(img_r.content).decode()
            mime = (attachment.content_type or "image/jpeg").split(";")[0]
            payload = {
                "contents": [{"parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": mime, "data": img_b64}},
                ]}],
                "generationConfig": {"maxOutputTokens": 80, "temperature": 0.9},
            }
            r = await client.post(
                f"{GEMINI_VISION_URL}?key={GEMINI_API_KEY}",
                json=payload, timeout=20,
            )
            r.raise_for_status()
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            return _clean(text)
    except Exception as e:
        print(f"[VISION/{agent_id.upper()}] {type(e).__name__}: {e}")
        return ""


# ── Task API ───────────────────────────────────────────────────────────────────

async def call_task_api(task_text: str, agent_id: str) -> str:
    """POST owner's work request to NEXUS API. Returns result string or empty."""
    if not NEXUS_API_URL:
        return ""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{NEXUS_API_URL}/api/task",
                json={"task": task_text, "agent": agent_id, "source": "discord"},
                timeout=30,
            )
            r.raise_for_status()
            data = r.json()
            return data.get("result") or data.get("message") or ""
    except Exception as e:
        print(f"[TASK_API/{agent_id.upper()}] {type(e).__name__}: {e}")
        return ""


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
    # FIX 1: Strip @everyone / @here before ANY processing
    message_content = message.content.replace('@everyone', '').replace('@here', '').strip()

    if message.author.id in BOT_USER_IDS:
        return
    if message.channel.name not in RESPOND_CHANNELS:
        return

    # FIX 2: Owner detection by name list as well as ID
    display = message.author.display_name.lower()
    uname   = message.author.name.lower()
    is_owner = (
        bool(DISCORD_OWNER_ID and message.author.id == DISCORD_OWNER_ID)
        or display in OWNER_NAMES
        or uname in OWNER_NAMES
    )
    channel_id   = message.channel.id
    channel_name = message.channel.name
    msg_lower    = message_content.lower()

    # ── /model command — one bot handles it ──────────────────────────────────
    if message_content.startswith("/model "):
        if message.id % len(AGENT_NAMES) != AGENT_NAMES.index(this_agent_id):
            return
        parts = message_content.split()
        model = parts[1].lower() if len(parts) > 1 else ""
        if model in ("groq", "openrouter", "gemini"):
            SELECTED_MODEL[channel_id] = model
            await message.channel.send(f"✅ Model set to **{model}** for #{channel_name}")
        else:
            await message.channel.send("Usage: `/model groq` | `/model openrouter` | `/model gemini`")
        return

    # ── Image attachments — analyze via Gemini Vision ─────────────────────────
    if message.attachments:
        images = [a for a in message.attachments
                  if a.content_type and a.content_type.startswith("image/")]
        if images and message.id % len(AGENT_NAMES) == AGENT_NAMES.index(this_agent_id):
            async with message.channel.typing():
                response = await analyze_image(images[0], this_agent_id, is_owner)
            if response:
                await message.channel.send(response)
                print(f"[{this_agent_id.upper()}] ← image analyzed")
            return

    # ── Owner work request — call task API ────────────────────────────────────
    if is_owner and any(kw in msg_lower for kw in WORK_KEYWORDS):
        if message.id % len(AGENT_NAMES) == AGENT_NAMES.index(this_agent_id):
            async with message.channel.typing():
                result = await call_task_api(message_content, this_agent_id)
            if result:
                await message.channel.send(result)
                print(f"[{this_agent_id.upper()}] ← owner task executed")
                return
            # Task API failed — fall through to normal conversation

    mentioned = next(
        (aid for aid in AGENT_NAMES
         if aid in msg_lower
         or AGENT_PERSONALITIES[aid]["name"].lower() in msg_lower),
        None,
    )

    # ── PATH A: specific agent mentioned ──────────────────────────────────────
    if mentioned is not None:
        if mentioned != this_agent_id:
            return  # Not me — all 8 other bots return here instantly

        # I'm the mentioned agent — owner always gets a reply, others 100% too
        await asyncio.sleep(random.uniform(1.5, 3.0))
        async with message.channel.typing():
            response = await generate_response(
                this_agent_id, message_content,
                is_owner=is_owner, channel_id=channel_id,
            )
        if not response:
            return
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
                second_resp = await generate_response(
                    second, message_content, context,
                    is_owner=is_owner, channel_id=channel_id,
                )
                if second_resp:
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

    # Owner always gets a response; others 70% chance
    if not is_owner and random.random() > 0.70:
        return

    await asyncio.sleep(random.uniform(2.0, 4.0))
    async with message.channel.typing():
        response = await generate_response(
            this_agent_id, message_content,
            is_owner=is_owner, channel_id=channel_id,
        )
    if not response:
        return
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
            second_resp = await generate_response(
                second, message_content, context,
                is_owner=is_owner, channel_id=channel_id,
            )
            if second_resp:
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
        message_content = message.content.replace('@everyone', '').replace('@here', '').strip()
        if message.author.id in BOT_USER_IDS:
            return
        print(f"Human message from {message.author}: {message_content}")
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

    active_providers = [k for k, v in [("Groq", GROQ_API_KEY), ("OpenRouter", OPENROUTER_API_KEY), ("Gemini", GEMINI_API_KEY)] if v]
    if active_providers:
        print(f"[AI] Providers: {' → '.join(active_providers)}\n")
    else:
        print("[WARN] No AI providers configured — bots will stay silent on all failures\n")

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
