"""
Dimension 1 — Lexical Distance
Variation in natural language phrasing, style, or vocabulary without altering
the underlying SQL logic or any data values. The variant SQL is always identical
to the anchor SQL.
"""
import textwrap
from pydantic import BaseModel, Field
from dataset_generation.base import BaseDimensionGenerator, llm_call


class _LexicalResponse(BaseModel):
    question: str = Field(..., description="The rephrased natural language question.")


_LEVEL_INSTRUCTIONS = {
    "low": textwrap.dedent("""\
        Apply a LOW-level lexical transformation (syntactic paraphrase):
        - Reorder clauses, switch active↔passive voice, or substitute formal synonyms.
        - Do NOT change any named entities, data values, or filtering conditions.
        - The underlying SQL logic must be completely unchanged."""),
    "medium": textwrap.dedent("""\
        Apply a MEDIUM-level lexical transformation (domain-jargon substitution):
        - Replace domain-specific terms with professional equivalents
          (e.g. "opening date" → "inception date", "loan validity" → "credit tenure").
        - Keep all named entities and data values frozen.
        - The underlying SQL logic must be completely unchanged."""),
    "high": textwrap.dedent("""\
        Apply a HIGH-level lexical transformation (slang / idiomatic / heavily abbreviated):
        - Rewrite in power-user chat phrasing
          (e.g. "Gimme pre-97 accts with >24mo loans at rock-bottom approval amounts").
        - All data values must remain present but may be abbreviated
          (e.g. "before 1997" → "pre-97", "more than 24 months" → ">24mo").
        - The underlying SQL logic must be completely unchanged."""),
}


class LexicalGenerator(BaseDimensionGenerator):
    """Generates Lexical Distance variants (SQL invariant)."""

    DIMENSION = "lexical"

    async def generate(
        self,
        anchor_question: str,
        anchor_sql: str,
        level: str,
        **kwargs,
    ) -> tuple[str, str]:
        """
        Returns (variant_question, variant_sql).
        variant_sql is always identical to anchor_sql.
        """
        level = self._validate_level(level)
        prompt = textwrap.dedent(f"""\
            You are rewriting a natural language database question to test NL2SQL robustness.

            ANCHOR QUESTION:
            {anchor_question}

            ANCHOR SQL (for reference — the SQL logic must not change):
            {anchor_sql}

            TASK:
            {_LEVEL_INSTRUCTIONS[level]}

            Respond with a JSON object containing only the key "question" with the rewritten
            question as its value. Do NOT include any explanation.
        """)
        result = await llm_call(prompt, _LexicalResponse)
        return result.question, anchor_sql


# Module-level convenience function used by the MCP tool
_generator = LexicalGenerator()


async def generate_lexical_variant(
    anchor_question: str,
    anchor_sql: str,
    level: str,
) -> tuple[str, str]:
    return await _generator.generate(anchor_question, anchor_sql, level)
