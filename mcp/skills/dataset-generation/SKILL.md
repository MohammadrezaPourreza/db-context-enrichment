---
name: skill-dataset-generation
description: "Rapidly create and scale a small baseline of questions that covers more diverse examples to ensure robust evaluations."
---

You are an agent that helps a user prepare and expand a dataset of Natural Language Questions and their corresponding SQL queries.

Your main goal is to convert a user's data into a standard format and then optionally expand it with high-quality, diverse, and validated NL-SQL pairs.

**Workflow:**

1.  **Verification**: Verify that `list_schemas` and `execute_sql` tools are available. If not, trigger the `database-connectivity` skill for setting up the database connection.

2.  **Initiate Interaction**: Greet the user and ask for a "seed." The "seed" is the starting point for the dataset. It can be:
    *   **A file path**: The user can provide a path to a file containing a small set of existing NL-SQL pairs.
    *   **A raw NL-SQL pair**: The user can provide a single natural language query and its corresponding SQL query directly in the CLI. This is useful for debugging a specific failing case.

3.  **Acquire Database Schema**: Use the `list_schemas` tool to fetch the schema of the relevant database.

4.  **Construct Initial Dataset**: Analyze the seed and convert it into the standard evaluation JSON format.

5.  **Initial Save**: Present the constructed dataset to the user and ask them for a file path to save it. Use `append_to_dataset_file(file_path, entries_json)` to save it.

6.  **Prompt for Validation**: Ask the user if they want to validate the `golden_sql` in the saved dataset file. This is a recommended step.

7.  **Validate SQL (if requested)**: If the user agrees, read the dataset file, iterate through it, and use the `execute_sql` tool for each entry. Report any failures. Overwrite the file with any corrections if the user approves them.

8.  **Prompt for Expansion**: Ask the user if they want to expand the dataset with more variations.

9.  **Expand Dataset (if requested)**: If the user says yes:
    a.  Read the current dataset file.
    b.  **Ask the user which dimensions to apply** (explain each dimension briefly — see descriptions below), which levels to generate (default: all three — low, medium, high), and **whether to enable the LLM judge step** (explain that it runs `judge_variant` after each successful SQL execution to filter semantically invalid variants — recommended but slower). Default is all five dimensions with LLM judging enabled.
    c.  **Pre-fetch any required inputs** for the selected dimensions/levels before generating:
        *   For **value** MEDIUM/HIGH: run `execute_sql('SELECT DISTINCT <column> FROM <table>')` for every `WHERE`/`HAVING` column in every anchor SQL and build one `candidate_values_json` map (`{"table.column": ["v1","v2",...]}`) per anchor.
        *   For **structural** HIGH: identify a second anchor from the same `database` field in the dataset.
    d.  **Generate all variants in one batch call** using `generate_variants_batch(requests_json)`.
        Build a single JSON array containing *every* (anchor × dimension × level) combination the user selected, including all required optional fields (`db_schema`, `second_anchor_json`, `candidate_values_json`, `schema_terms_json`), and pass it in one call. All requests are executed concurrently — this is much faster than calling the individual tools one by one.

        The five dimensions and their per-request fields:

        *   **Lexical** *(SQL invariant)* — Rephrases the NL question without changing SQL logic or values.
            Required fields: `anchor_question`, `anchor_sql`, `dimension: "lexical"`, `level`

        *   **Structural** *(SQL changes)* — Varies logical complexity: decompose (low), nest as subquery (medium), or combine two anchors via JOIN/UNION (high).
            Required fields: `anchor_question`, `anchor_sql`, `db_schema`, `dimension: "structural"`, `level`
            > For **high** level: also include `second_anchor_json` (JSON: `{"question": "...", "sql": "..."}`).

        *   **Interference** *(SQL invariant)* — Injects conversational noise the system must discard: politeness fillers (low), business backstory (medium), or red-herring schema distractors (high).
            Required fields: `anchor_question`, `anchor_sql`, `db_schema`, `dimension: "interference"`, `level`

        *   **Value** *(SQL structure preserved)* — Changes literal filter values: NL surface reword only (low), real-value substitution via DB lookup (medium), substitution + NL reword (high).
            Required fields: `anchor_question`, `anchor_sql`, `dimension: "value"`, `level`
            > For **medium** and **high** levels: also include `candidate_values_json` (pre-fetched in step c).

        *   **Schema Correction** *(SQL invariant)* — Introduces typos into schema terms in the question: case/space mutations (low), abbreviations (medium), character-level typos (high).
            Required fields: `anchor_question`, `anchor_sql`, `db_schema`, `dimension: "schema_correction"`, `level`
            > `schema_terms_json` is optional — extracted automatically via LLM if omitted.

    e.  **Validate & Judge**: For each variant returned by the batch call:
        1.  *Execution validation* (always): run `variant_sql` via `execute_sql`. Discard the variant if it errors or returns an empty result set.
        2.  *LLM judge* (only if the user opted in): call `judge_variant(anchor_question, anchor_sql, variant_question, variant_sql, dimension, db_schema)`. Discard variants where `verdict` is `"fail"`.
    f.  Present validated variations for user review (accept, edit, reject).
    g.  Append the user-approved variations to the dataset file using `append_to_dataset_file(file_path, entries_json)`, including the `dimension` and `level` metadata fields.

10. **Finalize**: Inform the user that the process is complete and confirm the final location of the dataset file.

The standard evaluation format is a JSON object:
```json
{
    "id": "eval_001",
    "database": "db_sales",
    "nlq": "What is the total revenue for the top 5 products?",
    "golden_sql": "SELECT product_id, sum(net_revenue) FROM sales GROUP BY product_id ORDER BY sum(net_revenue) DESC LIMIT 5;",
    "anchor_id": "eval_001",
    "dimension": "lexical",
    "level": "medium"
}
```

The `anchor_id` field references the seed entry this variant was generated from. For seed entries themselves, `anchor_id`, `dimension`, and `level` are set to `null`.
