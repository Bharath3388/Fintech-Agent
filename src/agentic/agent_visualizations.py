"""
Visualization Agent — LLM-Generated Interactive Charts (Plotly)
================================================================
After metrics are computed, this agent asks Gemini to generate Plotly code
that turns each metric's result data into interactive charts.

No hardcoded chart logic — the LLM decides the chart design, layout,
annotations and formatting based on the metric data and a style guide.
"""

from __future__ import annotations
import os
import json
import time
import traceback

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import plotly.io as pio

from agentic.state import AgentState
from agentic.llm_config import get_llm, extract_text
from agentic.prompts import VIZ_SYSTEM, VIZ_TASK_TEMPLATE
from langchain_core.messages import SystemMessage, HumanMessage
from core.logger import (
    log_banner, log_step_start, log_step_end, log_step_fail,
    log_info, log_warn, log_error, log_success,
    reset_steps,
)

AGENT = "Visualization-AI"

# ── Output directory ──────────────────────────────────────────────────────
OUTPUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "output_charts"))


def generate_visualizations(state: AgentState) -> dict:
    """LangGraph node: Use LLM to generate Plotly visualisation code for computed metrics."""
    reset_steps(AGENT)
    log_banner(AGENT)
    t_total = time.time()

    metrics = state.get("metrics", {})
    if not metrics:
        return {
            "charts": {},
            "messages": [f"[{AGENT}] No metrics to visualize"],
        }

    # Collect only successful metric data
    metrics_data = {}
    for mid, m in metrics.items():
        if m.get("status") == "ok" and m.get("data"):
            data = m["data"]
            # Skip metrics whose data is an error dict
            if isinstance(data, dict) and "error" in data:
                continue
            metrics_data[mid] = {
                "name": m["name"],
                "data": _truncate_for_prompt(data),
            }

    if not metrics_data:
        log_warn(AGENT, "No successful metrics with data — nothing to visualize")
        return {
            "charts": {},
            "messages": [f"[{AGENT}] No data to visualize"],
        }

    log_info(AGENT, f"Generating interactive charts for {len(metrics_data)} metrics: {list(metrics_data.keys())}")

    llm = get_llm(temperature=0.0)
    all_charts: dict = {}
    all_messages: list[str] = []

    # Generate charts in batches (group small metrics, individual for complex)
    batch_metrics = {}
    for mid, mdata in metrics_data.items():
        batch_metrics[mid] = mdata

    # Try batch generation first
    step, t0 = log_step_start(AGENT, "Batch chart generation")
    try:
        charts = _generate_batch(llm, batch_metrics)
        all_charts.update(charts)
        generated = [mid for mid, c in charts.items() if "error" not in c]
        log_success(AGENT, f"Batch generated {len(generated)} charts: {generated}")
        log_step_end(AGENT, step, t0, f"{len(generated)} charts")
    except Exception as e:
        log_error(AGENT, f"Batch generation failed: {e}")
        log_step_end(AGENT, step, t0, "FAILED")

    # Retry individual metrics that failed or were missed
    missing = [mid for mid in metrics_data if mid not in all_charts or "error" in all_charts.get(mid, {})]
    if missing:
        step2, t1 = log_step_start(AGENT, f"Individual retry for {len(missing)} metrics")
        for mid in missing:
            try:
                chart = _generate_single(llm, mid, metrics_data[mid])
                if chart and "error" not in chart:
                    all_charts[mid] = chart
                    log_success(AGENT, f"  {mid}: OK (individual)")
                else:
                    log_warn(AGENT, f"  {mid}: failed individually")
            except Exception as e:
                log_error(AGENT, f"  {mid}: {e}")
                all_charts[mid] = {"error": str(e)}
        log_step_end(AGENT, step2, t1)

    # Save HTML files locally
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    for mid, chart in all_charts.items():
        if "error" not in chart and "html_snippet" in chart:
            html_path = os.path.join(OUTPUT_DIR, f"{mid.lower()}_interactive.html")
            try:
                with open(html_path, "w") as f:
                    f.write(_wrap_full_html(chart["html_snippet"], mid))
                chart["html_path"] = html_path
                log_info(AGENT, f"  Saved {html_path}")
            except Exception:
                pass

    elapsed = time.time() - t_total
    ok_count = sum(1 for c in all_charts.values() if "error" not in c)
    log_success(AGENT, f"Visualization complete: {ok_count}/{len(metrics_data)} charts in {elapsed:.1f}s")

    all_messages.append(f"[{AGENT}] Generated {ok_count}/{len(metrics_data)} interactive charts")

    return {
        "charts": all_charts,
        "messages": all_messages,
    }


# ═══════════════════════════════════════════════════════════════════════════
#  Internal helpers
# ═══════════════════════════════════════════════════════════════════════════

def _generate_batch(llm, metrics_data: dict) -> dict:
    """Ask LLM to generate Plotly code for all metrics in one shot."""
    data_summary = _build_data_summary(metrics_data)

    messages = [
        SystemMessage(content=VIZ_SYSTEM),
        HumanMessage(content=VIZ_TASK_TEMPLATE.format(
            metrics_summary=data_summary,
            metric_ids=", ".join(metrics_data.keys()),
        )),
    ]

    response = llm.invoke(messages)
    code = _extract_code(extract_text(response))

    return _execute_viz_code(code, metrics_data)


def _generate_single(llm, metric_id: str, mdata: dict) -> dict | None:
    """Ask LLM to generate Plotly code for a single metric."""
    data_summary = _build_data_summary({metric_id: mdata})

    prompt = f"""Generate Plotly code for ONE metric only: {metric_id} — {mdata['name']}.

{VIZ_TASK_TEMPLATE.format(
    metrics_summary=data_summary,
    metric_ids=metric_id,
)}"""

    messages = [
        SystemMessage(content=VIZ_SYSTEM),
        HumanMessage(content=prompt),
    ]

    response = llm.invoke(messages)
    code = _extract_code(extract_text(response))

    charts = _execute_viz_code(code, {metric_id: mdata})
    return charts.get(metric_id)


def _execute_viz_code(code: str, metrics_data: dict) -> dict:
    """Execute LLM-generated Plotly code in a sandboxed namespace."""
    # Build read-only metric data (no DataFrames, just results)
    clean_data = {}
    for mid, mdata in metrics_data.items():
        clean_data[mid] = mdata["data"]

    exec_namespace = {
        "metrics_data": clean_data,
        "go": go,
        "px": px,
        "pio": pio,
        "pd": pd,
        "np": np,
        "json": json,
        "result": {},
        "print": _make_print(),
    }

    exec(code, exec_namespace)

    raw_result = exec_namespace.get("result", {})

    charts = {}
    for mid, fig in raw_result.items():
        if isinstance(fig, go.Figure):
            try:
                charts[mid] = {
                    "plotly_json": json.loads(fig.to_json()),
                    "html_snippet": fig.to_html(
                        full_html=False,
                        include_plotlyjs="cdn",
                        config={"displayModeBar": True, "responsive": True},
                    ),
                }
            except Exception as e:
                charts[mid] = {"error": f"Serialization failed: {e}"}
        elif isinstance(fig, dict) and "error" not in fig:
            charts[mid] = {"error": f"Expected go.Figure, got dict"}
        else:
            charts[mid] = {"error": f"Expected go.Figure, got {type(fig).__name__}"}

    return charts


def _extract_code(text: str) -> str:
    """Extract Python code from LLM response (strip markdown fences)."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:])
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
    return text.strip()


def _build_data_summary(metrics_data: dict) -> str:
    """Build a compact text representation of metric results for the LLM prompt."""
    lines = []
    for mid, mdata in sorted(metrics_data.items()):
        lines.append(f"\n{'='*60}")
        lines.append(f"METRIC {mid}: {mdata['name']}")
        lines.append(f"{'='*60}")
        data = mdata["data"]
        data_str = json.dumps(data, indent=2, default=str)
        # Truncate very large data
        if len(data_str) > 3000:
            data_str = data_str[:3000] + "\n... [truncated]"
        lines.append(f"Data:\n{data_str}")
    return "\n".join(lines)


def _truncate_for_prompt(data) -> any:
    """Truncate large arrays/lists in metric data to keep prompt size reasonable."""
    if isinstance(data, dict):
        out = {}
        for k, v in data.items():
            out[k] = _truncate_for_prompt(v)
        return out
    elif isinstance(data, list):
        if len(data) > 50:
            return data[:25] + [{"__truncated__": f"... {len(data) - 25} more items"}]
        return data
    return data


def _make_print():
    """Create a safe print function for exec namespace."""
    def _print(*args, **kwargs):
        msg = " ".join(str(a) for a in args)
        log_info(AGENT, f"  [viz-code] {msg}")
    return _print


def _wrap_full_html(snippet: str, title: str) -> str:
    """Wrap an HTML snippet in a full dark-themed page."""
    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{title} — Interactive Chart</title>
    <style>
        body {{ background: #1a1a2e; color: #e0e0e0; font-family: sans-serif; margin: 20px; }}
        h1 {{ color: #4ade80; text-align: center; }}
    </style>
</head>
<body>
    <h1>{title}</h1>
    {snippet}
</body>
</html>"""
