"""
NEXUS — Model Registry
Defines all available models, their capabilities, costs, and fallback chain.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ModelProvider(Enum):
    CLAUDE    = "claude"
    OPENAI    = "openai"      # Phase 2
    GEMINI    = "gemini"      # Phase 2
    OLLAMA    = "ollama"      # Always free
    LOCAL     = "local"


class TaskType(Enum):
    REASONING      = "reasoning"       # Complex thinking, strategy
    CREATIVE       = "creative"        # Design concepts, ideation
    CODING         = "coding"          # Code generation
    IMAGE_GEN      = "image_gen"       # Image creation
    CHAT           = "chat"            # Casual conversation
    SUMMARIZE      = "summarize"       # Quick summaries
    ROAST          = "roast"           # Discord banter, dark humor


@dataclass
class ModelConfig:
    name: str
    provider: ModelProvider
    model_id: str
    cost_per_1k_tokens: float          # USD, 0 = free
    max_tokens: int
    supports_images: bool = False
    supports_tools: bool = False
    local: bool = False                # Runs on local machine
    best_for: list[TaskType] = field(default_factory=list)
    available: bool = True             # Set False if key missing


# ── MODEL REGISTRY ────────────────────────────────────────────
MODELS = {
    # Claude — Phase 1
    "claude-sonnet": ModelConfig(
        name="Claude Sonnet 4",
        provider=ModelProvider.CLAUDE,
        model_id="claude-sonnet-4-20250514",
        cost_per_1k_tokens=0.003,
        max_tokens=8096,
        supports_images=True,
        supports_tools=True,
        best_for=[TaskType.REASONING, TaskType.CREATIVE, TaskType.SUMMARIZE],
    ),
    "claude-haiku": ModelConfig(
        name="Claude Haiku",
        provider=ModelProvider.CLAUDE,
        model_id="claude-haiku-4-5-20251001",
        cost_per_1k_tokens=0.00025,
        max_tokens=4096,
        supports_tools=True,
        best_for=[TaskType.SUMMARIZE, TaskType.CHAT],
    ),

    # Ollama — Phase 1 (always available, free)
    "phi3-mini": ModelConfig(
        name="Phi-3 Mini",
        provider=ModelProvider.OLLAMA,
        model_id="phi3:mini",
        cost_per_1k_tokens=0.0,
        max_tokens=4096,
        local=True,
        best_for=[TaskType.CHAT, TaskType.SUMMARIZE, TaskType.CODING],
    ),
    "tinydolphin": ModelConfig(
        name="TinyDolphin",
        provider=ModelProvider.OLLAMA,
        model_id="tinydolphin",
        cost_per_1k_tokens=0.0,
        max_tokens=2048,
        local=True,
        best_for=[TaskType.ROAST, TaskType.CHAT],
    ),
    "openhermes": ModelConfig(
        name="OpenHermes",
        provider=ModelProvider.OLLAMA,
        model_id="openhermes",
        cost_per_1k_tokens=0.0,
        max_tokens=4096,
        local=True,
        best_for=[TaskType.CREATIVE, TaskType.CHAT],
    ),

    # OpenAI — Phase 2
    "gpt4o": ModelConfig(
        name="GPT-4o",
        provider=ModelProvider.OPENAI,
        model_id="gpt-4o",
        cost_per_1k_tokens=0.005,
        max_tokens=8096,
        supports_images=True,
        supports_tools=True,
        best_for=[TaskType.CODING, TaskType.REASONING],
        available=False,               # Enable in Phase 2
    ),

    # Gemini — Phase 2
    "gemini-pro": ModelConfig(
        name="Gemini 1.5 Pro",
        provider=ModelProvider.GEMINI,
        model_id="gemini-1.5-pro",
        cost_per_1k_tokens=0.0,        # Free tier = very generous
        max_tokens=8096,
        supports_images=True,
        best_for=[TaskType.IMAGE_GEN, TaskType.REASONING],
        available=False,               # Enable in Phase 2
    ),
}


# ── FALLBACK CHAIN ────────────────────────────────────────────
# When a model fails or hits limit, try next in chain
FALLBACK_CHAIN = {
    TaskType.REASONING:  ["claude-sonnet", "gpt4o",   "gemini-pro", "phi3-mini"],
    TaskType.CREATIVE:   ["claude-sonnet", "gemini-pro","openhermes", "phi3-mini"],
    TaskType.CODING:     ["claude-sonnet", "gpt4o",   "phi3-mini"],
    TaskType.IMAGE_GEN:  ["gemini-pro",   "gpt4o",   "phi3-mini"],
    TaskType.CHAT:       ["claude-haiku", "phi3-mini","tinydolphin"],
    TaskType.SUMMARIZE:  ["claude-haiku", "phi3-mini"],
    TaskType.ROAST:      ["tinydolphin", "openhermes","phi3-mini"],
}


def get_best_model(task: TaskType, budget_conscious: bool = False) -> ModelConfig:
    """Get best available model for a task type."""
    chain = FALLBACK_CHAIN.get(task, ["claude-haiku", "phi3-mini"])
    for model_key in chain:
        model = MODELS.get(model_key)
        if model and model.available:
            if budget_conscious and model.cost_per_1k_tokens > 0:
                continue          # Skip paid models in budget mode
            return model
    return MODELS["phi3-mini"]   # Ultimate fallback — always free
