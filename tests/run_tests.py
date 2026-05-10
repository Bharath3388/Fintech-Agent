"""
Test runner — runs the pipeline on all 3 synthetic datasets
and uses the LLM to compare computed metrics against ground truth.

Instead of brittle hard-coded parsers, we send both the pipeline result
and the ground truth to Gemini and ask it to judge each check.
"""
import requests, json, time, os, sys

# Make src/ importable
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from langchain_core.messages import SystemMessage, HumanMessage
from agentic.llm_config import get_llm, extract_text

BASE = "http://localhost:8000"
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))

DATASETS = {
    "TC1_Clean": os.path.join(TESTS_DIR, "test_case_1"),
    "TC2_Stressed": os.path.join(TESTS_DIR, "test_case_2"),
    "TC3_EdgeCases": os.path.join(TESTS_DIR, "test_case_3"),
}

TOLERANCE_PCT = 5.0  # relative tolerance for numeric comparisons


# ── LLM Judge ──────────────────────────────────────────────────────────────

JUDGE_SYSTEM = """\
You are a strict test-validation judge for a fintech loan-portfolio analytics pipeline.
You will receive:
1. GROUND TRUTH — the expected values for this test case (manually computed).
2. PIPELINE RESULT — the actual output from the analytics pipeline (metrics JSON).
3. CHECKS — a list of specific assertions to evaluate.

For each check, determine PASS or FAIL:
- Numeric comparisons: allow up to {tolerance}% relative tolerance. If the expected value is 0, allow ±0.5 absolute tolerance.
- Status checks: the metric status must be "ok" or "partial" to pass.
- Existence checks: the field/data must exist and be non-empty.
- The pipeline may use different JSON key names (e.g. "pos_crores" vs "pos_amount_crore" vs "amount_crores") — look for the semantic match regardless of exact key name.
- The pipeline may nest data differently (flat dict vs list of dicts vs dict of dicts) — extract the value by meaning, not by exact path.

Respond with ONLY a valid JSON array. Each element must be:
{{"check": "<check_name>", "result": "PASS" or "FAIL", "actual": "<what you found>", "reason": "<brief explanation>"}}

No markdown, no extra text. Just the JSON array.
"""

# ── Check definitions per test case ────────────────────────────────────────

TC1_CHECKS = [
    "M1 metric status is ok or partial",
    "M1 active_loan_count equals 10",
    "M1 WAIR is 0 or near 0 (all loans fully paid, POS=0 so WAIR has no weight)",
    "M2 metric status is ok or partial",
    "M2 total POS across all DPD buckets is 0 or near 0 (all loans fully paid off)",
    "M3 metric status is ok or partial",
    "M3 overall collection efficiency is approximately 100% (all EMIs paid on time)",
    "M4 metric status is ok or partial",
    "M5 or M5_M6_M7_M8 metric status is ok or partial",
    "M9 metric status is ok or partial",
    "At least 3 charts were generated (have non-empty html_snippet)",
]

TC2_CHECKS = [
    "M1 metric status is ok or partial",
    "M1 active_loan_count equals 10",
    "M1 total_pos_cr is approximately {M1[total_pos_cr]} Cr",
    "M1 WAIR is approximately {M1[wair_pct]}%",
    "M2 metric status is ok or partial",
    "M2 Current bucket POS is approximately {M2[Current]} Cr",
    "M2 DPD 1-30 bucket POS is approximately {M2[DPD 1-30]} Cr",
    "M2 DPD 31-60 bucket POS is approximately {M2[DPD 31-60]} Cr",
    "M2 DPD 61-90 bucket POS is approximately {M2[DPD 61-90]} Cr",
    "M2 DPD 90+ bucket POS is approximately {M2[DPD 90+]} Cr",
    "M3 metric status is ok or partial",
    "M3 overall collection efficiency is approximately {M3[overall_ce_pct]}%",
    "M5 or M5_M6_M7_M8 metric status is ok or partial",
    "M5/M8 Current→Current transition percentage is approximately 66.67% (4 out of 6 loans stayed Current)",
    "M5/M7 Current→Current transition count is approximately 4 loans",
    "M9 metric status is ok or partial",
    "At least 3 charts were generated (have non-empty html_snippet)",
]

TC3_CHECKS = [
    "M1 metric status is ok or partial",
    "M1 active_loan_count equals 6",
    "M2 metric status is ok or partial",
    "M2 DPD 90+ bucket has POS > 0 (from zero-pay and half-pay loans)",
    "M3 metric status is ok or partial",
    "M3 overall collection efficiency is approximately {M3[overall_ce_pct]}%",
    "M3 overall CE is between 50% and 110% (mix of full-pay and zero-pay)",
    "M3 has monthly time-series data with at least 1 month",
    "M5 or M5_M6_M7_M8 metric status is ok or partial",
    "At least 3 charts were generated (have non-empty html_snippet)",
]


def format_checks(checks: list[str], gt: dict) -> list[str]:
    """Interpolate ground truth values into check strings."""
    formatted = []
    for c in checks:
        try:
            result = c
            for key in gt:
                if isinstance(gt[key], dict):
                    for subkey, val in gt[key].items():
                        placeholder = f"{{{key}[{subkey}]}}"
                        if placeholder in result:
                            if isinstance(val, float):
                                result = result.replace(placeholder, f"{val:.4f}")
                            else:
                                result = result.replace(placeholder, str(val))
            formatted.append(result)
        except Exception:
            formatted.append(c)
    return formatted


def run_analysis(dataset_dir):
    """POST /analyze with all CSVs in the directory."""
    csvs = sorted([
        os.path.join(dataset_dir, f)
        for f in os.listdir(dataset_dir)
        if f.endswith(".csv")
    ])
    print(f"  Files: {[os.path.basename(c) for c in csvs]}")
    t0 = time.time()
    r = requests.post(f"{BASE}/analyze", json={"csv_paths": csvs}, timeout=900)
    elapsed = time.time() - t0
    print(f"  HTTP {r.status_code} | {elapsed:.0f}s")
    if r.status_code != 200:
        print(f"  ERROR: {r.text[:300]}")
        return None
    return r.json()


def llm_judge(pipeline_result: dict, ground_truth: dict, checks: list[str]) -> list[dict]:
    """Use the LLM to evaluate each check against pipeline output and ground truth."""
    llm = get_llm(temperature=0.0)

    # Build a compact view: metric statuses + data (truncated per metric) + charts summary
    metrics_compact = {}
    for mid, m in pipeline_result.get("metrics", {}).items():
        data_str = json.dumps(m.get("data", {}), default=str)
        metrics_compact[mid] = {
            "status": m.get("status", "not_available"),
            "data": json.loads(data_str[:3000]) if len(data_str) <= 3000 else data_str[:3000] + "...(truncated)",
        }

    charts_summary = {}
    for mid, c in pipeline_result.get("charts", {}).items():
        charts_summary[mid] = {
            "has_html_snippet": bool(c.get("html_snippet", "")),
            "has_plotly_json": bool(c.get("plotly_json")),
        }

    trimmed = {
        "metrics": metrics_compact,
        "charts": charts_summary,
        "summary": pipeline_result.get("summary", {}),
    }

    prompt = f"""GROUND TRUTH:
{json.dumps(ground_truth, indent=2, default=str)}

PIPELINE RESULT:
{json.dumps(trimmed, indent=2, default=str)}

CHECKS TO EVALUATE:
{json.dumps(checks, indent=2)}

Evaluate each check. Respond with ONLY a JSON array."""

    messages = [
        SystemMessage(content=JUDGE_SYSTEM.format(tolerance=TOLERANCE_PCT)),
        HumanMessage(content=prompt),
    ]

    response = extract_text(llm.invoke(messages))

    # Parse JSON from response (strip markdown fences if present)
    text = response.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        if text.startswith("json"):
            text = text[4:].strip()

    try:
        results = json.loads(text)
        if not isinstance(results, list):
            results = [results]
        return results
    except json.JSONDecodeError:
        print(f"  ⚠️  LLM judge response was not valid JSON, treating all as FAIL")
        print(f"     Raw: {response[:300]}")
        return [{"check": c, "result": "FAIL", "actual": "parse error",
                 "reason": "LLM response not valid JSON"} for c in checks]


def main():
    all_results = {}
    total_pass = 0
    total_fail = 0

    check_map = {
        "TC1_Clean": TC1_CHECKS,
        "TC2_Stressed": TC2_CHECKS,
        "TC3_EdgeCases": TC3_CHECKS,
    }

    for label, ddir in DATASETS.items():
        print(f"\n{'='*70}")
        print(f"  {label}")
        print(f"{'='*70}")

        gt = json.load(open(os.path.join(ddir, "ground_truth.json")))

        # Run pipeline
        result = run_analysis(ddir)
        if result is None:
            print("  ❌ PIPELINE FAILED — skipping validation")
            n_checks = len(check_map.get(label, []))
            total_fail += n_checks
            all_results[label] = {"passed": 0, "failed": n_checks, "details": []}
            continue

        # Save raw result for debugging
        json.dump(result, open(f"/tmp/test_result_{label}.json", "w"), indent=2)

        # Format checks with ground truth values
        raw_checks = check_map.get(label, [])
        checks = format_checks(raw_checks, gt)

        # Ask LLM to judge
        print(f"  Evaluating {len(checks)} checks with LLM judge...")
        t0 = time.time()
        judgments = llm_judge(result, gt, checks)
        print(f"  LLM judge responded in {time.time()-t0:.1f}s\n")

        # Print results
        pass_count = 0
        fail_count = 0
        details = []
        for j in judgments:
            check_name = j.get("check", "?")
            passed = j.get("result", "FAIL").upper() == "PASS"
            actual = j.get("actual", "?")
            reason = j.get("reason", "")
            icon = "✅" if passed else "❌"
            print(f"  {icon} {check_name}")
            print(f"     actual={actual} | {reason}")
            if passed:
                pass_count += 1
            else:
                fail_count += 1
            details.append(j)

        print(f"\n  Subtotal: {pass_count}/{pass_count+fail_count} passed")
        total_pass += pass_count
        total_fail += fail_count
        all_results[label] = {"passed": pass_count, "failed": fail_count, "details": details}

    # ── Final Summary ──
    print(f"\n{'='*70}")
    print(f"  FINAL RESULT: {total_pass}/{total_pass+total_fail} checks passed")
    print(f"{'='*70}")
    for label, r in all_results.items():
        icon = "✅" if r["failed"] == 0 else "⚠️"
        print(f"  {icon} {label}: {r['passed']}/{r['passed']+r['failed']}")

    # Save structured results
    summary = {
        "total_passed": total_pass,
        "total_failed": total_fail,
        "total_checks": total_pass + total_fail,
        "pass_rate_pct": round(total_pass / (total_pass + total_fail) * 100, 1) if (total_pass + total_fail) else 0,
        "details": {label: r for label, r in all_results.items()},
    }
    json.dump(summary, open("/tmp/test_summary.json", "w"), indent=2)
    print(f"\n  Full results → /tmp/test_summary.json")

    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
