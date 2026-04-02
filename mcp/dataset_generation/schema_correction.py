"""
Dimension 5 — Schema Correction Distance
Typos or fuzzy references to schema terms (table/column names) are introduced
into the question. The variant SQL is always identical to the anchor SQL.

  LOW    — Case changes + inserted spaces  (e.g. "accounts" → "Ac counts")
  MEDIUM — Abbreviation substitution       (e.g. "accounts" → "accts")
  HIGH   — Character-level typos           (e.g. "account"  → "acount")

The pipeline has two stages:
  1. LLM extracts schema tokens referenced in the question (can be pre-supplied).
  2. Programmatic mutation is applied based on the chosen level.
"""
import json
import random
import textwrap
from typing import List
from pydantic import BaseModel, Field
from dataset_generation.base import BaseDimensionGenerator, llm_call


# ── Abbreviation table (MEDIUM level) ────────────────────────────────────────
# Abbreviations are generated on-demand by the LLM (see _abbreviate_token below).


# ── Internal schema-term model ────────────────────────────────────────────────

class _SchemaTerm(BaseModel):
    schema_term: str = Field(..., description="The actual schema table or column name.")
    question_token: str = Field(..., description="The exact word/phrase as it appears in the question.")
    term_type: str = Field(..., description="'table' or 'column'")


class _SchemaTermsList(BaseModel):
    terms: List[_SchemaTerm]


# ── Mutation strategies ───────────────────────────────────────────────────────

def _mutate_low(token: str) -> str:
    """Insert a space at the midpoint and capitalise the first half."""
    if len(token) < 3:
        return token.capitalize()
    mid = len(token) // 2
    return token[:mid].capitalize() + " " + token[mid:]


class _AbbreviationResponse(BaseModel):
    abbreviation: str = Field(
        ...,
        description="A common abbreviation or shortened form of the given word.",
    )


async def _abbreviate_token(token: str) -> str:
    """
    Ask a lightweight LLM to produce a natural abbreviation for a schema term.
    Falls back to dropping the last two characters if the model returns the
    same string unchanged.
    """
    prompt = textwrap.dedent(f"""\
        A database user is typing quickly and abbreviates schema terms.
        Provide a single common abbreviation or shortened form for the word below,
        as a domain user might type it (e.g. "accounts" → "accts", "amount" → "amt",
        "employee" → "emp", "transaction" → "txn").
        If no natural abbreviation exists, shorten by dropping the last few characters.
        Return ONLY the abbreviation, nothing else.

        Word: {token}
    """)
    result = await llm_call(prompt, _AbbreviationResponse, lightweight=True)
    abbr = result.abbreviation.strip()
    # Sanity guard: if the LLM returns the original unchanged, truncate instead
    if abbr.lower() == token.lower():
        return token[: max(3, len(token) - 2)]
    return abbr


def _mutate_high(token: str, rng: random.Random) -> str:
    """Apply a random character-level typo."""
    if len(token) < 2:
        return token
    ops = ["delete_char", "swap_adjacent", "double_char"]
    op = rng.choice(ops)
    idx = rng.randint(0, len(token) - 1)
    if op == "delete_char":
        return token[:idx] + token[idx + 1 :]
    if op == "swap_adjacent" and idx < len(token) - 1:
        chars = list(token)
        chars[idx], chars[idx + 1] = chars[idx + 1], chars[idx]
        return "".join(chars)
    # double_char
    return token[:idx] + token[idx] + token[idx:]


# ── LLM schema-term extractor ─────────────────────────────────────────────────

async def _extract_schema_terms(anchor_question: str, db_schema: str) -> List[_SchemaTerm]:
    """Ask a lightweight LLM to identify which schema terms appear in the question."""
    prompt = textwrap.dedent(f"""\
        Identify all database schema terms (table names or column names) that are explicitly
        referenced or clearly implied in the following natural language question, given the schema.

        DATABASE SCHEMA:
        {db_schema}

        QUESTION:
        {anchor_question}

        Return a JSON object with key "terms". Each item must have:
        - "schema_term":    the actual table or column name from the schema
        - "question_token": the exact word or phrase used in the question
        - "term_type":      "table" or "column"

        If no schema terms are explicitly referenced, return an empty list.
    """)
    result = await llm_call(prompt, _SchemaTermsList, lightweight=True)
    return result.terms


# ── Public API ────────────────────────────────────────────────────────────────

class SchemaCorrectionGenerator(BaseDimensionGenerator):
    """Generates Schema Correction Distance variants (programmatic mutations, SQL invariant)."""

    DIMENSION = "schema_correction"

    async def generate(
        self,
        anchor_question: str,
        anchor_sql: str,
        level: str,
        db_schema: str = "",
        schema_terms_json: str | None = None,
        seed: int | None = None,
        **kwargs,
    ) -> tuple[str, str]:
        """
        Returns (variant_question, variant_sql).
        variant_sql is always identical to anchor_sql.

        schema_terms_json (optional): pre-extracted terms as a JSON list of
            {"schema_term", "question_token", "term_type"} objects. If omitted
            the LLM extracts them automatically.

        seed: optional integer seed for reproducible character-level mutations (HIGH level).
        """
        level = self._validate_level(level)

        if schema_terms_json:
            raw = json.loads(schema_terms_json)
            terms = [_SchemaTerm(**t) for t in raw]
        else:
            terms = await _extract_schema_terms(anchor_question, db_schema)

        if not terms:
            raise ValueError(
                "No schema terms found in the question. "
                "Schema correction variant is not applicable for this anchor."
            )

        rng = random.Random(seed)
        variant_question = anchor_question

        for term in terms:
            if level == "low":
                mutated = _mutate_low(term.question_token)
            elif level == "medium":
                mutated = await _abbreviate_token(term.question_token)
            else:  # high
                mutated = _mutate_high(term.question_token, rng)
            variant_question = variant_question.replace(term.question_token, mutated, 1)

        return variant_question, anchor_sql


# Module-level convenience function used by the MCP tool
_generator = SchemaCorrectionGenerator()


async def generate_schema_correction_variant(
    anchor_question: str,
    anchor_sql: str,
    db_schema: str,
    level: str,
    schema_terms_json: str | None = None,
) -> tuple[str, str]:
    return await _generator.generate(
        anchor_question, anchor_sql, level,
        db_schema=db_schema, schema_terms_json=schema_terms_json
    )
