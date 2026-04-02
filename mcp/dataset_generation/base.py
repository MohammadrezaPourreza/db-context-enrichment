"""
Shared base class and configuration for all dataset-generation dimension modules.

Setting the model name
----------------------
Import `set_generation_model` (or `set_lightweight_model`) in main.py and call
them at startup before any tool is invoked:

    from dataset_generation.base import set_generation_model, set_lightweight_model
    set_generation_model("gemini-2.5-pro")
    set_lightweight_model("gemini-2.5-flash")

The heavy model is used for creative generation (lexical, structural,
interference, value substitution, schema correction, judging).
The lightweight model is used for cheap extraction tasks (slot extraction,
schema-term extraction).
"""

import textwrap
from abc import ABC, abstractmethod
from typing import Type, TypeVar
from pydantic import BaseModel
from google import genai

# ── Module-level model names (override via set_* functions) ──────────────────

_GENERATION_MODEL: str = "gemini-2.5-pro"
_LIGHTWEIGHT_MODEL: str = "gemini-2.5-flash"

def set_generation_model(model_name: str) -> None:
    """Set the model used for all creative generation and judging steps."""
    global _GENERATION_MODEL
    _GENERATION_MODEL = model_name


def set_lightweight_model(model_name: str) -> None:
    """Set the model used for cheap extraction steps (slot/schema-term extraction)."""
    global _LIGHTWEIGHT_MODEL
    _LIGHTWEIGHT_MODEL = model_name


def get_generation_model() -> str:
    return _GENERATION_MODEL


def get_lightweight_model() -> str:
    return _LIGHTWEIGHT_MODEL


# ── Typed helper for structured LLM calls ────────────────────────────────────

T = TypeVar("T", bound=BaseModel)


async def llm_call(prompt: str, schema: Type[T], lightweight: bool = False) -> T:
    """
    Make a single structured LLM call and return a validated Pydantic response.

    Args:
        prompt:      The prompt text.
        schema:      The Pydantic model class to use as the response schema.
        lightweight: If True, use the lightweight model; otherwise the generation model.

    Returns:
        A validated instance of `schema`.
    """
    model = _LIGHTWEIGHT_MODEL if lightweight else _GENERATION_MODEL
    client = genai.Client()
    try:
        response = await client.aio.models.generate_content(
            model=model,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": schema,
            },
        )
        return schema.model_validate_json(response.text)
    finally:
        client.close()
        await client.aio.aclose()


# ── Abstract base for every dimension generator ───────────────────────────────

class BaseDimensionGenerator(ABC):
    """
    Abstract base class that every dimension generator must subclass.

    Enforces a common interface:
      - `DIMENSION` class attribute — string identifier (e.g. "lexical")
      - `VALID_LEVELS` class attribute — frozenset of accepted level strings
      - `generate(anchor_question, anchor_sql, level, **kwargs)` — async method
        returning (variant_question, variant_sql)
    """

    DIMENSION: str
    VALID_LEVELS: frozenset = frozenset({"low", "medium", "high"})

    def _validate_level(self, level: str) -> str:
        level = level.lower()
        if level not in self.VALID_LEVELS:
            raise ValueError(
                f"Invalid level '{level}' for dimension '{self.DIMENSION}'. "
                f"Must be one of: {', '.join(sorted(self.VALID_LEVELS))}."
            )
        return level

    @abstractmethod
    async def generate(
        self,
        anchor_question: str,
        anchor_sql: str,
        level: str,
        **kwargs,
    ) -> tuple[str, str]:
        """
        Generate a variant for the given anchor and level.

        Returns:
            (variant_question, variant_sql)
        """
