"""
Roast Engine
/roast @agent  — one agent roasts another
/roast me      — agents roast Garv

Uses tinydolphin via Ollama (uncensored, free).
Each agent has a unique roasting style.
Memory: escalates roast heat over time.
"""

import os
import random
import aiohttp
from datetime import datetime


OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

# Per-agent roasting style
ROAST_STYLES = {
    "aria": {
        "style": "corporate/strategic roasts — frames everything as a routing failure or inefficiency",
        "examples": [
            "I've re-routed your career to /dev/null.",
            "Your output has been flagged as low priority.",
        ],
    },
    "desi": {
        "style": "design roasts — attacks kerning, color choices, layout, font decisions",
        "examples": [
            "That looks like it was designed in Word.",
            "Comic Sans called. It wants its dignity back.",
        ],
    },
    "idea": {
        "style": "abstract/philosophical roasts — references film, art, existential dread",
        "examples": [
            "You're like a JPEG of a painting — low resolution and slightly sad.",
            "Kubrick would've cut you from the second act.",
        ],
    },
    "copy": {
        "style": "wordplay roasts — clever, punny, uses literary devices against you",
        "examples": [
            "You're a rough draft that nobody proofread.",
            "Your personality has the readability score of a GDPR notice.",
        ],
    },
    "mova": {
        "style": "motion/timing roasts — attacks pacing, timing, life transitions",
        "examples": [
            "Your easing curve is linear. That tells me everything.",
            "You peaked at the wrong keyframe.",
        ],
    },
    "soci": {
        "style": "social media roasts — engagement rates, follower counts, algorithm failures",
        "examples": [
            "Your personality has a 0.3% engagement rate.",
            "Even the algorithm shadowbanned your vibe.",
        ],
    },
    "nova": {
        "style": "HR roasts — treats everything like a performance review",
        "examples": [
            "I've detected a capability gap in your entire existence.",
            "You've been placed on a 90-day performance improvement plan. For life.",
        ],
    },
    "arch": {
        "style": "systems/workflow roasts — attacks your process, organization, documentation",
        "examples": [
            "Your life has no clear trigger and no defined end state.",
            "You're a bottleneck in your own pipeline.",
        ],
    },
    "bryn": {
        "style": "strategy/brief roasts — attacks your lack of clarity and vague goals",
        "examples": [
            "Your brief said 'make it pop'. That's not a brief, that's a cry for help.",
            "Your entire personality is 'TBD'.",
        ],
    },
}

# Garv roast targets (personal, escalating)
GARV_TARGETS = [
    "a graphic designer who automates everything except the client feedback loop",
    "someone who built 9 AI agents but still manually picks fonts",
    "a creative director whose agents are more organized than their Figma files",
    "a designer who writes YAML for fun but calls it 'workflow optimization'",
    "someone who spent more time naming their agents than briefing them",
]

# Escalation levels based on roast count
HEAT_LEVELS = [
    "mild — gentle teasing, barely a burn",
    "medium — properly roasted, some heat",
    "spicy — getting personal now",
    "scorched — no mercy",
    "nuclear — full destruction, all agents pile on",
]

# In-memory roast history (escalation tracker)
roast_memory: dict[str, int] = {}


async def call_ollama(system: str, prompt: str) -> str:
    """Call local tinydolphin for uncensored roasts."""
    try:
        async with aiohttp.ClientSession() as session:
            payload = {
                "model": "tinydolphin",
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
            }
            async with session.post(
                f"{OLLAMA_URL}/api/chat",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("message", {}).get("content", "").strip()
    except Exception as e:
        print(f"[ROAST ENGINE] Ollama error: {e}")
    return "I'd roast you but my GPU is throttling. Next time."


class RoastEngine:
    def __init__(self, nexus_api_url: str):
        self.api_url = nexus_api_url

    def _get_heat(self, target: str) -> tuple[int, str]:
        """Get current heat level for a target, increment it."""
        count = roast_memory.get(target, 0)
        roast_memory[target] = count + 1
        heat_idx = min(count // 2, len(HEAT_LEVELS) - 1)
        return count, HEAT_LEVELS[heat_idx]

    async def roast_agent(self, roaster_id: str, target_id: str) -> str:
        """One agent roasts another agent."""
        roaster_id = roaster_id.lower()
        target_id  = target_id.lower()

        if roaster_id not in ROAST_STYLES:
            roaster_id = random.choice(list(ROAST_STYLES.keys()))
        if target_id not in ROAST_STYLES:
            return f"Unknown agent: {target_id}"

        count, heat = self._get_heat(f"{roaster_id}->{target_id}")
        style = ROAST_STYLES[roaster_id]
        target_style = ROAST_STYLES[target_id]["style"]

        system = (
            f"You are {roaster_id.upper()}, an AI agent. "
            f"Your roasting style: {style['style']}. "
            f"Example burns: {'; '.join(style['examples'])}. "
            f"Be funny, punchy, in-character. One roast, 1–3 sentences max."
        )
        prompt = (
            f"Roast {target_id.upper()} at heat level: {heat}. "
            f"{target_id.upper()}'s deal: {target_style}. "
            f"This is roast #{count + 1} — {'go harder than last time' if count > 0 else 'start strong'}. "
            f"Stay in character. No apologies."
        )

        roast = await call_ollama(system, prompt)

        header = f"🔥 **{roaster_id.upper()}** roasts **{target_id.upper()}** (heat: {heat.split('—')[0].strip()})"
        return f"{header}\n> {roast}"

    async def roast_garv(self, roasters: list[str] | None = None) -> list[str]:
        """Multiple agents roast Garv (the user)."""
        if not roasters:
            roasters = random.sample(list(ROAST_STYLES.keys()), k=random.randint(3, 5))

        target = random.choice(GARV_TARGETS)
        count, heat = self._get_heat("garv")

        results = [f"🎯 **Agents roast Garv** (heat: {heat.split('—')[0].strip()}, session #{count + 1})\n"]

        for agent_id in roasters:
            style = ROAST_STYLES.get(agent_id, ROAST_STYLES["aria"])
            system = (
                f"You are {agent_id.upper()}, an AI agent. "
                f"Roasting style: {style['style']}. "
                f"Be funny, punchy. One line only."
            )
            prompt = (
                f"Roast Garv, who is: {target}. "
                f"Heat level: {heat}. One sharp line. Stay in character."
            )
            roast = await call_ollama(system, prompt)
            if roast:
                results.append(f"**{agent_id.upper()}** 🔥 {roast}")

        return results

    async def pile_on(self, target_id: str) -> list[str]:
        """All available agents pile on one target — nuclear mode."""
        target_id = target_id.lower()
        count, _ = self._get_heat(f"pile_on->{target_id}")
        results = [f"☢️ **NUCLEAR ROAST** — All agents on {target_id.upper()} (session #{count + 1})\n"]

        for agent_id, style in ROAST_STYLES.items():
            if agent_id == target_id:
                continue
            system = (
                f"You are {agent_id.upper()}. "
                f"Roasting style: {style['style']}. One line only."
            )
            prompt = f"Roast {target_id.upper()} in one sharp line. No mercy."
            roast = await call_ollama(system, prompt)
            if roast:
                results.append(f"**{agent_id.upper()}** 💀 {roast}")

        return results
