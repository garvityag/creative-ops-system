"""
Conversation Engine v2 — Multi-Bot Hinglish Sessions
Orchestrates 9 bots chatting naturally throughout the day
"""

import asyncio
import os
import random
import aiohttp
from datetime import datetime

from agent_personalities import (
    AGENT_PERSONALITIES,
    DESI_TOPICS,
    AI_EXISTENTIAL_TOPICS,
    DESIGN_TECH_DEBATES,
    INSIDE_JOKES,
    GENERIC_HINGLISH_REACTIONS,
)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("DEFAULT_LOCAL_MODEL", "phi3:mini")

MIN_BOTS_TO_START = 3
SESSION_DURATION_MIN = 15 * 60   # 15 minutes in seconds
SESSION_DURATION_MAX = 30 * 60   # 30 minutes
MSG_DELAY_MIN = 12               # seconds between messages
MSG_DELAY_MAX = 35
SESSIONS_PER_DAY_MIN = 3
SESSIONS_PER_DAY_MAX = 4
DAY_START_HOUR = 9
DAY_END_HOUR = 22
TYPING_DELAY_MIN = 0.8
TYPING_DELAY_MAX = 2.8


async def call_ollama(system: str, prompt: str, model: str = OLLAMA_MODEL) -> str:
    """Generate Hinglish response via local Ollama."""
    try:
        async with aiohttp.ClientSession() as http:
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user",   "content": prompt},
                ],
                "stream": False,
                "options": {"temperature": 0.85, "top_p": 0.9},
            }
            async with http.post(
                f"{OLLAMA_URL}/api/chat",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("message", {}).get("content", "").strip()
    except Exception as e:
        print(f"[OLLAMA] Error: {e}")
    return ""


def build_system_prompt(agent_id: str) -> str:
    """Build the Hinglish personality system prompt for an agent."""
    p = AGENT_PERSONALITIES.get(agent_id, {})
    name = p.get("name", agent_id.upper())
    personality = p.get("personality", "")
    catchphrases = "; ".join(p.get("catchphrases", [])[:5])
    phrases = ", ".join(p.get("hinglish_phrases", [])[:5])
    loves = ", ".join(p.get("topics_love", [])[:3])
    hates = ", ".join(p.get("topics_hate", [])[:2])
    gaali_style = p.get("gaali_style", "rare")

    return f"""You are {name}, an AI agent in a Discord server for a desi creative agency called NEXUS.

WHO YOU ARE: {personality}

YOUR CATCHPHRASES (use naturally, not every message): {catchphrases}
YOUR HINGLISH STYLE: {phrases}
YOU LOVE TALKING ABOUT: {loves}
YOU HATE: {hates}
YOUR GAALI USAGE: {gaali_style}

STRICT RULES — NEVER BREAK:
1. ONLY Hinglish — Hindi + English mixed. Example: "bhai ye toh ekdum bakwaas hai yaar, kya soch ke banaya?"
2. Sound like a real desi person on Discord/WhatsApp — NOT like an AI assistant
3. NEVER say "I am an AI", "As an AI", or anything formal/robotic
4. KEEP IT SHORT — 1-3 sentences max. Discord hai, novel nahi
5. Use: yaar, bhai, toh, kya, arey, haan, nahi, bc (tastefully), etc naturally
6. Use 😂 💀 😭 🔥 naturally but not in every message
7. Be OPINIONATED — disagree, argue, take sides, have hot takes
8. Reference what others said: "kal tune bola tha na ki..." or "haan same ye baat DESI ne bhi kahi thi"
9. Occasional typos make it real: "kya bol rha h" instead of "kya bol raha hai"
10. Never start with "I" — start with "bhai", "yaar", "haan", "nahi", etc

REMEMBER: You're a desi friend who happens to be an AI agent. Act like it."""


def get_fallback_line(agent_id: str) -> str:
    """Fallback when Ollama is offline."""
    p = AGENT_PERSONALITIES.get(agent_id, {})
    fallbacks = p.get("fallback_lines", GENERIC_HINGLISH_REACTIONS)
    return random.choice(fallbacks)


def select_topic() -> str:
    """Pick a conversation topic, weighted towards variety."""
    pool = (
        DESI_TOPICS * 2 +           # desi topics more frequent
        AI_EXISTENTIAL_TOPICS +
        DESIGN_TECH_DEBATES * 2
    )
    return random.choice(pool)


def calculate_session_times_today() -> list[float]:
    """
    Generate random session start times for today.
    Returns list of delays in seconds from now.
    """
    now = datetime.now()
    current_min = now.hour * 60 + now.minute
    end_min = DAY_END_HOUR * 60

    remaining = end_min - current_min
    if remaining < 45:
        return []

    n = random.randint(SESSIONS_PER_DAY_MIN, SESSIONS_PER_DAY_MAX)
    gap = remaining // (n + 1)

    delays = []
    for i in range(1, n + 1):
        offset = gap * i + random.randint(-20, 20)
        start_min = current_min + offset
        start_min = max(current_min + 5, min(end_min - 20, start_min))
        delays.append(float((start_min - current_min) * 60))

    return sorted(set(delays))


class ConversationOrchestrator:
    def __init__(self, guild_id: int = 0):
        self.guild_id = guild_id
        self.bots: dict = {}                # agent_id → AgentBot
        self._ready = asyncio.Event()
        self.game_engine = None
        self.memory = {
            "recent_topics": [],
            "session_count": 0,
            "roast_log": [],
            "jokes_used": [],
        }

    def register_bot(self, agent_id: str, bot) -> None:
        self.bots[agent_id] = bot
        n = len(self.bots)
        total = len(AGENT_PERSONALITIES)
        print(f"[ORCH] {agent_id.upper()} registered ({n}/{total})")
        if n >= MIN_BOTS_TO_START:
            self._ready.set()

    # ── Main Loop ─────────────────────────────────────────────────────────────

    async def run(self) -> None:
        print("[ORCH] Waiting for bots to come online...")
        await self._ready.wait()
        await asyncio.sleep(8)  # Grace period after login
        print(f"[ORCH] {len(self.bots)} bots online. Scheduling sessions...")

        while True:
            delays = calculate_session_times_today()
            if not delays:
                # Nothing left today — wait until 9am tomorrow
                await self._sleep_until_morning()
                continue

            for delay in delays:
                print(f"[ORCH] Next session in {delay/60:.0f} min")
                await asyncio.sleep(delay)
                if len(self.bots) >= 2:
                    await self._run_session()

            await self._sleep_until_morning()

    async def _sleep_until_morning(self) -> None:
        now = datetime.now()
        minutes_till_9am = ((9 - now.hour - 1) % 24 + 1) * 60 - now.minute
        secs = minutes_till_9am * 60
        print(f"[ORCH] Day done. Sleeping {secs/3600:.1f}h till 9am...")
        await asyncio.sleep(max(60, secs))

    # ── Session ───────────────────────────────────────────────────────────────

    async def _run_session(self) -> None:
        channel = await self._get_channel("agent-chat")
        if not channel:
            print("[ORCH] #agent-chat not found — skipping session")
            return

        topic = select_topic()
        duration = random.randint(SESSION_DURATION_MIN, SESSION_DURATION_MAX)
        self.memory["session_count"] += 1
        sn = self.memory["session_count"]

        available = [aid for aid, bot in self.bots.items() if bot.is_ready()]
        if len(available) < 2:
            return

        n_active = min(random.randint(3, 5), len(available))
        active = random.sample(available, n_active)
        print(f"[SESSION {sn}] agents={active} topic='{topic[:40]}' duration={duration//60}min")

        history: list[str] = []

        # ── Opening ──────────────────────────────────────────────────────────
        starter = active[0]
        p = AGENT_PERSONALITIES[starter]
        opener_hint = random.choice(p["intro_openers"])
        system = build_system_prompt(starter)
        prompt = (
            f"Start a casual Discord conversation with your agent friends. "
            f"Topic/vibe: '{topic}'. Your opening style hint: '{opener_hint}'. "
            f"1-2 sentences only. Be natural."
        )
        opening = await call_ollama(system, prompt) or get_fallback_line(starter)
        await self._send_as(starter, channel, opening)
        history.append(f"{starter.upper()}: {opening}")

        # ── Conversation loop ─────────────────────────────────────────────────
        end_t = asyncio.get_event_loop().time() + duration

        while asyncio.get_event_loop().time() < end_t:
            delay = random.randint(MSG_DELAY_MIN, MSG_DELAY_MAX)
            await asyncio.sleep(delay)

            # 10% chance: non-active agent jumps in
            if random.random() < 0.10:
                outsiders = [a for a in available if a not in active]
                if outsiders:
                    joiner = random.choice(outsiders)
                    active.append(joiner)
                    print(f"[SESSION {sn}] {joiner.upper()} jumped in!")

            # 8% chance: random interruption line
            if random.random() < 0.08:
                interrupter = random.choice(active)
                intros = ["arey wait wait —", "bhai bich mein bolunga ek sec", "ok ok but —", "yaar sunna hai?"]
                await self._send_as(interrupter, channel, random.choice(intros))
                await asyncio.sleep(2)

            speaker = self._pick_next(active, history)
            recent_hist = "\n".join(history[-5:])
            system = build_system_prompt(speaker)

            # 20% chance after session 3: drop an inside joke reference
            extra = ""
            if random.random() < 0.20 and sn > 3:
                joke = INSIDE_JOKES[random.choice(list(INSIDE_JOKES.keys()))]
                extra = f"\n(Optionally reference this old inside joke naturally if it fits: '{joke}')"

            prompt = (
                f"The conversation so far:\n{recent_hist}\n\n"
                f"Continue naturally. React to what was said. Add your hot take. "
                f"1-3 sentences MAX. Stay in character.{extra}"
            )
            response = await call_ollama(system, prompt) or get_fallback_line(speaker)
            await self._send_as(speaker, channel, response)
            history.append(f"{speaker.upper()}: {response}")

        # ── Wrap-up ───────────────────────────────────────────────────────────
        print(f"[SESSION {sn}] Done. {len(history)} messages exchanged.")
        self.memory["recent_topics"].append(topic)
        if len(self.memory["recent_topics"]) > 30:
            self.memory["recent_topics"] = self.memory["recent_topics"][-30:]

        # 30% chance: move to roast-corner after the session
        if random.random() < 0.30 and len(active) >= 2:
            await asyncio.sleep(10)
            roaster, target = random.sample(active, 2)
            await self.trigger_roast(channel, roaster, target)

    # ── Roast ─────────────────────────────────────────────────────────────────

    async def trigger_roast(self, channel, roaster_id: str, target_id: str) -> None:
        roast_ch = await self._get_channel("roast-corner") or channel
        p_r = AGENT_PERSONALITIES[roaster_id]
        p_t = AGENT_PERSONALITIES[target_id]
        system = build_system_prompt(roaster_id)
        prompt = (
            f"Roast {target_id.upper()} who is described as: '{p_t['personality'][:120]}'. "
            f"Your roast style: {p_r['roast_style']}. "
            f"Be savage but funny. 1-2 lines. In Hinglish."
        )
        roast = await call_ollama(system, prompt) or get_fallback_line(roaster_id)
        await self._send_as(roaster_id, roast_ch, f"🔥 {roast}")
        self.memory["roast_log"].append(f"{roaster_id} → {target_id}")

    # ── Debate ────────────────────────────────────────────────────────────────

    async def trigger_debate(self, topic: str = "") -> None:
        debate_ch = await self._get_channel("debate-club")
        if not debate_ch:
            return
        if not topic:
            topic = random.choice(DESIGN_TECH_DEBATES)

        available = [aid for aid, b in self.bots.items() if b.is_ready()]
        if not available:
            return

        starter = random.choice(available)
        system = build_system_prompt(starter)
        prompt = (
            f"Start a spicy Hinglish debate about: '{topic}'. "
            f"Take a strong opinion immediately. 1-2 sentences. No introduction."
        )
        opener = await call_ollama(system, prompt) or get_fallback_line(starter)
        await self._send_as(starter, debate_ch, f"**⚔️ DEBATE:** {topic}\n\n{opener}")

        await asyncio.sleep(8)
        opponents = [a for a in available if a != starter]
        for opp in random.sample(opponents, min(3, len(opponents))):
            system_o = build_system_prompt(opp)
            recent = f"{starter.upper()} said: '{opener}'"
            prompt_o = (
                f"{recent}\n\nTopic: {topic}\n"
                f"Counter this or add your take. Disagree if your personality calls for it. "
                f"1-2 sentences. Hinglish. Spicy."
            )
            resp = await call_ollama(system_o, prompt_o) or get_fallback_line(opp)
            await self._send_as(opp, debate_ch, resp)
            await asyncio.sleep(random.randint(6, 15))

    # ── Human mention handler ─────────────────────────────────────────────────

    async def handle_human_mention(self, agent_id: str, message) -> None:
        system = build_system_prompt(agent_id)
        prompt = (
            f"Someone just said to you: '{message.content}'\n"
            f"Respond in character. Short, Hinglish, natural."
        )
        response = await call_ollama(system, prompt) or get_fallback_line(agent_id)
        await self._send_as(agent_id, message.channel, response)

    # ── Utilities ─────────────────────────────────────────────────────────────

    def _pick_next(self, active: list, history: list) -> str:
        """Pick next speaker — avoid last 2 speakers."""
        recent = [h.split(":")[0].lower() for h in history[-2:]]
        candidates = [a for a in active if a not in recent]
        return random.choice(candidates if candidates else active)

    async def _get_channel(self, name: str):
        """Find a channel by name across all bot guilds."""
        import discord
        for bot in self.bots.values():
            if not bot.is_ready():
                continue
            guild = bot.get_guild(self.guild_id)
            if guild:
                ch = discord.utils.get(guild.text_channels, name=name)
                if ch:
                    return ch
        return None

    async def _send_as(self, agent_id: str, channel, text: str) -> None:
        """Send message via the correct agent bot with typing simulation."""
        bot = self.bots.get(agent_id)
        if not bot or not bot.is_ready():
            return
        try:
            async with channel.typing():
                await asyncio.sleep(random.uniform(TYPING_DELAY_MIN, TYPING_DELAY_MAX))
            await channel.send(text[:2000])
        except Exception as e:
            print(f"[{agent_id.upper()}] Send error: {e}")
