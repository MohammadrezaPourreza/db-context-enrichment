"""
Dimension 2 — Structural Distance
Variation in the logical complexity of the request. This is the only dimension
where the ground-truth SQL differs structurally from the anchor SQL.
  LOW    — Decompose: extract the simplest atomic sub-part.
  MEDIUM — Nest: anchor SQL becomes a subquery feeding an outer aggregation.
  HIGH   — Combine: two anchors from the same DB merged via JOIN/UNION/subquery.
"""
import json
import textwrap
from pydantic import BaseModel, Field
from dataset_generation.base import BaseDimensionGenerator, llm_call


class _StructuralResponse(BaseModel):
    question: str = Field(..., description="The variant natural language question.")
    sql: str = Field(..., description="The variant SQL query.")


_LEVEL_INSTRUCTIONS = {
    "low": textwrap.dedent("""\
        Apply a LOW-level structural transformation — DECOMPOSE:
        Extract the simplest atomic sub-part of the anchor query.
        - Remove aggregations, drop one condition, or simplify to a single-table lookup.
        - The variant should be a simpler but still meaningful question.
        - Produce a valid, simpler SQL that correctly answers the simpler variant question."""),
    "medium": textwrap.dedent("""\
        Apply a MEDIUM-level structural transformation — NEST:
        Wrap the anchor SQL as a subquery and build a more complex outer query around it.
        - The anchor SQL should feed an outer aggregation, filter, or lookup.
        - Example patterns:
            SELECT count(*) FROM (<anchor_sql>) sub
            WHERE id IN (<anchor_sql>)
        - Produce both the combined natural language question and the nested SQL."""),
    "high": textwrap.dedent("""\
        Apply a HIGH-level structural transformation — COMBINE:
        Merge the anchor with a second anchor from the same database into one query.
        - Join both information needs into a single SQL using JOIN, UNION, or a correlated subquery.
        - Produce a single natural language question that clearly asks for both pieces of information.
        - Produce a single SQL that satisfies both."""),
}


class StructuralGenerator(BaseDimensionGenerator):
    """Generates Structural Distance variants (SQL changes)."""

    DIMENSION = "structural"

    async def generate(
        self,
        anchor_question: str,
        anchor_sql: str,
        level: str,
        db_schema: str = "",
        second_anchor_json: str | None = None,
        **kwargs,
    ) -> tuple[str, str]:
        """
        Returns (variant_question, variant_sql).
        SQL structure changes at every level.
        For HIGH level, second_anchor_json must be a JSON string: {"question": "...", "sql": "..."}.
        """
        level = self._validate_level(level)

        second_section = ""
        if level == "high":
            if not second_anchor_json:
                raise ValueError(
                    "HIGH structural level requires 'second_anchor_json' — "
                    "a JSON string with keys 'question' and 'sql' from the same database."
                )
            second = json.loads(second_anchor_json)
            second_section = textwrap.dedent(f"""\
                SECOND ANCHOR (to combine with):
                Question: {second['question']}
                SQL: {second['sql']}

            """)

        prompt = textwrap.dedent(f"""\
            You are creating a structural complexity variant of a natural language database question
            to test NL2SQL robustness.

            DATABASE SCHEMA:
            {db_schema}

            ANCHOR QUESTION:
            {anchor_question}

            ANCHOR SQL:
            {anchor_sql}

            {second_section}TASK:
            {_LEVEL_INSTRUCTIONS[level]}

            Constraints:
            - The variant SQL must be valid for the given schema.
            - The variant question must be grammatically correct and unambiguous.
            - The variant must have exactly one correct SQL interpretation.

            Respond with a JSON object with keys "question" (variant NL question) and "sql" (variant SQL).
        """)
        result = await llm_call(prompt, _StructuralResponse)
        return result.question, result.sql


# Module-level convenience function used by the MCP tool
_generator = StructuralGenerator()


async def generate_structural_variant(
    anchor_question: str,
    anchor_sql: str,
    db_schema: str,
    level: str,
    second_anchor_json: str | None = None,
) -> tuple[str, str]:
    return await _generator.generate(
        anchor_question, anchor_sql, level,
        db_schema=db_schema, second_anchor_json=second_anchor_json
    )
