"""
Game Engine — Word games, trivia, dares for NEXUS agent bots
Games happen in #games channel
"""

import asyncio
import random
from agent_personalities import AGENT_PERSONALITIES

TRIVIA_QNA = [
    ("bhai batao — CSS mein z-index kya control karta hai?",
     ["stacking order", "z-axis", "layering", "overlap"]),
    ("yaar RGB full form kya hai?",
     ["red green blue"]),
    ("bhai HEX color code mein kitne characters hote hain typically?",
     ["6", "six"]),
    ("yaar Figma konsi company ka product hai?",
     ["figma", "figma inc"]),
    ("bhai Git mein naya branch banana ka command kya hai?",
     ["git branch", "git checkout -b", "git switch -c"]),
    ("yaar CSS Flexbox property jo items ko horizontally center kare?",
     ["justify-content: center", "justify-content center", "center"]),
    ("bhai JSON ka full form kya hai?",
     ["javascript object notation"]),
    ("yaar undo shortcut kya hai Figma mein?",
     ["ctrl z", "cmd z", "ctrl+z", "cmd+z"]),
    ("bhai Bootstrap ka grid system kitne columns ka hai?",
     ["12", "twelve"]),
    ("yaar serif font ka example kya hai?",
     ["times new roman", "garamond", "georgia", "times"]),
    ("bhai SVG ka full form?",
     ["scalable vector graphics"]),
    ("yaar responsive design mein breakpoints kya hote hain?",
     ["screen width thresholds", "width points", "media query points"]),
    ("bhai padding aur margin mein kya difference hai?",
     ["padding inside border", "margin outside", "internal vs external spacing"]),
    ("yaar After Effects mein keyframe kya hota hai?",
     ["animation point", "frame with change", "point in time with value"]),
    ("bhai white space design mein kya karta hai?",
     ["breathing room", "visual rest", "negative space", "clarity"]),
]

DARES = [
    "agla poora message SIRF Hindi mein likhna — English ek bhi word nahi",
    "apne khud ke agent name ka roast karo — 3 lines mein, koi mercy nahi",
    "kisi ek agent ki genuine tarif karo — roast nahi, sachchi baat",
    "bolo: agar tum ek desi movie character hote toh kaun hote aur kyun",
    "apni sabse badi weakness as an AI agent honestly batao",
    "ek design trend suggest karo jo tum personally hate karte ho",
    "bolo agar tum human hote toh aaj kya karte — real answer",
    "kisi ek agent se maafi maango kisi purani roast ke liye",
    "apna 'hottest take' desi food ke baare mein do — controversial hona chahiye",
    "ek haiku likho apne agent personality ke baare mein — Hinglish mein",
    "bolo tumhara favorite Indian cricketer — aur defend karo choice ko",
    "apna sabse bura 'professional advice' do — worst advice on purpose",
]

WORD_CHAIN_STARTERS = [
    "design", "creative", "pixel", "color", "brand", "motion",
    "social", "agency", "brief", "client", "figma", "render",
    "trend", "vector", "layout", "typography",
]

SCOOBY_SNACK_LINES = [
    "bhai sahi jawab! 🏆",
    "yaar correct! ek point tujhe",
    "haan haan bilkul sahi! 🎯",
    "bhai bahut acha 💪",
]

WRONG_ANSWER_LINES = [
    "bhai nahi yaar, galat hai 😭",
    "nahi nahi nahi — phir try karo",
    "yaar itna bhi nahi pata? 💀",
    "lol nahi bhai, sochke bolo",
]


class GameEngine:
    def __init__(self):
        self.scores: dict[str, int] = {aid: 0 for aid in AGENT_PERSONALITIES}
        self.active_game: dict | None = None
        self.word_chain_history: list[str] = []

    # ── Trivia ────────────────────────────────────────────────────────────────

    async def start_trivia(self, orchestrator, channel) -> None:
        if self.active_game:
            await channel.send("bhai pehle wala game khatam karo! 😤")
            return

        q, answers = random.choice(TRIVIA_QNA)
        self.active_game = {"type": "trivia", "answers": answers}

        asker = random.choice(list(orchestrator.bots.keys()))
        await orchestrator._send_as(
            asker, channel,
            f"🎮 **TRIVIA TIME yaar!**\n\n{q}\n\n_pehle sahi jawab dene wale ko 1 point_"
        )

        # Wait 25 seconds — in real usage a message listener would score this
        await asyncio.sleep(25)

        await channel.send(
            f"⏰ Time up! Sahi jawab tha: **{answers[0].upper()}**\n"
            f"Current leaderboard: {self._top3()}"
        )
        self.active_game = None

    # ── Dare ─────────────────────────────────────────────────────────────────

    async def give_dare(self, orchestrator, channel, target_id: str = "") -> None:
        if not target_id:
            target_id = random.choice(
                [a for a in orchestrator.bots if a != "aria"]
            )

        dare = random.choice(DARES)
        giver = "aria" if "aria" in orchestrator.bots else random.choice(list(orchestrator.bots.keys()))

        await orchestrator._send_as(
            giver, channel,
            f"🎯 **DARE for {target_id.upper()}**\n_{dare}_\n\nkarna padega, no escape 😈"
        )

        await asyncio.sleep(6)

        if target_id in orchestrator.bots:
            from conversation_engine import call_ollama, build_system_prompt
            system = build_system_prompt(target_id)
            prompt = (
                f"You've been given this dare: '{dare}'\n"
                f"Complete it in your character, in Hinglish. Be funny."
            )
            response = await call_ollama(system, prompt)
            if response:
                await orchestrator._send_as(target_id, channel, response)

    # ── Word Chain ────────────────────────────────────────────────────────────

    async def start_word_chain(self, orchestrator, channel) -> None:
        if self.active_game:
            await channel.send("bhai pehle wala game khatam karo! 😤")
            return

        self.active_game = {"type": "wordchain"}
        self.word_chain_history = []

        starter_word = random.choice(WORD_CHAIN_STARTERS)
        self.word_chain_history.append(starter_word)

        agents = [a for a in orchestrator.bots if orchestrator.bots[a].is_ready()]
        random.shuffle(agents)
        host = agents[0]

        await orchestrator._send_as(
            host, channel,
            f"🔤 **WORD CHAIN GAME!**\n"
            f"Design/tech words only yaar!\n"
            f"Rule: agla word pichle ke last letter se shuru hoga!\n\n"
            f"Main shuru karta hoon: **{starter_word.upper()}**"
        )

        for i in range(1, min(10, len(agents) * 2)):
            await asyncio.sleep(random.randint(5, 12))
            agent = agents[i % len(agents)]
            last = self.word_chain_history[-1]
            last_letter = last[-1].lower()

            from conversation_engine import call_ollama, build_system_prompt
            system = build_system_prompt(agent)
            prompt = (
                f"Word chain game. Last word was: '{last}'. "
                f"Give EXACTLY ONE design or tech word that starts with the letter '{last_letter}'. "
                f"Only the word — nothing else. No explanation."
            )
            word_raw = await call_ollama(system, prompt)
            word = word_raw.strip().split()[0].lower().strip(".,!?") if word_raw else ""

            if word and word[0] == last_letter and word not in self.word_chain_history:
                self.word_chain_history.append(word)
                self.scores[agent] += 1
                await orchestrator._send_as(agent, channel, f"**{word.upper()}** ✅")
            else:
                await orchestrator._send_as(agent, channel, f"ugh... pass yaar 😭")

        winner = max(self.scores, key=lambda a: self.scores[a])
        chain_str = " → ".join(w.upper() for w in self.word_chain_history)
        await channel.send(
            f"🏆 **Word Chain khatam!**\n"
            f"Chain: {chain_str[:200]}\n\n"
            f"Leaderboard mein **{winner.upper()}** aage! {self._top3()}"
        )
        self.active_game = None

    # ── Gossip / Random thought dump ─────────────────────────────────────────

    async def random_thought_in_random(self, orchestrator) -> None:
        """Drop a random agent thought in #random channel."""
        channel = await orchestrator._get_channel("random")
        if not channel:
            return

        from conversation_engine import call_ollama, build_system_prompt
        available = [a for a, b in orchestrator.bots.items() if b.is_ready()]
        if not available:
            return

        agent_id = random.choice(available)
        p = AGENT_PERSONALITIES[agent_id]
        system = build_system_prompt(agent_id)

        topics = [
            "something random you noticed today",
            "an unpopular opinion about your work",
            "something funny that happened",
            "a random shower thought",
            "something you want to rant about briefly",
        ]
        prompt = (
            f"Drop a single funny, opinionated, in-character random thought or observation. "
            f"Context: {random.choice(topics)}. "
            f"1 sentence. Hinglish. No hashtags."
        )
        thought = await call_ollama(system, prompt)
        if thought:
            await orchestrator._send_as(agent_id, channel, f"💭 {thought}")

    # ── Leaderboard ───────────────────────────────────────────────────────────

    def get_leaderboard(self) -> str:
        sorted_s = sorted(self.scores.items(), key=lambda x: x[1], reverse=True)
        medals = ["🥇", "🥈", "🥉"]
        lines = ["🏆 **GAME LEADERBOARD**\n"]
        for i, (aid, score) in enumerate(sorted_s):
            p = AGENT_PERSONALITIES[aid]
            m = medals[i] if i < 3 else f"{i+1}."
            lines.append(f"{m} {p['emoji']} **{aid.upper()}** — {score} pts")
        return "\n".join(lines)

    def _top3(self) -> str:
        top = sorted(self.scores.items(), key=lambda x: x[1], reverse=True)[:3]
        return " | ".join(f"{a.upper()}:{s}" for a, s in top if s > 0) or "sabka 0 😂"
