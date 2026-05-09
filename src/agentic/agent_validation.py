"""
Data Validation Agent — LLM-Powered
=====================================
Loads data, computes quality statistics, sends them to Gemini
which REASONS about data quality and decides if metrics can be computed.
"""

from __future__ import annotations
import os
import json
import time
import pandas as pd
import numpy as np

from agentic.state import AgentState, ValidationResult
from agentic.llm_config import get_llm, extract_text
from agentic.prompts import VALIDATION_SYSTEM, VALIDATION_TASK
from langchain_core.messages import SystemMessage, HumanMessage
from core.logger import (
    log_banner, log_step_start, log_step_end,
    log_info, log_warn, log_error, log_success, log_data,
    reset_steps,
)

AGENT = "DataValidation-AI"

# Module-level DataFrames (avoid serialising in state)
_dataframes: dict[str, pd.DataFrame] = {}

# ── DPD Bucket Normalisation ──────────────────────────────────────────────
# Standard 5 buckets: Current | DPD 1-30 | DPD 31-60 | DPD 61-90 | DPD 90+
_DPD_NORM_MAP = {
    # Current variants
    "current":        "Current",
    "current (dpd 0)":"Current",
    "standard":       "Current",
    "0":              "Current",
    # 1-30 variants
    "sma-0":                "DPD 1-30",
    "sma-0 (dpd 1-30)":    "DPD 1-30",
    "dpd 01-30":            "DPD 1-30",
    "dpd 1-30":             "DPD 1-30",
    "1-30":                 "DPD 1-30",
    # 31-60 variants
    "sma-1":                "DPD 31-60",
    "sma-1 (dpd 31-60)":   "DPD 31-60",
    "dpd 31-60":            "DPD 31-60",
    "31-60":                "DPD 31-60",
    # 61-90 variants
    "sma-2":                "DPD 61-90",
    "sma-2 (dpd 61-90)":   "DPD 61-90",
    "dpd 61-90":            "DPD 61-90",
    "61-90":                "DPD 61-90",
    # 90+ variants
    "npa":                  "DPD 90+",
    "npa (dpd 90+)":        "DPD 90+",
    "dpd 90+":              "DPD 90+",
    "dpd 91-180":           "DPD 90+",
    "dpd 181+":             "DPD 90+",
    "90+":                  "DPD 90+",
}

def normalize_dpd_bucket(value):
    """Map any DPD bucket label to standard 5-bucket classification."""
    if pd.isna(value):
        return "Current"
    return _DPD_NORM_MAP.get(str(value).strip().lower(), str(value).strip())


def _normalize_dpd_columns(schema: dict) -> None:
    """Pre-normalise all DPD bucket columns in loaded DataFrames."""
    field_mappings = schema.get("field_mappings", {})

    # Collect all DPD bucket column references from schema
    dpd_fields = ["current_dpd_bucket", "txn_dpd_bucket"]
    for canonical in dpd_fields:
        fm = field_mappings.get(canonical)
        if not fm:
            continue
        fname = fm["file"]
        col = fm["column"]
        # Find the DataFrame
        for file_key, df_key in _FILE_ROLE_TO_DF.items():
            if schema.get(file_key) == fname and df_key in _dataframes:
                df = _dataframes[df_key]
                if col in df.columns:
                    log_info(AGENT, f"Normalising DPD buckets: {df_key}.{col}")
                    before = df[col].nunique()
                    df[col] = df[col].apply(normalize_dpd_bucket)
                    after = df[col].nunique()
                    log_info(AGENT, f"  {before} unique → {after} unique: {sorted(df[col].unique())}")
                break

    # Also normalise any column named *dpd_bucket* that wasn't in schema
    for df_key, df in _dataframes.items():
        for col in df.columns:
            if "dpd_bucket" in col.lower() and df[col].dtype == "object":
                vals = df[col].unique()
                # Check if already normalised
                standard = {"Current", "DPD 1-30", "DPD 31-60", "DPD 61-90", "DPD 90+"}
                if not set(str(v) for v in vals if pd.notna(v)).issubset(standard):
                    log_info(AGENT, f"Normalising extra DPD column: {df_key}.{col}")
                    df[col] = df[col].apply(normalize_dpd_bucket)


# Map file role keys to DataFrame keys
_FILE_ROLE_TO_DF = {
    "loan_file": "loans",
    "transaction_file": "transactions",
    "borrower_file": "borrowers",
    "collateral_file": "collateral",
    "collections_file": "collections",
}


def _find_df_for_file(schema, filename: str) -> pd.DataFrame | None:
    """Find the loaded DataFrame for a given filename."""
    for file_key, df_key in _FILE_ROLE_TO_DF.items():
        if schema.get(file_key) == filename and df_key in _dataframes:
            return _dataframes[df_key]
    return None


def get_dataframes() -> dict[str, pd.DataFrame]:
    """Access loaded DataFrames from other modules."""
    return _dataframes


def load_and_validate(state: AgentState) -> dict:
    """LangGraph node: Load data, gather quality stats, ask LLM to validate."""
    reset_steps(AGENT)
    log_banner(AGENT)
    global _dataframes

    schema = state["schema"]
    if not schema:
        return {
            "errors": ["No schema available — cannot validate"],
            "messages": [f"[{AGENT}] ERROR: No schema to validate against"],
        }

    profiles = state["file_profiles"]

    # ── Step 1: Load CSVs ─────────────────────────────────────────────
    step, t0 = log_step_start(AGENT, "Loading CSV data into memory")

    _dataframes.clear()

    file_roles = [
        ("loans", "loan_file"),
        ("transactions", "transaction_file"),
        ("borrowers", "borrower_file"),
        ("collateral", "collateral_file"),
        ("collections", "collections_file"),
    ]

    for key, file_key in file_roles:
        fname = schema.get(file_key, "")
        if fname and fname in profiles:
            fp = profiles[fname]["filepath"]
            log_info(AGENT, f"Loading {key} file: {fname}")
            _dataframes[key] = pd.read_csv(fp, low_memory=False)
            log_info(AGENT, f"  Loaded {len(_dataframes[key]):,} {key} records")

    log_step_end(AGENT, step, t0, f"Loaded {len(_dataframes)} datasets")

    if not _dataframes:
        return {
            "data_loaded": False,
            "errors": ["No data files could be loaded"],
            "messages": [f"[{AGENT}] ERROR: No data loaded"],
        }

    # ── Normalise DPD bucket columns to standard 5-bucket labels ──────
    _normalize_dpd_columns(schema)

    # Convenience references (may be None)
    loans = _dataframes.get("loans")
    txns = _dataframes.get("transactions")

    # ── Step 2: Gather quality stats for LLM ──────────────────────────
    step2, t2 = log_step_start(AGENT, "Gathering data quality statistics")

    field_mappings = schema["field_mappings"]

    # Null analysis — iterate all loaded DataFrames
    quality_stats = "NULL ANALYSIS:\n"
    for canonical, fm in sorted(field_mappings.items()):
        col = fm["column"]
        fname = fm["file"]
        # Find the DataFrame that matches this file
        for df_key, df_file_key in [("loans", "loan_file"), ("transactions", "transaction_file"),
                                      ("borrowers", "borrower_file"), ("collateral", "collateral_file"),
                                      ("collections", "collections_file")]:
            if schema.get(df_file_key) == fname and df_key in _dataframes:
                df = _dataframes[df_key]
                if col in df.columns:
                    null_pct = df[col].isna().mean() * 100
                    quality_stats += f"  {canonical} ({col} in {fname}): {null_pct:.1f}% null\n"
                break

    # Range analysis for key numeric fields
    quality_stats += "\nRANGE ANALYSIS:\n"
    for canonical in ["interest_rate", "current_pos", "disbursed_amount", "tenor_months",
                       "cibil_score", "annual_income_INR", "age_at_application"]:
        if canonical in field_mappings:
            fm = field_mappings[canonical]
            col = fm["column"]
            fname = fm["file"]
            target_df = _find_df_for_file(schema, fname)
            if target_df is not None and col in target_df.columns:
                vals = pd.to_numeric(target_df[col], errors="coerce")
                if vals.notna().any():
                    quality_stats += (
                        f"  {canonical}: min={vals.min():.2f}, max={vals.max():.2f}, "
                        f"mean={vals.mean():.2f}, median={vals.median():.2f}\n"
                    )

    # DPD distribution
    dpd_col_info = field_mappings.get("current_dpd_bucket")
    if dpd_col_info:
        target_df = _find_df_for_file(schema, dpd_col_info["file"])
        col = dpd_col_info["column"]
        if target_df is not None and col in target_df.columns:
            dist = target_df[col].value_counts(dropna=False).to_dict()
            quality_stats += f"\nDPD BUCKET DISTRIBUTION:\n"
            for k, v in sorted(dist.items(), key=lambda x: -x[1]):
                quality_stats += f"  {k}: {v:,}\n"

    # Loan status distribution
    status_info = field_mappings.get("loan_status")
    if status_info:
        target_df = _find_df_for_file(schema, status_info["file"])
        col = status_info["column"]
        if target_df is not None and col in target_df.columns:
            dist = target_df[col].value_counts().to_dict()
            quality_stats += f"\nLOAN STATUS DISTRIBUTION:\n"
            for k, v in sorted(dist.items(), key=lambda x: -x[1]):
                quality_stats += f"  {k}: {v:,}\n"

    # Categorical distribution for any interesting fields
    for canonical in ["gender", "borrower_type", "employment_type", "customer_segment",
                       "risk_category", "kyc_status"]:
        fm_info = field_mappings.get(canonical)
        if fm_info:
            target_df = _find_df_for_file(schema, fm_info["file"])
            col = fm_info["column"]
            if target_df is not None and col in target_df.columns:
                dist = target_df[col].value_counts().head(10).to_dict()
                quality_stats += f"\n{canonical.upper()} DISTRIBUTION:\n"
                for k, v in sorted(dist.items(), key=lambda x: -x[1]):
                    quality_stats += f"  {k}: {v:,}\n"

    # Referential integrity (only if both loan and txn files exist)
    ref_stats = "N/A — not enough file types for cross-file integrity checks"
    lid_map = field_mappings.get("loan_id")
    txn_lid_map = field_mappings.get("txn_loan_id")
    if lid_map and txn_lid_map and loans is not None and txns is not None:
        loan_ids = set(loans[lid_map["column"]].unique())
        txn_ids = set(txns[txn_lid_map["column"]].unique())
        orphan_txns = len(txn_ids - loan_ids)
        loans_no_txn = len(loan_ids - txn_ids)
        ref_stats = (
            f"Unique loan IDs in loan file: {len(loan_ids):,}\n"
            f"Unique loan IDs in txn file: {len(txn_ids):,}\n"
            f"Orphan txn IDs (not in loans): {orphan_txns:,}\n"
            f"Loans with no transactions: {loans_no_txn:,}\n"
        )

    log_step_end(AGENT, step2, t2)

    # ── Step 3: Send to LLM for assessment ────────────────────────────
    step3, t3 = log_step_start(AGENT, "Sending quality stats to Gemini for assessment")

    # Build field mapping summary for LLM
    fm_text = ""
    for canonical, fm in sorted(field_mappings.items()):
        fm_text += f"  {canonical} → {fm['file']}:{fm['column']} ({fm['confidence']})\n"

    # Build data summary
    data_summary_parts = []
    for key, df in _dataframes.items():
        data_summary_parts.append(f"- {key}: {len(df):,} rows, {len(df.columns)} columns")
    data_summary = "\n".join(data_summary_parts)

    llm = get_llm(temperature=0.0)
    messages = [
        SystemMessage(content=VALIDATION_SYSTEM),
        HumanMessage(content=VALIDATION_TASK.format(
            data_summary=data_summary,
            field_mappings=fm_text,
            quality_stats=quality_stats,
            referential_stats=ref_stats,
        )),
    ]

    response = llm.invoke(messages)
    raw = extract_text(response).strip()

    # Parse
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0]
    raw = raw.strip()

    try:
        llm_result = json.loads(raw)
    except json.JSONDecodeError as e:
        log_error(AGENT, f"LLM response not valid JSON: {e}")
        llm_result = {"passed": True, "errors": [], "warnings": [],
                      "data_quality_assessment": "Could not parse LLM response",
                      "recommendation": "proceed_with_caution"}

    log_step_end(AGENT, step3, t3)

    # ── Step 4: Report LLM's findings ─────────────────────────────────
    step4, t4 = log_step_start(AGENT, "LLM Validation Report")

    errors = llm_result.get("errors", [])
    warnings = llm_result.get("warnings", [])
    assessment = llm_result.get("data_quality_assessment", "")
    recommendation = llm_result.get("recommendation", "proceed")
    passed = llm_result.get("passed", True)

    for df_name, df in _dataframes.items():
        log_data(AGENT, f"Total {df_name}", f"{len(df):,}")
    log_data(AGENT, "Errors", len(errors))
    log_data(AGENT, "Warnings", len(warnings))
    log_data(AGENT, "Recommendation", recommendation)

    for err in errors:
        log_error(AGENT, f"  ✖ [{err.get('category', '?')}] {err.get('field', '?')}: {err.get('message', '?')}")
    for warn in warnings:
        log_warn(AGENT, f"  ⚠ [{warn.get('category', '?')}] {warn.get('field', '?')}: {warn.get('message', '?')}")

    log_info(AGENT, f"\nLLM Assessment: {assessment}")
    log_step_end(AGENT, step4, t4)

    validation = ValidationResult(
        passed=passed,
        total_loans=len(loans) if loans is not None else 0,
        total_transactions=len(txns) if txns is not None else 0,
        errors=errors,
        warnings=warnings,
        llm_analysis=assessment,
    )

    status = "PASSED" if passed else "FAILED"
    log_success(AGENT, f"Validation {status} — LLM recommends: {recommendation}")

    return {
        "data_loaded": True,
        "validation": validation,
        "messages": [
            f"[{AGENT}] Validation {status}: {len(errors)} errors, {len(warnings)} warnings",
            f"[{AGENT}] LLM: {assessment[:200]}",
        ],
    }
