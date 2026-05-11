#!/usr/bin/env python3
"""
Benchmark script — runs the pipeline, records timing & metric results.
Saves output to tests/benchmark_result_<branch>.json for comparison.

Usage:
    cd src && python -m tests.benchmark        # auto-detects branch
    cd src && python ../tests/benchmark.py     # also works
"""

import sys
import os
import json
import time
import subprocess

# Ensure src/ is importable
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from dotenv import load_dotenv
load_dotenv()

from agentic.graph import run_pipeline


def get_branch_name() -> str:
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True,
            cwd=os.path.join(os.path.dirname(__file__), ".."),
        )
        return result.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def main():
    # Use medium dataset by default
    data_dir = os.path.join(os.path.dirname(__file__), "..", "data", "Medium Size data Set")
    csv_paths = sorted([
        os.path.join(data_dir, f)
        for f in os.listdir(data_dir)
        if f.endswith(".csv")
    ])

    if not csv_paths:
        print("ERROR: No CSV files found in data/Medium Size data Set/")
        sys.exit(1)

    branch = get_branch_name()
    print(f"\n{'='*60}")
    print(f"  BENCHMARK — branch: {branch}")
    print(f"  Files: {[os.path.basename(p) for p in csv_paths]}")
    print(f"{'='*60}\n")

    t_start = time.time()
    final_state = run_pipeline(csv_paths)
    t_total = time.time() - t_start

    # Extract metric results for comparison
    metrics_raw = final_state.get("metrics", {})
    metrics_out = {}
    for mid in sorted(metrics_raw.keys()):
        m = metrics_raw[mid]
        metrics_out[mid] = {
            "status": m["status"],
            "data": m.get("data"),
        }

    # Extract chart results
    charts_raw = final_state.get("charts", {})
    charts_summary = {}
    for mid in sorted(charts_raw.keys()):
        c = charts_raw[mid]
        charts_summary[mid] = "ok" if "error" not in c else f"error: {c['error'][:100]}"

    result = {
        "branch": branch,
        "total_time_seconds": round(t_total, 2),
        "metrics_ok": sum(1 for m in metrics_out.values() if m["status"] == "ok"),
        "metrics_total": len(metrics_out),
        "charts_ok": sum(1 for v in charts_summary.values() if v == "ok"),
        "charts_total": len(charts_summary),
        "metric_statuses": {mid: m["status"] for mid, m in metrics_out.items()},
        "metric_data": {},
        "chart_statuses": charts_summary,
    }

    # Store numeric/summary metric data for comparison (not huge nested dicts)
    for mid, m in metrics_out.items():
        data = m.get("data")
        if isinstance(data, dict):
            # For M1: store the whole thing (small)
            # For others: store keys and sample
            if mid == "M1":
                result["metric_data"][mid] = data
            else:
                result["metric_data"][mid] = {
                    "type": "dict",
                    "keys": list(data.keys())[:20],
                    "num_keys": len(data),
                }
        elif isinstance(data, list):
            result["metric_data"][mid] = {
                "type": "list",
                "length": len(data),
            }
        else:
            result["metric_data"][mid] = str(data)[:200] if data else None

    out_path = os.path.join(
        os.path.dirname(__file__),
        f"benchmark_result_{branch.replace('/', '_')}.json",
    )
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2, default=str)

    print(f"\n{'='*60}")
    print(f"  BENCHMARK COMPLETE — {branch}")
    print(f"  Total time: {t_total:.2f}s")
    print(f"  Metrics: {result['metrics_ok']}/{result['metrics_total']} OK")
    print(f"  Charts:  {result['charts_ok']}/{result['charts_total']} OK")
    print(f"  Saved:   {out_path}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
