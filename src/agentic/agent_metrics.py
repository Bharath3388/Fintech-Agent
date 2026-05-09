"""
Metric Computation Agent — LLM-Powered
========================================
For each metric, sends the schema mapping to Gemini and asks it to
GENERATE Python code. Then executes that code on the loaded DataFrames.

The LLM is the brain — it decides HOW to compute each metric based on
the actual column names and data characteristics.
"""

from __future__ import annotations
import os
import json
import time
import traceback
import pandas as pd
import numpy as np
from datetime import datetime

from agentic.state import AgentState, MetricResultItem
from agentic.llm_config import get_llm, extract_text
from agentic.prompts import METRIC_SYSTEM, METRIC_PROMPTS
from agentic.agent_validation import get_dataframes
from langchain_core.messages import SystemMessage, HumanMessage
from agentic.agent_validation import normalize_dpd_bucket as _normalize_dpd_bucket
from core.logger import (
    log_banner, log_step_start, log_step_end, log_step_fail,
    log_info, log_warn, log_error, log_success, log_data,
    reset_steps,
)

AGENT = "MetricComputation-AI"


def compute_metrics(state: AgentState) -> dict:
    """LangGraph node: Use LLM to generate and execute metric computation code."""
    reset_steps(AGENT)
    log_banner(AGENT)
    t_total = time.time()

    schema = state["schema"]
    if not schema or not state.get("data_loaded"):
        return {
            "errors": ["No schema or data — cannot compute metrics"],
            "messages": [f"[{AGENT}] ERROR: Missing schema or data"],
        }

    dfs = get_dataframes()
    loans_df = dfs.get("loans")
    txns_df = dfs.get("transactions")

    # Build dict of extra DataFrames for LLM-generated code
    extra_dfs = {k: v for k, v in dfs.items() if k not in ("loans", "transactions")}

    if not dfs:
        return {
            "errors": ["No DataFrames loaded"],
            "messages": [f"[{AGENT}] ERROR: No data in memory"],
        }

    # Build schema mapping text for LLM
    schema_text = _build_schema_text(schema, dfs)

    llm = get_llm(temperature=0.0)
    metrics: dict[str, MetricResultItem] = {}
    all_messages = []

    # Check which metrics the LLM thinks are computable
    non_computable = schema.get("non_computable_metrics", {})

    for metric_key, (metric_name, prompt_template) in METRIC_PROMPTS.items():
        step, t0 = log_step_start(AGENT, f"{metric_key}: {metric_name}")

        metric_ids = metric_key.split("_") if "_" in metric_key else [metric_key]

        # Check if any metric in this group was flagged as non-computable
        skip_reason = None
        for mid in metric_ids:
            if mid in non_computable:
                skip_reason = non_computable[mid]
                break

        if skip_reason:
            log_warn(AGENT, f"Skipping {metric_key} — LLM says: {skip_reason}")
            for mid in metric_ids:
                metrics[mid] = MetricResultItem(
                    metric_id=mid, name=metric_name,
                    status="not_available",
                    data={"reason": skip_reason},
                    llm_insight=f"Not computable: {skip_reason}",
                )
            log_step_end(AGENT, step, t0, "SKIPPED")
            all_messages.append(f"[{AGENT}] {metric_key}: SKIPPED — {skip_reason}")
            continue

        try:
            # ── Ask LLM to generate code ──────────────────────────────
            log_info(AGENT, f"Asking Gemini to generate computation code...")

            messages = [
                SystemMessage(content=METRIC_SYSTEM),
                HumanMessage(content=prompt_template.format(schema_mapping=schema_text)),
            ]

            response = llm.invoke(messages)
            generated_code = extract_text(response).strip()

            # Clean markdown fences
            if generated_code.startswith("```"):
                lines = generated_code.split("\n")
                generated_code = "\n".join(lines[1:])
                if generated_code.endswith("```"):
                    generated_code = generated_code.rsplit("```", 1)[0]
            generated_code = generated_code.strip()

            log_info(AGENT, f"LLM generated {len(generated_code)} chars of code")

            # ── Execute the generated code ────────────────────────────
            log_info(AGENT, f"Executing generated code...")

            # Build execution namespace with DataFrames and utilities
            exec_namespace = {
                "loans_df": loans_df.copy() if loans_df is not None else None,
                "txns_df": txns_df.copy() if txns_df is not None else None,
                "extra_dfs": {k: v.copy() for k, v in extra_dfs.items()},
                "pd": pd,
                "np": np,
                "datetime": datetime,
                "result": None,
                "print": _make_agent_print(AGENT),
                "normalize_dpd_bucket": _normalize_dpd_bucket,
            }

            exec(generated_code, exec_namespace)

            result_data = exec_namespace.get("result")

            if result_data is None:
                log_warn(AGENT, f"Code executed but 'result' variable not set")
                for mid in metric_ids:
                    metrics[mid] = MetricResultItem(
                        metric_id=mid, name=metric_name,
                        status="error", data=None,
                        llm_insight="Code ran but produced no result",
                    )
            else:
                # ── Check if result has per-metric sub-keys ───────────
                if isinstance(result_data, dict) and all(mid in result_data for mid in metric_ids):
                    # Per-metric results (e.g. B1_B2_B3 returns {"B1": {...}, "B2": {...}, "B3": {...}})
                    insight = _get_llm_insight(llm, metric_name, result_data)
                    for mid in metric_ids:
                        sub_data = result_data[mid]
                        sub_status = "ok"
                        if isinstance(sub_data, dict) and "error" in sub_data:
                            sub_status = "not_available"
                        metrics[mid] = MetricResultItem(
                            metric_id=mid, name=metric_name,
                            status=sub_status, data=sub_data,
                            llm_insight=insight,
                        )
                        log_success(AGENT, f"{mid} — {metric_name}: {sub_status.upper()}")
                else:
                    # Single result for all metric_ids (e.g. M5_M8)
                    insight = _get_llm_insight(llm, metric_name, result_data)
                    for mid in metric_ids:
                        metrics[mid] = MetricResultItem(
                            metric_id=mid, name=metric_name,
                            status="ok", data=result_data,
                            llm_insight=insight,
                        )
                        log_success(AGENT, f"{mid} — {metric_name}: OK")

                log_info(AGENT, f"LLM Insight: {insight[:200]}")

            log_step_end(AGENT, step, t0, "OK")
            all_messages.append(f"[{AGENT}] {metric_key}: OK")

        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            tb = traceback.format_exc()
            log_error(AGENT, f"Execution failed: {error_msg}")
            log_info(AGENT, f"Traceback:\n{tb[-500:]}")

            # ── Ask LLM to fix the code ───────────────────────────────
            log_info(AGENT, "Asking Gemini to fix the code...")
            fixed = _retry_with_fix(llm, prompt_template, schema_text,
                                     generated_code, error_msg, tb,
                                     loans_df, txns_df, extra_dfs, AGENT, metric_name)

            if fixed is not None:
                insight = _get_llm_insight(llm, metric_name, fixed)
                if isinstance(fixed, dict) and all(mid in fixed for mid in metric_ids):
                    for mid in metric_ids:
                        sub_data = fixed[mid]
                        sub_status = "ok"
                        if isinstance(sub_data, dict) and "error" in sub_data:
                            sub_status = "not_available"
                        metrics[mid] = MetricResultItem(
                            metric_id=mid, name=metric_name,
                            status=sub_status, data=sub_data,
                            llm_insight=insight,
                        )
                        log_success(AGENT, f"{mid} — {metric_name}: {sub_status.upper()} (after retry)")
                else:
                    for mid in metric_ids:
                        metrics[mid] = MetricResultItem(
                            metric_id=mid, name=metric_name,
                            status="ok", data=fixed,
                            llm_insight=insight,
                        )
                        log_success(AGENT, f"{mid} — {metric_name}: OK (after retry)")
                log_step_end(AGENT, step, t0, "OK (retried)")
                all_messages.append(f"[{AGENT}] {metric_key}: OK (after self-correction)")
            else:
                for mid in metric_ids:
                    metrics[mid] = MetricResultItem(
                        metric_id=mid, name=metric_name,
                        status="error", data={"error": error_msg},
                        llm_insight="",
                    )
                log_step_fail(AGENT, step, t0, error_msg)
                all_messages.append(f"[{AGENT}] {metric_key}: FAILED — {error_msg}")

    # ── Final Summary ─────────────────────────────────────────────────
    step_final, tf = log_step_start(AGENT, "Final metric summary")
    ok = sum(1 for m in metrics.values() if m["status"] == "ok")
    total = len(metrics)

    for mid in sorted(metrics.keys()):
        m = metrics[mid]
        if m["status"] == "ok":
            log_success(AGENT, f"  {mid} — {m['name']}: OK")
        else:
            log_error(AGENT, f"  {mid} — {m['name']}: {m['status'].upper()}")

    log_step_end(AGENT, step_final, tf, f"{ok}/{total} metrics computed")

    elapsed = time.time() - t_total
    log_success(AGENT, f"Metric computation complete in {elapsed:.2f}s")

    return {
        "metrics": metrics,
        "messages": all_messages,
    }


def _build_schema_text(schema, dfs: dict) -> str:
    """Build a readable schema mapping text for the LLM."""
    lines = []
    lines.append("AVAILABLE DATA:")
    for df_name, df in dfs.items():
        lines.append(f"  {df_name}: {len(df):,} rows × {len(df.columns)} columns")
        lines.append(f"    DataFrame variable: {'loans_df' if df_name == 'loans' else 'txns_df' if df_name == 'transactions' else f'extra_dfs[\"{df_name}\"]'}")
        lines.append(f"    Columns: {list(df.columns)}")

    if schema.get("loan_file"):
        lines.append(f"\nLoan file: {schema['loan_file']}")
    else:
        lines.append("\nLoan file: NOT AVAILABLE (loans_df is None)")
    if schema.get("transaction_file"):
        lines.append(f"Transaction file: {schema['transaction_file']}")
    else:
        lines.append("Transaction file: NOT AVAILABLE (txns_df is None)")

    lines.append("\nField Mappings:")
    for canonical, fm in sorted(schema["field_mappings"].items()):
        lines.append(f"  {canonical} → {fm['file']}['{fm['column']}']")
    return "\n".join(lines)


def _make_agent_print(agent_name: str):
    """Create a print function that logs through our logger."""
    def _print(*args, **kwargs):
        msg = " ".join(str(a) for a in args)
        log_info(agent_name, f"  [code] {msg}")
    return _print


def _get_llm_insight(llm, metric_name: str, result_data) -> str:
    """Ask LLM to interpret the computed metric results."""
    try:
        # Summarise result for LLM (truncate large data)
        if isinstance(result_data, dict):
            summary = {}
            for k, v in result_data.items():
                if isinstance(v, list) and len(v) > 5:
                    summary[k] = f"[{len(v)} items, first 3: {v[:3]}]"
                elif isinstance(v, dict) and len(v) > 10:
                    summary[k] = f"{{dict with {len(v)} keys}}"
                else:
                    summary[k] = v
            result_str = json.dumps(summary, default=str, indent=2)[:2000]
        else:
            result_str = str(result_data)[:2000]

        response = llm.invoke([
            HumanMessage(content=(
                f"You are a financial analyst. Briefly interpret this {metric_name} result "
                f"for an Indian NBFC loan portfolio. 2-3 sentences max.\n\n{result_str}"
            ))
        ])
        return extract_text(response).strip()
    except Exception:
        return ""


def _retry_with_fix(llm, prompt_template, schema_text, original_code,
                     error_msg, traceback_str, loans_df, txns_df, extra_dfs,
                     agent_name, metric_name) -> dict | None:
    """Ask LLM to fix its own code after an error."""
    try:
        # Give LLM the error and ask to fix
        # Build column info for all available DataFrames
        col_info = ""
        if loans_df is not None:
            col_info += f"  loans_df.columns = {list(loans_df.columns)[:30]}\n"
        else:
            col_info += "  loans_df = None\n"
        if txns_df is not None:
            col_info += f"  txns_df.columns = {list(txns_df.columns)}\n"
        else:
            col_info += "  txns_df = None\n"
        for k, v in extra_dfs.items():
            col_info += f"  extra_dfs['{k}'].columns = {list(v.columns)[:30]}\n"

        fix_prompt = (
            f"Your previous code for {metric_name} failed with this error:\n\n"
            f"ERROR: {error_msg}\n\n"
            f"TRACEBACK (last 300 chars):\n{traceback_str[-300:]}\n\n"
            f"ORIGINAL CODE:\n{original_code[:1500]}\n\n"
            f"Available DataFrames:\n{col_info}\n"
            f"Fix the code. Return ONLY executable Python code. "
            f"Store the result in a variable called 'result'. "
            f"If the data needed is not available, set result = {{'error': 'not_computable', 'reason': '...'}}."
        )

        response = llm.invoke([
            SystemMessage(content=METRIC_SYSTEM),
            HumanMessage(content=fix_prompt),
        ])

        fixed_code = extract_text(response).strip()
        if fixed_code.startswith("```"):
            fixed_code = fixed_code.split("\n", 1)[1]
            if fixed_code.endswith("```"):
                fixed_code = fixed_code.rsplit("```", 1)[0]
        fixed_code = fixed_code.strip()

        log_info(agent_name, f"Executing fixed code ({len(fixed_code)} chars)...")

        exec_namespace = {
            "loans_df": loans_df.copy() if loans_df is not None else None,
            "txns_df": txns_df.copy() if txns_df is not None else None,
            "extra_dfs": {k: v.copy() for k, v in extra_dfs.items()},
            "pd": pd,
            "np": np,
            "datetime": datetime,
            "result": None,
            "print": _make_agent_print(agent_name),
            "normalize_dpd_bucket": _normalize_dpd_bucket,
        }

        exec(fixed_code, exec_namespace)
        return exec_namespace.get("result")

    except Exception as e:
        log_error(agent_name, f"Retry also failed: {e}")
        return None
