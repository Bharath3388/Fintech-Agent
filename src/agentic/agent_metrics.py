"""
Metric Computation Agent — LLM-Powered (Parallel)
===================================================
For each metric, sends the schema mapping to Gemini and asks it to
GENERATE Python code. Then executes that code on the loaded DataFrames.

Metrics are computed in PARALLEL using ThreadPoolExecutor — independent
metric groups (grouped by CSV dependency) run simultaneously.

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
from concurrent.futures import ThreadPoolExecutor, as_completed

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

# ── M1 key normalization — LLM may produce different key names ────────────
_M1_KEY_MAP = {
    # total_pos_cr variants
    "total_pos_crores": "total_pos_cr",
    "total_pos": "total_pos_cr",
    "pos_crores": "total_pos_cr",
    "total_pos_cr": "total_pos_cr",
    # interest_outstanding_cr variants
    "interest_outstanding_crores": "interest_outstanding_cr",
    "interest_outstanding": "interest_outstanding_cr",
    "interest_outstanding_cr": "interest_outstanding_cr",
    # active_loan_count variants
    "active_loans": "active_loan_count",
    "active_count": "active_loan_count",
    "active_loan_count": "active_loan_count",
    "loan_count": "active_loan_count",
    # wair variants
    "wair_pct": "wair_pct",
    "wair": "wair_pct",
    "weighted_avg_interest_rate": "wair_pct",
    "weighted_avg_interest_rate_pct": "wair_pct",
    "weighted_average_interest_rate": "wair_pct",
    # wart variants
    "wart_months": "wart_months",
    "wart": "wart_months",
    "weighted_avg_residual_tenor_months": "wart_months",
    "weighted_average_residual_tenor_months": "wart_months",
    "residual_tenor_months": "wart_months",
}

def _normalize_m1_keys(data: dict) -> dict:
    """Standardize M1 result keys to canonical names.
    Handles both flat dict (legacy) and new yearly_data structure."""
    if not isinstance(data, dict):
        return data

    # New yearly structure — normalize keys within nested dicts
    if "yearly_data" in data or "overall" in data:
        out = {}
        if "yearly_data" in data:
            out["yearly_data"] = [
                {_M1_KEY_MAP.get(k.lower().strip(), k): v for k, v in row.items()}
                for row in data["yearly_data"]
            ]
        if "years" in data:
            out["years"] = data["years"]
        if "overall" in data and isinstance(data["overall"], dict):
            out["overall"] = {
                _M1_KEY_MAP.get(k.lower().strip(), k): v
                for k, v in data["overall"].items()
            }
        return out

    # Legacy flat dict — convert to new structure
    out = {}
    for k, v in data.items():
        canonical = _M1_KEY_MAP.get(k.lower().strip(), k)
        out[canonical] = v
    # Wrap legacy flat result into the new structure for consistency
    return {
        "yearly_data": [],
        "years": [],
        "overall": out,
    }


def _compute_single_metric_group(
    metric_key: str,
    metric_name: str,
    prompt_template: str,
    schema_text: str,
    non_computable: dict,
    dfs: dict[str, pd.DataFrame],
) -> tuple[dict[str, MetricResultItem], list[str]]:
    """Compute a single metric group. Thread-safe — each call gets its own LLM instance
    and its own deep-copies of all available DataFrames."""
    metrics: dict[str, MetricResultItem] = {}
    messages: list[str] = []
    metric_ids = metric_key.split("_") if "_" in metric_key else [metric_key]

    step, t0 = log_step_start(AGENT, f"{metric_key}: {metric_name}")

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
        messages.append(f"[{AGENT}] {metric_key}: SKIPPED — {skip_reason}")
        return metrics, messages

    # ── Build exec namespace with all available DataFrames ─────────
    loans_df = dfs.get("loans").copy() if dfs.get("loans") is not None else None
    txns_df = dfs.get("transactions").copy() if dfs.get("transactions") is not None else None
    extra_dfs = {k: v.copy() for k, v in dfs.items()
                 if k not in ("loans", "transactions")}

    # Each thread gets its own LLM instance (connection)
    llm = get_llm(temperature=0.0)

    generated_code = ""
    try:
        # ── Ask LLM to generate code ──────────────────────────────
        log_info(AGENT, f"[{metric_key}] Asking Gemini to generate computation code...")

        llm_messages = [
            SystemMessage(content=METRIC_SYSTEM),
            HumanMessage(content=prompt_template.format(schema_mapping=schema_text)),
        ]

        response = llm.invoke(llm_messages)
        generated_code = extract_text(response).strip()

        # Clean markdown fences
        if generated_code.startswith("```"):
            lines = generated_code.split("\n")
            generated_code = "\n".join(lines[1:])
            if generated_code.endswith("```"):
                generated_code = generated_code.rsplit("```", 1)[0]
        generated_code = generated_code.strip()

        log_info(AGENT, f"[{metric_key}] LLM generated {len(generated_code)} chars of code")

        # ── Execute the generated code ────────────────────────────
        log_info(AGENT, f"[{metric_key}] Executing generated code...")

        exec_namespace = {
            "loans_df": loans_df,
            "txns_df": txns_df,
            "extra_dfs": extra_dfs,
            "pd": pd,
            "np": np,
            "datetime": datetime,
            "result": None,
            "print": _make_agent_print(AGENT),
            "normalize_dpd_bucket": _normalize_dpd_bucket,
        }

        exec(generated_code, exec_namespace)

        result_data = exec_namespace.get("result")

        # Normalize M1 keys to canonical names
        if result_data is not None and metric_key == "M1":
            result_data = _normalize_m1_keys(result_data)

        if result_data is None:
            log_warn(AGENT, f"[{metric_key}] Code executed but 'result' variable not set")
            for mid in metric_ids:
                metrics[mid] = MetricResultItem(
                    metric_id=mid, name=metric_name,
                    status="error", data=None,
                    llm_insight="Code ran but produced no result",
                )
        else:
            # ── Check if result has per-metric sub-keys ───────────
            if isinstance(result_data, dict) and all(mid in result_data for mid in metric_ids):
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
                    log_success(AGENT, f"[{metric_key}] {mid} — {metric_name}: {sub_status.upper()}")
            else:
                insight = _get_llm_insight(llm, metric_name, result_data)
                for mid in metric_ids:
                    metrics[mid] = MetricResultItem(
                        metric_id=mid, name=metric_name,
                        status="ok", data=result_data,
                        llm_insight=insight,
                    )
                    log_success(AGENT, f"[{metric_key}] {mid} — {metric_name}: OK")

            log_info(AGENT, f"[{metric_key}] LLM Insight: {insight[:200]}")

        log_step_end(AGENT, step, t0, "OK")
        messages.append(f"[{AGENT}] {metric_key}: OK")

    except Exception as e:
        error_msg = f"{type(e).__name__}: {e}"
        tb = traceback.format_exc()
        log_error(AGENT, f"[{metric_key}] Execution failed: {error_msg}")
        log_info(AGENT, f"[{metric_key}] Traceback:\n{tb[-500:]}")

        # ── Ask LLM to fix the code ───────────────────────────────
        log_info(AGENT, f"[{metric_key}] Asking Gemini to fix the code...")
        # For retry, pass original DataFrames (_retry_with_fix does its own .copy())
        retry_loans = dfs.get("loans")
        retry_txns = dfs.get("transactions")
        retry_extra = {k: v for k, v in dfs.items()
                       if k not in ("loans", "transactions")}

        fixed = _retry_with_fix(llm, prompt_template, schema_text,
                                 generated_code, error_msg, tb,
                                 retry_loans, retry_txns, retry_extra, AGENT, metric_name)

        if fixed is not None:
            if metric_key == "M1":
                fixed = _normalize_m1_keys(fixed)
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
                    log_success(AGENT, f"[{metric_key}] {mid} — {metric_name}: {sub_status.upper()} (after retry)")
            else:
                for mid in metric_ids:
                    metrics[mid] = MetricResultItem(
                        metric_id=mid, name=metric_name,
                        status="ok", data=fixed,
                        llm_insight=insight,
                    )
                    log_success(AGENT, f"[{metric_key}] {mid} — {metric_name}: OK (after retry)")
            log_step_end(AGENT, step, t0, "OK (retried)")
            messages.append(f"[{AGENT}] {metric_key}: OK (after self-correction)")
        else:
            for mid in metric_ids:
                metrics[mid] = MetricResultItem(
                    metric_id=mid, name=metric_name,
                    status="error", data={"error": error_msg},
                    llm_insight="",
                )
            log_step_fail(AGENT, step, t0, error_msg)
            messages.append(f"[{AGENT}] {metric_key}: FAILED — {error_msg}")

    return metrics, messages


def compute_metrics(state: AgentState) -> dict:
    """LangGraph node: Use LLM to generate and execute metric computation code.

    Metrics are computed in PARALLEL using ThreadPoolExecutor.
    Independent metric groups run simultaneously — each gets its own LLM
    instance and deep-copies of all available DataFrames.
    """
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

    if not dfs:
        return {
            "errors": ["No DataFrames loaded"],
            "messages": [f"[{AGENT}] ERROR: No data in memory"],
        }

    # Build schema mapping text for LLM (shared across all threads, read-only)
    schema_text = _build_schema_text(schema, dfs)

    metrics: dict[str, MetricResultItem] = {}
    all_messages = []

    non_computable = schema.get("non_computable_metrics", {})

    # ── Submit all metric groups to thread pool in parallel ────────────
    log_info(AGENT, f"Submitting {len(METRIC_PROMPTS)} metric groups for PARALLEL computation...")
    with ThreadPoolExecutor(max_workers=len(METRIC_PROMPTS)) as executor:
        future_to_key = {}
        for metric_key, (metric_name, prompt_template) in METRIC_PROMPTS.items():
            future = executor.submit(
                _compute_single_metric_group,
                metric_key, metric_name, prompt_template,
                schema_text, non_computable, dfs,
            )
            future_to_key[future] = metric_key

        for future in as_completed(future_to_key):
            metric_key = future_to_key[future]
            try:
                group_metrics, group_messages = future.result()
                metrics.update(group_metrics)
                all_messages.extend(group_messages)
            except Exception as e:
                log_error(AGENT, f"[{metric_key}] Thread crashed: {e}")
                all_messages.append(f"[{AGENT}] {metric_key}: THREAD CRASH — {e}")

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

    # ── Save intermediate metric results as JSON ──────────────────────
    _save_intermediate_metrics(metrics)

    return {
        "metrics": metrics,
        "messages": all_messages,
    }


# ── Output directory for intermediate results ─────────────────────────────
_OUTPUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "output_charts"))


def _save_intermediate_metrics(metrics: dict[str, MetricResultItem]) -> None:
    """Save computed metric results as JSON before passing to the visualization agent."""
    try:
        os.makedirs(_OUTPUT_DIR, exist_ok=True)
        out_path = os.path.join(_OUTPUT_DIR, "intermediate_metrics.json")

        serializable = {}
        for mid in sorted(metrics.keys()):
            m = metrics[mid]
            serializable[mid] = {
                "metric_id": m["metric_id"],
                "name": m["name"],
                "status": m["status"],
                "data": m.get("data"),
                "llm_insight": m.get("llm_insight", ""),
            }

        with open(out_path, "w") as f:
            json.dump(serializable, f, indent=2, default=str)

        log_success(AGENT, f"Saved intermediate metrics → {out_path}")
    except Exception as e:
        log_warn(AGENT, f"Could not save intermediate metrics: {e}")


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
    """Ask LLM to fix its own code after an error — up to 3 self-correction attempts."""
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

    current_code = original_code
    current_error = error_msg
    current_tb = traceback_str

    for attempt in range(1, 4):  # attempts 1, 2, 3
        try:
            fix_prompt = (
                f"Your previous code for {metric_name} failed with this error:\n\n"
                f"ERROR: {current_error}\n\n"
                f"TRACEBACK (last 300 chars):\n{current_tb[-300:]}\n\n"
                f"FAILING CODE:\n{current_code[:1500]}\n\n"
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

            log_info(agent_name, f"Executing fixed code (attempt {attempt}/3, {len(fixed_code)} chars)...")

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
            result = exec_namespace.get("result")
            if result is not None:
                log_info(agent_name, f"Fix succeeded on attempt {attempt}/3")
                return result

            # result is None — treat as an error and retry
            current_code = fixed_code
            current_error = "Code executed but 'result' variable was not set"
            current_tb = ""

        except Exception as e:
            current_error = f"{type(e).__name__}: {e}"
            current_tb = traceback.format_exc()
            current_code = fixed_code if 'fixed_code' in dir() else current_code
            log_error(agent_name, f"Retry attempt {attempt}/3 failed: {current_error}")

    log_error(agent_name, f"All 3 retry attempts failed. Last error: {current_error}")
    return None
