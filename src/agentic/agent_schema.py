"""
Schema Discovery Agent — LLM-Powered
======================================
Sends file profiles to Gemini, which REASONS about:
- What domain each file belongs to
- Which columns map to which canonical fields
- How confident it is about each mapping

The AI THINKS and decides, not a fuzzy-match algorithm.
"""

from __future__ import annotations
import os
import json
import time
import pandas as pd

from agentic.state import AgentState, FileInfo, SchemaResult, FieldMapping
from agentic.llm_config import get_llm, extract_text
from agentic.prompts import SCHEMA_DISCOVERY_SYSTEM, SCHEMA_DISCOVERY_TASK
from langchain_core.messages import SystemMessage, HumanMessage
from core.logger import (
    log_banner, log_step_start, log_step_end, log_step_fail,
    log_info, log_warn, log_error, log_success, log_data, log_table,
    reset_steps,
)

AGENT = "SchemaDiscovery-AI"


def discover_files(state: AgentState) -> dict:
    """LangGraph node: Profile the provided CSV files."""
    reset_steps(AGENT)
    log_banner(AGENT)

    step, t0 = log_step_start(AGENT, "Discovering CSV files")
    csv_files: list[str] = state["csv_paths"]

    missing = [p for p in csv_files if not os.path.isfile(p)]
    if missing:
        return {
            "errors": [f"File not found: {p}" for p in missing],
            "messages": [f"[{AGENT}] ERROR: {len(missing)} path(s) not found"],
        }

    log_step_end(AGENT, step, t0, f"Found {len(csv_files)} CSV file(s)")
    for fp in csv_files:
        log_info(AGENT, f"  {os.path.basename(fp)}")

    # Profile each file
    step2, t2 = log_step_start(AGENT, "Profiling CSV files")
    profiles: dict[str, FileInfo] = {}

    for filepath in csv_files:
        fname = os.path.basename(filepath)
        log_info(AGENT, f"Profiling {fname} ...")
        ft = time.time()

        sample = pd.read_csv(filepath, nrows=500, low_memory=False)
        row_count = sum(1 for _ in open(filepath)) - 1

        columns = list(sample.columns)
        dtypes = {}
        null_pcts = {}
        sample_values = {}

        for col in columns:
            null_pcts[col] = round(float(sample[col].isna().mean() * 100), 1)
            non_null = sample[col].dropna().head(5).tolist()
            sample_values[col] = [str(v) for v in non_null]
            dtypes[col] = str(sample[col].dtype)

        profiles[fname] = FileInfo(
            filepath=filepath,
            filename=fname,
            columns=columns,
            row_count=row_count,
            dtypes=dtypes,
            sample_values=sample_values,
            null_pcts=null_pcts,
        )
        log_info(AGENT, f"  {fname}: {len(columns)} cols × {row_count:,} rows ({time.time()-ft:.1f}s)")

    log_step_end(AGENT, step2, t2, f"Profiled {len(csv_files)} files")

    return {
        "files": csv_files,
        "file_profiles": profiles,
        "messages": [f"[{AGENT}] Discovered and profiled {len(csv_files)} CSV files"],
    }


def map_schema_with_llm(state: AgentState) -> dict:
    """LangGraph node: Send profiles to Gemini for intelligent schema mapping."""
    step, t0 = log_step_start(AGENT, "Sending file profiles to Gemini for schema mapping")

    profiles = state["file_profiles"]

    # Build a compact representation for the LLM
    profiles_text = ""
    for fname, profile in profiles.items():
        profiles_text += f"\n--- {fname} ({profile['row_count']:,} rows, {len(profile['columns'])} columns) ---\n"
        profiles_text += "Columns with sample values:\n"
        for col in profile["columns"]:
            samples = profile["sample_values"].get(col, [])
            null_pct = profile["null_pcts"].get(col, 0)
            dtype = profile["dtypes"].get(col, "?")
            sample_str = ", ".join(samples[:3]) if samples else "all null"
            null_str = f" [{null_pct}% null]" if null_pct > 0 else ""
            profiles_text += f"  - {col} ({dtype}): {sample_str}{null_str}\n"

    # Call LLM
    log_info(AGENT, f"Sending {len(profiles_text)} chars to Gemini...")
    llm = get_llm(temperature=0.0)

    messages = [
        SystemMessage(content=SCHEMA_DISCOVERY_SYSTEM),
        HumanMessage(content=SCHEMA_DISCOVERY_TASK.format(file_profiles=profiles_text)),
    ]

    response = llm.invoke(messages)
    raw_response = extract_text(response)
    log_info(AGENT, f"Gemini responded with {len(raw_response)} chars")

    # Parse LLM JSON response
    step2, t2 = log_step_start(AGENT, "Parsing LLM schema mapping")

    # Clean response — strip markdown fences if present
    cleaned = raw_response.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1]  # Remove first line
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0]
    cleaned = cleaned.strip()

    try:
        llm_result = json.loads(cleaned)
    except json.JSONDecodeError as e:
        log_error(AGENT, f"Failed to parse LLM response as JSON: {e}")
        log_error(AGENT, f"Raw response (first 500 chars): {raw_response[:500]}")
        return {
            "errors": [f"LLM response was not valid JSON: {e}"],
            "messages": [f"[{AGENT}] ERROR: LLM returned invalid JSON"],
        }

    # Build SchemaResult from LLM output
    file_class = llm_result.get("file_classification", {})
    field_maps = llm_result.get("field_mappings", {})
    unmapped = llm_result.get("unmapped_fields", [])
    assessment = llm_result.get("overall_assessment", "")

    # Determine file roles
    loan_file = ""
    txn_file = ""
    borrower_file = ""
    collateral_file = ""
    collections_file = ""

    for fname, info in file_class.items():
        domain = info.get("domain", "").lower()
        log_info(AGENT, f"  {fname} → {domain.upper()} — {info.get('reasoning', '')}")
        if domain == "loan":
            loan_file = fname
        elif domain == "transaction":
            txn_file = fname
        elif domain == "borrower":
            borrower_file = fname
        elif domain == "collateral":
            collateral_file = fname
        elif domain == "collections":
            collections_file = fname

    # Build field mappings
    mappings: dict[str, FieldMapping] = {}
    for canonical, info in field_maps.items():
        mappings[canonical] = FieldMapping(
            canonical=canonical,
            file=info["file"],
            column=info["column"],
            confidence=info.get("confidence", "medium"),
            reasoning=info.get("reasoning", ""),
        )

    computable = llm_result.get("computable_metrics", [])
    non_computable = llm_result.get("non_computable_metrics", {})

    schema = SchemaResult(
        loan_file=loan_file,
        transaction_file=txn_file,
        borrower_file=borrower_file,
        collateral_file=collateral_file,
        collections_file=collections_file,
        field_mappings=mappings,
        unmapped_fields=unmapped,
        computable_metrics=computable,
        non_computable_metrics=non_computable,
        llm_reasoning=assessment,
    )

    log_step_end(AGENT, step2, t2, f"Mapped {len(mappings)} fields, {len(unmapped)} unmapped")

    # Print summary table
    _print_mapping_summary(schema, profiles)

    log_step_end(AGENT, step, t0)
    log_success(AGENT, f"LLM Assessment: {assessment}")

    return {
        "schema": schema,
        "messages": [
            f"[{AGENT}] LLM mapped {len(mappings)} fields across {len(file_class)} files",
            f"[{AGENT}] Assessment: {assessment}",
        ],
    }


def _print_mapping_summary(schema: SchemaResult, profiles: dict):
    """Print a nice summary of the LLM's schema mapping."""
    log_info(AGENT, "\nFile Classification:")
    log_data(AGENT, "Loan file", schema["loan_file"] or "NOT FOUND")
    log_data(AGENT, "Transaction file", schema["transaction_file"] or "NOT FOUND")
    if schema["borrower_file"]:
        log_data(AGENT, "Borrower file", schema["borrower_file"])
    if schema["collateral_file"]:
        log_data(AGENT, "Collateral file", schema["collateral_file"])
    if schema["collections_file"]:
        log_data(AGENT, "Collections file", schema["collections_file"])

    log_info(AGENT, "\nField Mappings (by LLM):")
    headers = ["Canonical", "File", "Column", "Confidence", "Reasoning"]
    rows = []
    for canonical, fm in sorted(schema["field_mappings"].items()):
        rows.append([
            canonical,
            fm["file"][:25],
            fm["column"][:28],
            fm["confidence"],
            fm["reasoning"][:40],
        ])
    log_table(AGENT, headers, rows)

    if schema["unmapped_fields"]:
        log_warn(AGENT, f"\nUnmapped fields: {schema['unmapped_fields']}")
