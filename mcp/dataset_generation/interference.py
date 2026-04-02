"""
Dimension 3 — Interference Distance
Conversational noise is injected into the question; the core analytical intent
remains unchanged. The variant SQL is always identical to the anchor SQL.
  LOW    — Politeness fillers.
  MEDIUM — Business-context backstory prepended before the real question.
  HIGH   — Red-herring schema distractors + a contradictory-sounding override.
"""
import textwrap
from pydantic import BaseModel, Field
from dataset_generation.base import BaseDimensionGenerator, llm_call


class _InterferenceResponse(BaseModel):
    question: str = Field(..., description="The variant question with injected noise.")


_LEVEL_INSTRUCTIONS = {
    "low": textwrap.dedent("""\
        Apply a LOW-level interference transformation (politeness fillers):
        - Add a polite opener or closer to the question.
        - Examples: "Hi, could you please...", "Thanks in advance, but...",
          "Hey, I was wondering if you could..."
        - The core analytical intent must be completely unchanged."""),
    "medium": textwrap.dedent("""\
        Apply a MEDIUM-level interference transformation (business-context backstory):
        - Prepend 2–3 sentences of fictional but plausible business justification
          before the actual question.
        - Example: "We are preparing the quarterly board report and need to review
          our loan portfolio. As part of this review, we need to identify client
          accounts for an upcoming audit. <original question>"
        - The business context must be irrelevant to the SQL logic.
        - The core analytical intent must remain unchanged and clearly recoverable."""),
    "high": textwrap.dedent("""\
        Apply a HIGH-level interference transformation (red-herring schema distractors):
        - Mention 1–2 real table or column names from the schema that are IRRELEVANT
          to answering the question, framed as things to "ignore" or "not consider".
        - Additionally include a contradictory-sounding instruction that, on closer
          reading, resolves to the same logic as the anchor
          (e.g. "...but do not filter by status" when status was never in the anchor).
        - The SQL must remain identical to the anchor.
        - A careful reader must still be able to recover the core question intent."""),
}


class InterferenceGenerator(BaseDimensionGenerator):
    """Generates Interference Distance variants (SQL invariant)."""

    DIMENSION = "interference"

    async def generate(
        self,
        anchor_question: str,
        anchor_sql: str,
        level: str,
        db_schema: str = "",
        **kwargs,
    ) -> tuple[str, str]:
        """
        Returns (variant_question, variant_sql).
        variant_sql is always identical to anchor_sql.
        """
        level = self._validate_level(level)
        prompt = textwrap.dedent(f"""\
            You are creating an interference variant of a natural language database question
            to test NL2SQL robustness.

            DATABASE SCHEMA:
            {db_schema}

            ANCHOR QUESTION:
            {anchor_question}

            ANCHOR SQL (the correct answer — your variant question must still map to this exact SQL):
            {anchor_sql}

            TASK:
            {_LEVEL_INSTRUCTIONS[level]}

            Respond with a JSON object containing only the key "question" with the modified
            question as its value.
        """)
        result = await llm_call(prompt, _InterferenceResponse)
        return result.question, anchor_sql


# Module-level convenience function used by the MCP tool
_generator = InterferenceGenerator()


async def generate_interference_variant(
    anchor_question: str,
    anchor_sql: str,
    db_schema: str,
    level: str,
) -> tuple[str, str]:
    return await _generator.generate(anchor_question, anchor_sql, level, db_schema=db_schema)
