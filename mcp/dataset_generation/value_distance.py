"""
Dimension 4 — Value Distance
SQL structure is preserved; WHERE/HAVING literals and the NL surface forms of
values change. Tests whether systems generalise filter patterns to new values.
  LOW    — Surface synonym/abbreviation of existing values only (SQL identical).
  MEDIUM — Full value substitution using real DB values (SQL literals updated).
  HIGH   — Value substitution + surface reword in the NL question (SQL literals updated).

For MEDIUM and HIGH the caller must first fetch candidate values by running
  SELECT DISTINCT <column> FROM <table>
for each relevant column and supply the results via `candidate_values_json`.
"""
import json
import textwrap
from typing import List
from pydantic import BaseModel, Field
from dataset_generation.base import BaseDimensionGenerator, llm_call


# ── Internal response schemas ─────────────────────────────────────────────────

class _ValueSlot(BaseModel):
    table: str
    column: str
    operator: str
    value_literal: str


class _ValueSlotsList(BaseModel):
    slots: List[_ValueSlot]


class _ValueVariantResponse(BaseModel):
    question: str = Field(..., description="The variant NL question.")
    sql: str = Field(..., description="The variant SQL (structure preserved, literals updated).")


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _extract_value_slots(anchor_sql: str) -> List[_ValueSlot]:
    """Ask a lightweight LLM to identify WHERE/HAVING literal slots in the SQL."""
    prompt = textwrap.dedent(f"""\
        Extract all literal value slots from the WHERE and HAVING clauses of this SQL query.
        For each slot return the table name, column name, comparison operator, and the literal value.

        SQL:
        {anchor_sql}

        Return a JSON object with key "slots" containing a list of objects, each with keys:
        "table", "column", "operator", "value_literal".
        If there are no WHERE/HAVING literal values, return an empty list.
    """)
    result = await llm_call(prompt, _ValueSlotsList, lightweight=True)
    return result.slots


# ── Public API ────────────────────────────────────────────────────────────────

class ValueGenerator(BaseDimensionGenerator):
    """Generates Value Distance variants (SQL structure preserved, literals change)."""

    DIMENSION = "value"

    async def generate(
        self,
        anchor_question: str,
        anchor_sql: str,
        level: str,
        candidate_values_json: str | None = None,
        **kwargs,
    ) -> tuple[str, str]:
        """
        Returns (variant_question, variant_sql).

        candidate_values_json (required for MEDIUM/HIGH):
            JSON string mapping "table.column" → list of real DB values, e.g.
            '{"loans.duration": ["12", "24", "36", "60"]}'
            Obtain these by executing  SELECT DISTINCT <column> FROM <table>  for each
            relevant column before calling this function.
        """
        level = self._validate_level(level)

        if level == "low":
            prompt = textwrap.dedent(f"""\
                You are creating a LOW-level value distance variant of a NL database question.

                ANCHOR QUESTION:
                {anchor_question}

                ANCHOR SQL (DO NOT change the SQL — it must remain identical):
                {anchor_sql}

                TASK:
                Reword only the *surface phrasing* of data values in the question using synonyms
                or abbreviations. The underlying SQL and all actual filter values stay identical.
                - Examples: "more than 24 months" → ">2 years", "before 1997" → "pre-97",
                  "United States" → "US"
                - No new conditions may be added or removed.

                Respond with JSON: {{"question": "<reworded question>", "sql": "<identical to anchor SQL>"}}
            """)
        else:
            if not candidate_values_json:
                raise ValueError(
                    f"'{level}' level requires 'candidate_values_json' — a JSON mapping "
                    "\"table.column\" → list of real DB values. "
                    "Fetch these by running SELECT DISTINCT on each relevant column first."
                )
            candidates = json.loads(candidate_values_json)
            slots = await _extract_value_slots(anchor_sql)
            if not slots:
                raise ValueError(
                    "No WHERE/HAVING literal slots found in anchor SQL. "
                    "Value substitution is not applicable for this anchor."
                )

            slots_info = "\n".join(
                f"  - {s.table}.{s.column} {s.operator} '{s.value_literal}' "
                f"→ available candidates: {candidates.get(f'{s.table}.{s.column}', ['(none provided)'])}"
                for s in slots
            )
            surface_reword_instruction = ""
            if level == "high":
                surface_reword_instruction = (
                    "\n- Additionally, reword the *new* substituted values in the question "
                    "using synonyms or abbreviations to compound the surface mismatch "
                    "(e.g. if the replacement value is '60', write 'over 5 years' rather than "
                    "'more than 60 months')."
                )
            prompt = textwrap.dedent(f"""\
                You are creating a {level.upper()}-level value distance variant of a NL database question.

                ANCHOR QUESTION:
                {anchor_question}

                ANCHOR SQL:
                {anchor_sql}

                VALUE SLOTS TO SUBSTITUTE (with real candidate values from the database):
                {slots_info}

                TASK:
                - Replace EVERY value slot with a DIFFERENT value chosen from the provided candidates.
                - Rewrite the natural language question to reflect the new values.
                - Update the SQL by replacing the old literal strings with the chosen new values.
                - Keep the SQL structure (joins, aggregations, column references) completely identical.{surface_reword_instruction}

                Respond with JSON: {{"question": "...", "sql": "..."}}
            """)

        result = await llm_call(prompt, _ValueVariantResponse)
        return result.question, result.sql


# Module-level convenience function used by the MCP tool
_generator = ValueGenerator()


async def generate_value_variant(
    anchor_question: str,
    anchor_sql: str,
    level: str,
    candidate_values_json: str | None = None,
) -> tuple[str, str]:
    return await _generator.generate(
        anchor_question, anchor_sql, level, candidate_values_json=candidate_values_json
    )
