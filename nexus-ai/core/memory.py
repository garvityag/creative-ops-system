"""
NEXUS — Persistent Memory System
Agents remember: design styles, inside jokes, project history, preferences.
Uses ChromaDB locally — completely free.
"""

import json
import uuid
from datetime import datetime
from typing import Optional
import chromadb
from chromadb.config import Settings


class NexusMemory:
    """
    Central memory for all agents.
    Stores and retrieves context using vector similarity.
    """

    def __init__(self, db_path: str = "./nexus_memory"):
        self.client = chromadb.PersistentClient(
            path=db_path,
            settings=Settings(anonymized_telemetry=False)
        )
        self._init_collections()

    def _init_collections(self):
        """Create memory collections if they don't exist."""

        # Agent-to-agent conversations + inside jokes
        self.conversations = self.client.get_or_create_collection(
            name="conversations",
            metadata={"description": "Agent conversations, banter, inside jokes"}
        )

        # Project history — briefs, decisions, outputs
        self.projects = self.client.get_or_create_collection(
            name="projects",
            metadata={"description": "Project briefs, design decisions, outputs"}
        )

        # Design styles — colors, fonts, preferences per client
        self.design_styles = self.client.get_or_create_collection(
            name="design_styles",
            metadata={"description": "Brand styles, design preferences, references"}
        )

        # Agent personality — each agent's growing knowledge
        self.agent_knowledge = self.client.get_or_create_collection(
            name="agent_knowledge",
            metadata={"description": "Per-agent learned knowledge and preferences"}
        )

        # Task history — what worked, what didn't
        self.task_history = self.client.get_or_create_collection(
            name="task_history",
            metadata={"description": "Completed tasks, outcomes, token usage"}
        )

    # ── STORE ──────────────────────────────────────────────────

    def remember_conversation(self, agent_from: str, agent_to: str,
                               message: str, context: str = ""):
        """Store a conversation between agents (Discord banter, debates, etc.)"""
        self.conversations.add(
            documents=[message],
            metadatas=[{
                "from": agent_from,
                "to": agent_to,
                "context": context,
                "timestamp": datetime.now().isoformat(),
            }],
            ids=[str(uuid.uuid4())]
        )

    def remember_project(self, project_name: str, data: dict):
        """Store project details — brief, decisions, outputs."""
        self.projects.add(
            documents=[json.dumps(data)],
            metadatas=[{
                "project": project_name,
                "timestamp": datetime.now().isoformat(),
                "type": data.get("type", "general"),
            }],
            ids=[f"project_{project_name}_{uuid.uuid4().hex[:8]}"]
        )

    def remember_design_style(self, client_name: str, style_data: dict):
        """Store brand/design style for a client."""
        style_text = f"""
        Client: {client_name}
        Colors: {style_data.get('colors', [])}
        Fonts: {style_data.get('fonts', [])}
        Tone: {style_data.get('tone', '')}
        References: {style_data.get('references', [])}
        """
        self.design_styles.add(
            documents=[style_text],
            metadatas=[{
                "client": client_name,
                "timestamp": datetime.now().isoformat(),
                **{k: str(v) for k, v in style_data.items()},
            }],
            ids=[f"style_{client_name}_{uuid.uuid4().hex[:8]}"]
        )

    def agent_learned(self, agent_id: str, knowledge: str, category: str = "general"):
        """Agent learned something new — store it."""
        self.agent_knowledge.add(
            documents=[knowledge],
            metadatas=[{
                "agent": agent_id,
                "category": category,
                "timestamp": datetime.now().isoformat(),
            }],
            ids=[f"know_{agent_id}_{uuid.uuid4().hex[:8]}"]
        )

    def log_task(self, task_id: str, agent: str, model: str,
                  task: str, result: str, tokens_used: int, cost_usd: float):
        """Log every completed task for dashboard tracking."""
        self.task_history.add(
            documents=[f"Task: {task}\nResult: {result}"],
            metadatas=[{
                "task_id": task_id,
                "agent": agent,
                "model": model,
                "tokens": tokens_used,
                "cost_usd": cost_usd,
                "timestamp": datetime.now().isoformat(),
                "status": "completed",
            }],
            ids=[task_id]
        )

    # ── RECALL ─────────────────────────────────────────────────

    def recall(self, query: str, collection: str = "projects",
               n_results: int = 5, agent_filter: Optional[str] = None) -> list[dict]:
        """Search memory by semantic similarity."""
        coll = getattr(self, collection, self.projects)
        where = {"agent": agent_filter} if agent_filter else None

        try:
            results = coll.query(
                query_texts=[query],
                n_results=n_results,
                where=where,
            )
            memories = []
            for i, doc in enumerate(results["documents"][0]):
                memories.append({
                    "content": doc,
                    "metadata": results["metadatas"][0][i],
                    "distance": results["distances"][0][i] if results.get("distances") else None,
                })
            return memories
        except Exception:
            return []

    def get_design_style(self, client_name: str) -> Optional[dict]:
        """Get stored design style for a client."""
        results = self.design_styles.query(
            query_texts=[client_name],
            n_results=1,
        )
        if results["documents"][0]:
            return {
                "content": results["documents"][0][0],
                "metadata": results["metadatas"][0][0],
            }
        return None

    def get_agent_knowledge(self, agent_id: str, topic: str) -> list[dict]:
        """Get what an agent knows about a topic."""
        return self.recall(topic, "agent_knowledge", agent_filter=agent_id)

    def get_recent_tasks(self, limit: int = 20) -> list[dict]:
        """Get recent task history for dashboard."""
        try:
            results = self.task_history.get(limit=limit, include=["documents", "metadatas"])
            tasks = []
            for i, doc in enumerate(results["documents"]):
                tasks.append({
                    "content": doc,
                    "metadata": results["metadatas"][i],
                })
            return sorted(tasks, key=lambda x: x["metadata"].get("timestamp", ""), reverse=True)
        except Exception:
            return []

    def get_stats(self) -> dict:
        """Memory stats for dashboard."""
        return {
            "conversations": self.conversations.count(),
            "projects": self.projects.count(),
            "design_styles": self.design_styles.count(),
            "agent_knowledge": self.agent_knowledge.count(),
            "task_history": self.task_history.count(),
        }


# Global memory instance
memory = NexusMemory()
