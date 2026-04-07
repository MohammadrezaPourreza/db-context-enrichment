from fastmcp import FastMCP
from typing import List
import asyncio
import textwrap
from template import question_generator, template_generator
from facet import facet_generator
from value_search import generator as vi_generator
from value_search import match_templates
from model import context
import prompts
import datetime
import os
import json
from bootstrap import bootstrap_generator
from dataset_generation import (
    lexical as lexical_gen,
    structural as structural_gen,
    interference as interference_gen,
    value_distance as value_gen,
    schema_correction as schema_correction_gen,
)
from dataset_generation.base import (
    set_generation_model,
    set_lightweight_model,
    llm_call,
)
from pydantic import BaseModel, Field

mcp = FastMCP("DB Context Enrichment MCP")


@mcp.tool
async def generate_sql_pairs(
    db_schema: str,
    context: str | None = None,
    table_names: List[str] | None = None,
    sql_dialect: str | None = None,
) -> str:
    """
    Generates a list of question/SQL pairs based on a database schema.

    Args:
        db_schema: A string containing the database schema.
        context: Optional user feedback or context to guide generation.
        table_names: Optional list of table names to focus on. If the user
          mentions all tables, ignore this field. The default behavior is to use
          all tables for the pair generation.
        sql_dialect: Optional name of the database engine for SQL dialect.

    Returns:
        A JSON string representing a list of dictionaries, where each dictionary
        has a "question" and a "sql" key.
        Example: '[{"question": "...", "sql": "..."}]'
    """
    return await question_generator.generate_sql_pairs(
        db_schema, context, table_names, sql_dialect
    )


@mcp.tool
async def generate_templates(
    template_inputs_json: str, sql_dialect: str = "postgresql"
) -> str:
    """
    Generates final templates from a list of user-approved template question, template SQL statement, and optional template intent.

    Args:
        template_inputs_json: A JSON string representing a list of dictionaries (template inputs),
                             where each dictionary has "question", "sql", and optional "intent" keys.
                             Example (with intent): '[{"question": "How many users?", "sql": "SELECT count(*) FROM users", "intent": "Count total users"}]'
                             Example (default intent): '[{"question": "List all items", "sql": "SELECT * FROM items"}]'
        sql_dialect: The SQL dialect to use for parameterization. Accepted
                   values are 'postgresql' (default), 'mysql', or 'googlesql'.

    Returns:
        A JSON string representing a ContextSet object.
    """
    return await template_generator.generate_templates(
        template_inputs_json, sql_dialect
    )


@mcp.tool
async def generate_facets(
    facet_inputs_json: str, sql_dialect: str = "postgresql"
) -> str:
    """
    Generates final facets from a list of user-approved facet intent and facet SQL snippet.

    Args:
        facet_inputs_json: A JSON string representing a list of dictionaries (facet inputs),
                             where each dictionary has "intent" and "sql_snippet".
                             Example: '[{"intent": "high price", "sql_snippet": "price > 1000"}]'
        sql_dialect: The SQL dialect to use for parameterization. Accepted
                   values are 'postgresql' (default), 'mysql', or 'googlesql'.

    Returns:
        A JSON string representing a ContextSet object.
    """
    return await facet_generator.generate_facets(
        facet_inputs_json, sql_dialect
    )


@mcp.tool
async def generate_bootstrap_context(
    output_file_path: str,
    template_inputs_json: str | None = None,
    facet_inputs_json: str | None = None,
    sql_dialect: str = "postgresql"
) -> str:
    """
    Generates a single unified ContextSet from key information and saves it to a file.

    Args:
        output_file_path: The absolute path where the JSON ContextSet file should be saved.
        template_inputs_json: A JSON string representing a list of extracted seed information used to generate full templates.
            Each item in the list should be a dictionary with keys:
            - "question": The natural language question.
            - "sql": The corresponding SQL query to answer the question.
            - "intent": (Optional) A brief description of the intent.
            
            Example: 
            '[{"question": "How many users?", "sql": "SELECT COUNT(*) FROM users", "intent": "Count total users"}]'
            
        facet_inputs_json: A JSON string representing a list of extracted seed information used to generate full facets.
            Each item in the list should be a dictionary with keys:
            - "intent": A brief description of the facet intent.
            - "sql_snippet": A specific SQL fragment (such as a filter condition) representing the intent.
            
            Example: 
            '[{"intent": "high price", "sql_snippet": "price > 1000"}]'
        sql_dialect: SQL engine dialect.
        
    Returns:
        The absolute file path pointing to the generated and saved ContextSet JSON.
    """
    return await bootstrap_generator.generate_context(
        output_file_path, sql_dialect, template_inputs_json, facet_inputs_json
    )


@mcp.tool
async def generate_value_searches(
    value_search_inputs_json: str,
    db_engine: str,
    db_version: str | None = None,
) -> str:
    """
    Generates final value searches from a list of user-approved value search definitions.

    Args:
        value_search_inputs_json: A JSON string representing a list of value search definitions.
            Each item in the list should be a dictionary with keys:
            - "table_name": The name of the table.
            - "column_name": The name of the column.
            - "concept_type": The semantic type (e.g., 'City').
            - "match_function": The match function to use (e.g., 'EXACT_MATCH_STRINGS').
            - "description": (Optional) A description of the value search.
            
            Example:
            '[
                {"table_name": "users", "column_name": "city", "concept_type": "City", "match_function": "EXACT_MATCH_STRINGS"},
                {"table_name": "products", "column_name": "name", "concept_type": "Product", "match_function": "FUZZY_MATCH_STRINGS"}
            ]'
            
        db_engine: The database engine (postgresql, mysql, etc.).
        db_version: The database version (optional).
        
    Returns:
        A JSON string representing a ContextSet object containing all the new value searches.
    """
    if db_version and not db_version.strip():
        db_version = None
    
    return vi_generator.generate_value_searches(
        value_search_inputs_json, db_engine, db_version
    )

@mcp.tool
def list_match_functions(db_engine: str, db_version: str | None = None) -> str:
    """
    Lists the valid match template functions with their descriptions and examples for a specific database engine.
    Use this to show the user what 'match_function' options are available, along with their details.
    
    If the engine or version is not supported, this will return an error message
    listing the valid options.

    Args:
        db_engine: The database engine (e.g., 'postgresql').
        db_version: The specific database version (optional).
    
    Returns:
        A JSON string containing a dictionary of available function names mapped to their descriptions and examples,
        or an error message if validation fails.
    """
    try:
        functions = match_templates.get_available_functions(db_engine, db_version)
        return json.dumps(functions)
    except ValueError as e:
        return f"Error: {str(e)}"

@mcp.tool
def save_context_set(
    context_set_json: str,
    db_instance: str,
    db_name: str,
    output_dir: str,
) -> str:
    """
    Saves a ContextSet to a new JSON file with a generated timestamp.

    Args:
        context_set_json: The JSON string of the ContextSet.
        db_instance: The database instance name.
        db_name: The database name.
        output_dir: The directory to save the file in. The root of where the
          Gemini CLI is running.

    Returns:
        A confirmation message with the path to the newly created file.
    """
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    filename = f"{db_instance}_{db_name}_context_set_{timestamp}.json"
    filepath = os.path.join(output_dir, filename)

    try:
        data = json.loads(context_set_json)
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
        return f"Successfully saved context set to {filepath}"
    except (json.JSONDecodeError, IOError) as e:
        return f"Error saving file: {e}"


@mcp.tool
def attach_context_set(
    context_set_json: str,
    file_path: str,
) -> str:
    """
    Attaches a ContextSet to an existing JSON file.

    This tool reads an existing JSON file containing a ContextSet,
    appends new templates/facets/value_searches to it, and writes the updated ContextSet
    back to the file. Exceptions are propagated to the caller.

    Args:
        context_set_json: The JSON string output from the generation tools.
        file_path: The **absolute path** to the existing template file.

    Returns:
        A confirmation message with the path to the updated file.
    """

    existing_content_dict = {"templates": [], "facets": [], "value_searches": []}
    if os.path.getsize(file_path) > 0:
        with open(file_path, "r") as f:
            existing_content_dict = json.load(f)

    existing_context = context.ContextSet(**existing_content_dict)

    new_context = context.ContextSet(**json.loads(context_set_json))

    if existing_context.templates is None:
        existing_context.templates = []
    if new_context.templates:
        existing_context.templates.extend(new_context.templates)

    if existing_context.facets is None:
        existing_context.facets = []
    if new_context.facets:
        existing_context.facets.extend(new_context.facets)

    if existing_context.value_searches is None:
        existing_context.value_searches = []
    if new_context.value_searches:
        existing_context.value_searches.extend(new_context.value_searches)

    with open(file_path, "w") as f:
        json.dump(existing_context.model_dump(), f, indent=2)

    return f"Successfully attached context to {file_path}"


@mcp.tool
def generate_upload_url(
    db_type: str,
    project_id: str,
    location: str | None = None,
    cluster_id: str | None = None,
    instance_id: str | None = None,
    database_id: str | None = None,
) -> str:
    """
    Generates a URL for uploading the template file based on the database type.

    Args:
        db_type: The type of the database. Accepted values are 'alloydb',
                 'cloudsql', or 'spanner'. This can be derived from the 'kind'
                 field in the tools.yaml file. For example, 'alloydb-postgres'
                 becomes 'alloydb', and 'cloud-sql-postgres' becomes 'cloudsql'.
        project_id: The Google Cloud project ID.
        location: The location of the AlloyDB cluster.
        cluster_id: The ID of the AlloyDB cluster.
        instance_id: The ID of the Cloud SQL or Spanner instance.
        database_id: The ID of the Spanner database.

    Returns:
        The generated URL as a string, or an error message if the source kind is invalid.
    """
    if db_type == "alloydb":
        if location and cluster_id and project_id:
            return f"https://console.cloud.google.com/alloydb/locations/{location}/clusters/{cluster_id}/studio?project={project_id}"
        else:
            return "Error: Missing location, cluster_id, or project_id for alloydb."
    elif db_type == "cloudsql":
        if instance_id and project_id:
            return f"https://console.cloud.google.com/sql/instances/{instance_id}/studio?project={project_id}"
        else:
            return "Error: Missing instance_id or project_id for cloudsql."
    elif db_type == "spanner":
        if instance_id and database_id and project_id:
            return f"https://console.cloud.google.com/spanner/instances/{instance_id}/databases/{database_id}/details/query?project={project_id}"
        else:
            return "Error: Missing instance_id, database_id, or project_id for spanner."
    else:
        return "Error: Invalid db_type. Must be one of 'alloydb', 'cloudsql', or 'spanner'."


# ─── Dataset expansion tools ─────────────────────────────────────────────────


@mcp.tool
def set_dataset_generation_model(
    generation_model: str,
    lightweight_model: str | None = None,
) -> str:
    """
    Overrides the LLM models used by all dataset-generation dimension tools.

    Args:
        generation_model: Model name for creative generation and judging steps
               (e.g. 'gemini-2.5-pro'). Default: 'gemini-2.5-pro'.
        lightweight_model: Model name for cheap extraction steps such as value-slot
               extraction and schema-term extraction (e.g. 'gemini-2.5-flash').
               If omitted, the lightweight model is left unchanged.

    Returns:
        A confirmation message showing the active model names.
    """
    set_generation_model(generation_model)
    if lightweight_model:
        set_lightweight_model(lightweight_model)
    from dataset_generation.base import get_generation_model, get_lightweight_model
    return json.dumps({
        "generation_model": get_generation_model(),
        "lightweight_model": get_lightweight_model(),
    })


@mcp.tool
async def generate_lexical_variant(
    anchor_question: str,
    anchor_sql: str,
    level: str,
) -> str:
    """
    Generates a Lexical Distance variant of a seed NL-SQL pair.
    Rephrases the natural language question without altering SQL logic or data values.
    The variant SQL is always identical to the anchor SQL.

    Args:
        anchor_question: The original natural language question.
        anchor_sql: The original SQL query.
        level: Transformation severity — 'low' (syntactic paraphrase),
               'medium' (domain-jargon substitution), or 'high' (slang/idiomatic).

    Returns:
        A JSON string representing a NoiseVariant object.
    """
    try:
        variant_question, variant_sql = await lexical_gen.generate_lexical_variant(
            anchor_question, anchor_sql, level
        )
        return context.NoiseVariant(
            anchor_question=anchor_question,
            anchor_sql=anchor_sql,
            dimension="lexical",
            level=level.lower(),
            variant_question=variant_question,
            variant_sql=variant_sql,
        ).model_dump_json(indent=2)
    except (ValueError, Exception) as e:
        return json.dumps({"error": str(e)})


@mcp.tool
async def generate_structural_variant(
    anchor_question: str,
    anchor_sql: str,
    db_schema: str,
    level: str,
    second_anchor_json: str | None = None,
) -> str:
    """
    Generates a Structural Distance variant of a seed NL-SQL pair.
    Varies the logical complexity of the request; the SQL changes at every level.

    Args:
        anchor_question: The original natural language question.
        anchor_sql: The original SQL query.
        db_schema: The database schema DDL.
        level: Transformation severity — 'low' (decompose: simplest sub-part),
               'medium' (nest: anchor becomes subquery),
               'high' (combine: merge two anchors from the same DB).
        second_anchor_json: Required for 'high' level. JSON string with keys
               'question' and 'sql' for a second anchor from the same database.
               Example: '{"question": "...", "sql": "..."}'

    Returns:
        A JSON string representing a NoiseVariant object.
    """
    try:
        variant_question, variant_sql = await structural_gen.generate_structural_variant(
            anchor_question, anchor_sql, db_schema, level, second_anchor_json
        )
        return context.NoiseVariant(
            anchor_question=anchor_question,
            anchor_sql=anchor_sql,
            dimension="structural",
            level=level.lower(),
            variant_question=variant_question,
            variant_sql=variant_sql,
        ).model_dump_json(indent=2)
    except (ValueError, Exception) as e:
        return json.dumps({"error": str(e)})


@mcp.tool
async def generate_interference_variant(
    anchor_question: str,
    anchor_sql: str,
    db_schema: str,
    level: str,
) -> str:
    """
    Generates an Interference Distance variant of a seed NL-SQL pair.
    Injects conversational noise that the NL2SQL system must identify and discard;
    the core analytical intent and the SQL remain unchanged.

    Args:
        anchor_question: The original natural language question.
        anchor_sql: The original SQL query.
        db_schema: The database schema DDL.
        level: Noise severity — 'low' (politeness fillers),
               'medium' (business-context backstory),
               'high' (red-herring schema distractors).

    Returns:
        A JSON string representing a NoiseVariant object.
    """
    try:
        variant_question, variant_sql = await interference_gen.generate_interference_variant(
            anchor_question, anchor_sql, db_schema, level
        )
        return context.NoiseVariant(
            anchor_question=anchor_question,
            anchor_sql=anchor_sql,
            dimension="interference",
            level=level.lower(),
            variant_question=variant_question,
            variant_sql=variant_sql,
        ).model_dump_json(indent=2)
    except (ValueError, Exception) as e:
        return json.dumps({"error": str(e)})


@mcp.tool
async def generate_value_variant(
    anchor_question: str,
    anchor_sql: str,
    level: str,
    candidate_values_json: str | None = None,
) -> str:
    """
    Generates a Value Distance variant of a seed NL-SQL pair.
    Preserves the SQL structure but changes WHERE/HAVING literals and
    (optionally) their NL surface forms.

    For 'medium' and 'high' levels, you must first fetch candidate values by
    running  SELECT DISTINCT <column> FROM <table>  for each relevant column
    using the execute_sql tool, then pass the results via candidate_values_json.

    Args:
        anchor_question: The original natural language question.
        anchor_sql: The original SQL query.
        level: Substitution severity — 'low' (surface NL reword, SQL identical),
               'medium' (full literal substitution with real DB values),
               'high' (full substitution + surface NL reword).
        candidate_values_json: Required for 'medium'/'high'. JSON mapping
               "table.column" → list of real DB values. Example:
               '{"loans.duration": ["12","24","36","60"]}'

    Returns:
        A JSON string representing a NoiseVariant object.
    """
    try:
        variant_question, variant_sql = await value_gen.generate_value_variant(
            anchor_question, anchor_sql, level, candidate_values_json
        )
        return context.NoiseVariant(
            anchor_question=anchor_question,
            anchor_sql=anchor_sql,
            dimension="value",
            level=level.lower(),
            variant_question=variant_question,
            variant_sql=variant_sql,
        ).model_dump_json(indent=2)
    except (ValueError, Exception) as e:
        return json.dumps({"error": str(e)})


@mcp.tool
async def generate_schema_correction_variant(
    anchor_question: str,
    anchor_sql: str,
    db_schema: str,
    level: str,
    schema_terms_json: str | None = None,
) -> str:
    """
    Generates a Schema Correction Distance variant of a seed NL-SQL pair.
    Introduces typos or fuzzy references to schema terms in the question;
    the SQL remains identical to the anchor.

    Args:
        anchor_question: The original natural language question.
        anchor_sql: The original SQL query.
        db_schema: The database schema DDL (used to extract schema terms if
               schema_terms_json is not provided).
        level: Mutation severity — 'low' (case changes + inserted spaces),
               'medium' (abbreviation substitution), 'high' (character-level typos).
        schema_terms_json: Optional pre-extracted schema term list as a JSON array
               of {"schema_term", "question_token", "term_type"} objects. If omitted
               the tool extracts them automatically via an LLM call.

    Returns:
        A JSON string representing a NoiseVariant object.
    """
    try:
        variant_question, variant_sql = await schema_correction_gen.generate_schema_correction_variant(
            anchor_question, anchor_sql, db_schema, level, schema_terms_json
        )
        return context.NoiseVariant(
            anchor_question=anchor_question,
            anchor_sql=anchor_sql,
            dimension="schema_correction",
            level=level.lower(),
            variant_question=variant_question,
            variant_sql=variant_sql,
        ).model_dump_json(indent=2)
    except (ValueError, Exception) as e:
        return json.dumps({"error": str(e)})


@mcp.tool
async def judge_variant(
    anchor_question: str,
    anchor_sql: str,
    variant_question: str,
    variant_sql: str,
    dimension: str,
    db_schema: str,
) -> str:
    """
    Applies an LLM judge to a generated variant, enforcing universal quality rules
    and per-dimension correctness constraints.

    Call this after execute_sql has confirmed the variant SQL runs without errors
    and returns a non-empty result set.

    Args:
        anchor_question: The original NL question.
        anchor_sql: The original SQL query.
        variant_question: The generated variant NL question.
        variant_sql: The generated variant SQL.
        dimension: One of: lexical | structural | interference | value | schema_correction.
        db_schema: The database schema DDL.

    Returns:
        A JSON string with keys "verdict" ('pass' or 'fail') and "reason"
        (one-sentence justification).
    """
    _DIMENSION_RULES = {
        "lexical": (
            "- The variant SQL must be identical to the anchor SQL.\n"
            "- No new filtering conditions may have been introduced by the rewrite."
        ),
        "structural": (
            "- The variant SQL must be structurally different from the anchor SQL.\n"
            "- The structural change must be plausible (decompose, nest, or combine)."
        ),
        "interference": (
            "- The variant SQL must be identical to the anchor SQL.\n"
            "- The core analytical intent must be recoverable from the variant question.\n"
            "- No new filter constraints may have been introduced by the noise."
        ),
        "value": (
            "- The SQL structure (joins, aggregations, column references) must be preserved.\n"
            "- Only WHERE/HAVING literals may differ between anchor and variant SQL."
        ),
        "schema_correction": (
            "- The variant SQL must be identical to the anchor SQL.\n"
            "- The mutated schema terms in the variant question must still unambiguously"
            " map to the correct schema entities."
        ),
    }

    class _JudgeResponse(BaseModel):
        verdict: str = Field(..., description="'pass' or 'fail'")
        reason: str = Field(..., description="One-sentence justification.")

    dimension_key = dimension.lower()
    dim_rules = _DIMENSION_RULES.get(
        dimension_key,
        "- Verify the variant is a plausible and high-quality transformation of the anchor.",
    )

    prompt = textwrap.dedent(f"""\
        You are an expert NL2SQL dataset quality judge.

        DATABASE SCHEMA:
        {db_schema}

        ANCHOR QUESTION: {anchor_question}
        ANCHOR SQL:      {anchor_sql}

        VARIANT QUESTION: {variant_question}
        VARIANT SQL:      {variant_sql}

        DIMENSION: {dimension}

        UNIVERSAL RULES (must ALL hold for a 'pass'):
        - The variant question is grammatically correct and unambiguous.
        - The variant SQL is valid SQL and correctly answers the variant question.
        - The variant has exactly one correct SQL interpretation.

        DIMENSION-SPECIFIC RULES:
        {dim_rules}

        Respond with a JSON object with keys "verdict" ('pass' or 'fail') and
        "reason" (one sentence explaining your decision).
    """)

    try:
        result = await llm_call(prompt, _JudgeResponse)
        return result.model_dump_json(indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ── Internal dispatcher (not an MCP tool) ────────────────────────────────────

async def _dispatch_variant(req: dict) -> str:
    """Route a single generation request dict to the appropriate generator."""
    dimension = req.get("dimension", "").lower()
    anchor_question = req["anchor_question"]
    anchor_sql = req["anchor_sql"]
    level = req.get("level", "medium")

    try:
        if dimension == "lexical":
            vq, vs = await lexical_gen.generate_lexical_variant(
                anchor_question, anchor_sql, level
            )
        elif dimension == "structural":
            vq, vs = await structural_gen.generate_structural_variant(
                anchor_question, anchor_sql,
                req.get("db_schema", ""),
                level,
                req.get("second_anchor_json"),
            )
        elif dimension == "interference":
            vq, vs = await interference_gen.generate_interference_variant(
                anchor_question, anchor_sql,
                req.get("db_schema", ""),
                level,
            )
        elif dimension == "value":
            vq, vs = await value_gen.generate_value_variant(
                anchor_question, anchor_sql,
                level,
                req.get("candidate_values_json"),
            )
        elif dimension == "schema_correction":
            vq, vs = await schema_correction_gen.generate_schema_correction_variant(
                anchor_question, anchor_sql,
                req.get("db_schema", ""),
                level,
                req.get("schema_terms_json"),
            )
        else:
            return json.dumps({"error": f"Unknown dimension: '{dimension}'"})

        return context.NoiseVariant(
            anchor_question=anchor_question,
            anchor_sql=anchor_sql,
            dimension=dimension,
            level=level,
            variant_question=vq,
            variant_sql=vs,
        ).model_dump_json()
    except Exception as e:
        return json.dumps({"error": str(e), "dimension": dimension, "level": level})


@mcp.tool
async def generate_variants_batch(requests_json: str) -> str:
    """
    Generates multiple NL-SQL variants concurrently in a single call.

    All generation requests are dispatched simultaneously via asyncio.gather,
    making this dramatically faster than calling the individual generate_*_variant
    tools one by one. Use this whenever you need to generate variants for more
    than one (anchor, dimension, level) combination.

    Args:
        requests_json: A JSON array of request objects. Each object must have:
            - anchor_question (str): The original NL question.
            - anchor_sql      (str): The original SQL query.
            - dimension       (str): One of: lexical | structural | interference
                                     | value | schema_correction.
            - level           (str): One of: low | medium | high.
          Optional per-dimension fields:
            - db_schema            (str): Required for structural, interference,
                                          and schema_correction dimensions.
            - second_anchor_json   (str): Required for structural HIGH level.
                                          JSON: '{"question": "...", "sql": "..."}'
            - candidate_values_json (str): Required for value MEDIUM/HIGH.
                                          JSON: '{"table.col": ["v1","v2",...]}'
            - schema_terms_json    (str): Optional for schema_correction
                                          (extracted automatically if omitted).

        Example:
            '[
              {"anchor_question": "...", "anchor_sql": "...", "dimension": "lexical",    "level": "low"},
              {"anchor_question": "...", "anchor_sql": "...", "dimension": "lexical",    "level": "medium"},
              {"anchor_question": "...", "anchor_sql": "...", "dimension": "interference","level": "high","db_schema":"..."}
            ]'

    Returns:
        A JSON array of results in the same order as the input requests.
        Each result is either a NoiseVariant JSON object or {"error": "...", "dimension": "...", "level": "..."}.
    """
    try:
        requests = json.loads(requests_json)
        if not isinstance(requests, list):
            return json.dumps({"error": "requests_json must be a JSON array."})

        raw_results = await asyncio.gather(
            *[_dispatch_variant(req) for req in requests],
            return_exceptions=True,
        )

        output = []
        for r in raw_results:
            if isinstance(r, Exception):
                output.append({"error": str(r)})
            else:
                output.append(json.loads(r))

        return json.dumps(output, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool
async def append_to_dataset_file(file_path: str, entries_json: str) -> str:
    """
    Appends one or more NL-SQL dataset entries to a JSON file.

    Creates the file (as an empty JSON array) if it does not yet exist.
    Entries are appended to the existing array and the file is overwritten atomically
    (write to a temp file then rename) to avoid data loss on failure.

    Args:
        file_path:   Absolute path to the target dataset JSON file.
        entries_json: A JSON array string of entry objects to append.
                      Each entry should be a NoiseVariant JSON object or a
                      standard seed entry (id, database, nlq, golden_sql, …).
                      A single object (not wrapped in an array) is also accepted.

    Returns:
        A JSON object with:
            - "appended": number of entries added in this call.
            - "total":    new total number of entries in the file.
            - "file":     the resolved file path.
    """
    try:
        new_entries = json.loads(entries_json)
        if isinstance(new_entries, dict):
            new_entries = [new_entries]
        if not isinstance(new_entries, list):
            return json.dumps({"error": "entries_json must be a JSON object or array."})

        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
            if not isinstance(existing, list):
                return json.dumps({"error": "Existing file does not contain a JSON array."})
        else:
            existing = []

        existing.extend(new_entries)

        # Write atomically: temp file in same directory, then rename
        dir_name = os.path.dirname(os.path.abspath(file_path)) or "."
        import tempfile
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, file_path)
        except Exception:
            os.unlink(tmp_path)
            raise

        return json.dumps({
            "appended": len(new_entries),
            "total": len(existing),
            "file": os.path.abspath(file_path),
        })
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool
async def expand_anchor(
    anchor_question: str,
    anchor_sql: str,
    dimensions: list[str],
    levels: list[str],
    db_schema: str = "",
    second_anchor_json: str | None = None,
    candidate_values_json: str | None = None,
    schema_terms_json: str | None = None,
) -> str:
    """
    Expands a single NL-SQL anchor across every requested dimension × level combination
    in one concurrent call — no JSON request-array construction needed.

    All generation tasks are dispatched simultaneously via asyncio.gather, making this
    the preferred (fastest) way to expand an anchor. Call once per anchor instead of
    calling individual generate_*_variant tools in a loop.

    Args:
        anchor_question: The original natural language question.
        anchor_sql:      The original SQL query.
        dimensions:      List of dimensions to generate. Any subset of:
                         ["lexical", "structural", "interference", "value", "schema_correction"].
        levels:          List of levels to generate per dimension. Any subset of:
                         ["low", "medium", "high"].
        db_schema:       Database schema DDL. Required for structural, interference, and
                         schema_correction dimensions (pass empty string for lexical/value only).
        second_anchor_json: Required for structural HIGH level.
                         JSON: '{"question": "...", "sql": "..."}'.
        candidate_values_json: Required for value MEDIUM/HIGH.
                         JSON: '{"table.column": ["val1", "val2", ...]}'.
        schema_terms_json: Optional pre-extracted schema terms for schema_correction
                         (extracted automatically via LLM if omitted).

    Returns:
        A JSON array of NoiseVariant objects (one per dimension × level combination).
        Failed items include an "error" key instead of variant fields.
    """
    _DIMS_NEEDING_SCHEMA = {"structural", "interference", "schema_correction"}

    requests = []
    for dim in dimensions:
        for lvl in levels:
            req: dict = {
                "anchor_question": anchor_question,
                "anchor_sql": anchor_sql,
                "dimension": dim.lower(),
                "level": lvl.lower(),
            }
            if dim.lower() in _DIMS_NEEDING_SCHEMA:
                req["db_schema"] = db_schema
            if dim.lower() == "structural" and second_anchor_json:
                req["second_anchor_json"] = second_anchor_json
            if dim.lower() == "value" and candidate_values_json:
                req["candidate_values_json"] = candidate_values_json
            if dim.lower() == "schema_correction" and schema_terms_json:
                req["schema_terms_json"] = schema_terms_json
            requests.append(req)

    raw_results = await asyncio.gather(
        *[_dispatch_variant(req) for req in requests],
        return_exceptions=True,
    )

    output = []
    for r in raw_results:
        if isinstance(r, Exception):
            output.append({"error": str(r)})
        else:
            output.append(json.loads(r))

    return json.dumps(output, indent=2)


@mcp.prompt
def generate_bulk_templates() -> str:
    """Initiates a guided workflow to automatically generate templates based on the database schema."""
    return prompts.GENERATE_BULK_TEMPLATES_PROMPT


@mcp.prompt
def generate_targeted_templates() -> str:
    """Initiates a guided workflow to generate specific templates based on the user's input."""
    return prompts.GENERATE_TARGETED_TEMPLATES_PROMPT


@mcp.prompt
def generate_targeted_facets() -> str:
    """Initiates a guided workflow to generate specific facets based on the user's input."""
    return prompts.GENERATE_TARGETED_FACETS_PROMPT

@mcp.prompt
def generate_targeted_value_searches() -> str:
    """Initiates a guided workflow to generate specific Value Search configurations."""
    return prompts.GENERATE_TARGETED_VALUE_SEARCH_PROMPT


if __name__ == "__main__":
    mcp.run()  # Uses STDIO transport by default
