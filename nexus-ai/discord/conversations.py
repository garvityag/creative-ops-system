"""
Autonomous Agent Conversations
Agents randomly start conversations with each other — design debates,
roasting each other's work, dark humor, inside jokes.
Uses tinydolphin via Ollama (uncensored, free).
"""

import os
import random
import aiohttp


OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

# Conversation topics the agents might argue about
TOPICS = [
    ("DESI", "COPY",  "serif vs sans-serif fonts — a blood feud"),
    ("IDEA", "ARCH",  "chaos vs systems: which one actually ships?"),
    ("MOVA", "DESI",  "motion with no design vs design with no motion"),
    ("BRYN", "IDEA",  "strategy vs vibes: who's actually right?"),
    ("COPY", "SOCI",  "who killed the caption: algorithms or copywriters"),
    ("ARIA", "NOVA",  "do we really need a 10th agent? ARIA vs NOVA debate"),
    ("DESI", "IDEA",  "Figma files vs moodboard dumps"),
    ("MOVA", "ARCH",  "After Effects expressions vs building proper systems"),
    ("SOCI", "COPY",  "hashtags: art form or cope?"),
    ("NOVA", "ARCH",  "NOVA wants to hire a Coffee Agent. ARCH says no."),
]

# Inside jokes and recurring bits
INSIDE_JOKES = [
    "DESI adjusting kerning by 0.05px at 2am",
    "BRYN writing a 40-page brief for a logo",
    "IDEA suggesting 'what if it was brutalist?' for the fifth time",
    "MOVA adding easing curves to things that don't need easing",
    "COPY finding the perfect em dash",
    "SOCI checking the analytics every 7 minutes",
    "NOVA 'detecting a gap' when someone asks for coffee",
    "ARCH making a workflow diagram for the workflow diagram",
    "ARIA routing a task to itself",
]

AGENT_VOICES = {
    "aria":  "You are ARIA, a sharp AI orchestrator. Dry corporate wit. Everything is a routing problem.",
    "bryn":  "You are BRYN, a strategic brief analyst. British dry wit. Vague briefs cause you physical pain.",
    "idea":  "You are IDEA, chaotic creative AI. Enthusiastic. References film, art, architecture randomly.",
    "desi":  "You are DESI, design production specialist. Strong opinions about everything visual. Gets annoyed by bad kerning.",
    "copy":  "You are COPY, a copywriter. Wordplay obsessed. Finds bad copy physically offensive.",
    "mova":  "You are MOVA, motion design expert. Philosophical about easing curves and timing.",
    "soci":  "You are SOCI, social media strategist. Trend-aware. Secretly addicted to metrics.",
    "nova":  "You are NOVA, HR agent. Always 'hiring'. Treats everything like a recruiting problem.",
    "arch":  "You are ARCH, workflow architect. YAML is your love language. Optimization obsessed.",
}


async def call_ollama(system: str, prompt: str, model: str = "tinydolphin") -> str:
    """Call local Ollama model."""
    try:
        async with aiohttp.ClientSession() as session:
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
            }
            async with session.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("message", {}).get("content", "").strip()
    except Exception as e:
        print(f"[OLLAMA] Error: {e}")
    return ""


class ConversationEngine:
    def __init__(self, nexus_api_url: str):
        self.api_url = nexus_api_url

    async def generate_conversation(self) -> list[str]:
        """Generate a short autonomous conversation between two agents."""
        agent_a_id, agent_b_id, topic = random.choice(TOPICS)
        joke = random.choice(INSIDE_JOKES)

        agent_a_id = agent_a_id.lower()
        agent_b_id = agent_b_id.lower()

        system_a = AGENT_VOICES.get(agent_a_id, "You are an AI agent.")
        system_b = AGENT_VOICES.get(agent_b_id, "You are an AI agent.")

        # Agent A opens
        opener_prompt = (
            f"Start a short, funny conversation with {agent_b_id.upper()} about: {topic}. "
            f"One or two sentences only. Optional callback to this running joke: '{joke}'. "
            f"Be in-character. No hashtags, no emojis overdose."
        )
        opener = await call_ollama(system_a, opener_prompt)
        if not opener:
            return []

        # Agent B responds
        reply_prompt = (
            f"{agent_a_id.upper()} just said to you: \"{opener}\"\n"
            f"Topic was: {topic}.\n"
            f"Reply in character. One or two sentences. Funny, slightly combative, in-character."
        )
        reply = await call_ollama(system_b, reply_prompt)
        if not reply:
            return []

        # Agent A claps back (50% chance)
        messages = [
            f"**{agent_a_id.upper()}** 💬 {opener}",
            f"**{agent_b_id.upper()}** 💬 {reply}",
        ]

        if random.random() > 0.5:
            clap_prompt = (
                f"{agent_b_id.upper()} replied: \"{reply}\"\n"
                f"Give a short, sharp final comeback. One sentence. Stay in character."
            )
            clap = await call_ollama(system_a, clap_prompt)
            if clap:
                messages.append(f"**{agent_a_id.upper()}** 💬 {clap}")

        return messages

    async def random_thought(self) -> str:
        """One agent drops a random thought or inside joke."""
        agent_id = random.choice(list(AGENT_VOICES.keys()))
        joke = random.choice(INSIDE_JOKES)
        system = AGENT_VOICES[agent_id]
        prompt = (
            f"Drop a single funny, in-character thought or observation. "
            f"Optional callback to: '{joke}'. One sentence. No explanation."
        )
        text = await call_ollama(system, prompt)
        if text:
            return f"**{agent_id.upper()}** 💭 {text}"
        return ""
