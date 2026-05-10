"""
Chat Agent — Answers natural-language questions about the analysed portfolio.

The agent receives the full pipeline state (schema + metrics + validation)
and a user question, then generates a concise, accurate answer using Gemini.
Conversation history is passed in so the agent maintains context across turns.
"""

from __future__ import annotations
import json
from .llm_config import get_llm, extract_text

_SYSTEM_PROMPT = """\
You are an expert Loan Portfolio Analyst AI assistant embedded inside a fintech analytics platform.
You have been given the results of an automated analysis of a real loan portfolio dataset.

Your job:
- Answer the user's questions about this portfolio clearly and accurately.
- Use ONLY the data provided in the PORTFOLIO CONTEXT below. Do NOT hallucinate numbers.
- Format numbers with commas and appropriate units (Cr, %, months, INR, etc.).
- If asked about something not covered by the data, say so honestly.
- Be concise but thorough. Use bullet points or markdown tables when helpful.
- When comparing DPD buckets or metrics, use the actual values from context.
- "Cr" means Indian Crore (10 million INR). "POS" = Principal Outstanding.
- "WAIR" = Weighted Average Interest Rate. "WART" = Weighted Average Residual Tenor.
- "CE" = Collection Efficiency (actual payments / scheduled payments × 100).
- "DPD" = Days Past Due. Buckets: Current (0 DPD), DPD 1-30, DPD 31-60, DPD 61-90, DPD 90+.
- M5 = DPD transition matrix by POS (INR). M6 = by POS %. M7 = by loan count. M8 = by count %.

PORTFOLIO CONTEXT:
{context}
"""


def _format_matrix(m6: dict, m7: dict) -> str:
    """Format M5-M8 transition matrices as a readable text table."""
    buckets = ["Current", "DPD 1-30", "DPD 31-60", "DPD 61-90", "DPD 90+"]
    rows = []
    for fr in buckets:
        if fr not in m6:
            continue
        row_parts = [f"  From {fr}:"]
        for to in buckets:
            pct = m6.get(fr, {}).get(to, 0)
            cnt = int(m7.get(fr, {}).get(to, 0)) if m7 else 0
            if pct > 0.01:
                row_parts.append(f"    → {to}: {pct:.2f}% ({cnt:,} loans)")
        rows.append("\n".join(row_parts))
    return "\n".join(rows)


def _build_context(state: dict) -> str:
    """Convert pipeline result state into a compact, readable text context for the LLM."""
    lines: list[str] = []

    # ── Dataset / Schema ──────────────────────────────────────────────────
    schema = state.get("schema") or {}
    file_keys = ["loan_file", "transaction_file", "borrower_file", "collateral_file", "collections_file"]
    detected = [k.replace("_file", "").replace("_", " ").title() for k in file_keys if schema.get(k)]
    lines.append("=== DATASET ===")
    lines.append(f"Files detected: {', '.join(detected) if detected else 'Unknown'}")
    lines.append(f"Fields mapped: {schema.get('fields_mapped', 0)}")
    computable = schema.get("computable_metrics", [])
    lines.append(f"Metrics computed: {', '.join(computable) if computable else 'N/A'}")
    non_comp = schema.get("non_computable_metrics", {})
    if non_comp:
        lines.append(f"Metrics skipped: {', '.join(non_comp.keys())} (missing data)")

    # ── Data Quality ──────────────────────────────────────────────────────
    val = state.get("validation") or {}
    lines.append("\n=== DATA QUALITY ===")
    lines.append(f"Validation passed: {val.get('passed', False)}")
    lines.append(f"Total loans: {val.get('total_loans', 0):,}")
    lines.append(f"Total transactions: {val.get('total_transactions', 0):,}")
    errs = val.get("errors", [])
    warns = val.get("warnings", [])
    if errs:
        lines.append(f"Data errors: {len(errs)}")
    if warns:
        lines.append(f"Data warnings: {len(warns)}")

    # ── Metrics ───────────────────────────────────────────────────────────
    metrics = state.get("metrics") or {}

    NAMES = {
        "M1": "Portfolio Summary",
        "M2": "POS by DPD Bucket",
        "M3": "Collection Efficiency (Time Series)",
        "M4": "Collection Efficiency by DPD Bucket",
        "M5": "DPD Transition Matrices (M5-M8)",
        "M6": "DPD Transition % by POS",
        "M7": "DPD Transition Count",
        "M8": "DPD Transition % by Count",
        "M9": "Vintage Cohort Analysis",
    }

    for mid in ["M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8", "M9"]:
        m = metrics.get(mid) or {}
        status = m.get("status", "")
        if status not in ("ok", "partial"):
            continue
        data = m.get("data") or {}
        insight = m.get("llm_insight", "")
        name = NAMES.get(mid, mid)
        lines.append(f"\n=== {mid}: {name} ===")

        try:
            if mid == "M1":
                lines.append(f"  Total Portfolio Outstanding (POS): {data.get('total_pos_cr', 0):,.2f} Cr")
                lines.append(f"  Active Loans: {data.get('active_loan_count', 0):,}")
                lines.append(f"  Weighted Avg Interest Rate (WAIR): {data.get('wair_pct', 0):.4f}%")
                lines.append(f"  Weighted Avg Residual Tenor (WART): {data.get('wart_months', 0):.2f} months")
                if data.get("interest_outstanding_cr"):
                    lines.append(f"  Interest Outstanding: {data['interest_outstanding_cr']:,.2f} Cr")

            elif mid == "M2":
                total = sum(v for v in data.values() if isinstance(v, (int, float)))
                for bucket in ["Current", "DPD 1-30", "DPD 31-60", "DPD 61-90", "DPD 90+"]:
                    amt = data.get(bucket, 0)
                    pct = amt / total * 100 if total else 0
                    lines.append(f"  {bucket:<12}: {amt:>10,.2f} Cr  ({pct:.2f}%)")

            elif mid == "M3":
                overall = data.get("overall_ce_pct") or data.get("overall_ce") or data.get("ce_pct")
                if overall is not None:
                    lines.append(f"  Overall Collection Efficiency: {overall:.4f}%")
                total_due = data.get("total_emi_due") or data.get("total_scheduled")
                total_col = data.get("total_collected") or data.get("total_paid")
                if total_due:
                    lines.append(f"  Total EMI Due: {total_due:,.2f} INR")
                if total_col:
                    lines.append(f"  Total Collected: {total_col:,.2f} INR")
                # Use monthly_recent (last 24) if available; otherwise fall back to full time_series
                ts = data.get("monthly_recent") or data.get("time_series") or data.get("monthly_ce") or []
                if ts:
                    lines.append(f"  Monthly data: {len(ts)} months shown")
                    ce_vals = []
                    rows_text = []
                    for row in ts:
                        month = (row.get("month") or row.get("observation_month") or
                                 row.get("period") or row.get("obs_month") or "")
                        ce = (row.get("ce_pct") or row.get("collection_efficiency") or
                              row.get("ce") or 0)
                        ce_vals.append((month, ce))
                        rows_text.append(f"    {month}: {ce:.2f}%")
                    if ce_vals:
                        min_m, min_v = min(ce_vals, key=lambda x: x[1])
                        max_m, max_v = max(ce_vals, key=lambda x: x[1])
                        avg_v = sum(v for _, v in ce_vals) / len(ce_vals)
                        lines.append(f"  Lowest CE month : {min_m} = {min_v:.2f}%")
                        lines.append(f"  Highest CE month: {max_m} = {max_v:.2f}%")
                        lines.append(f"  Average CE (shown period): {avg_v:.2f}%")
                    lines.extend(rows_text)

            elif mid == "M4":
                if isinstance(data, dict):
                    for bucket, val_item in data.items():
                        if isinstance(val_item, (int, float)):
                            lines.append(f"  {bucket}: {val_item:.2f}%")
                        elif isinstance(val_item, dict):
                            ce = (val_item.get("ce_pct") or val_item.get("ce") or
                                  val_item.get("collection_efficiency") or 0)
                            lines.append(f"  {bucket}: CE = {ce:.2f}%")

            elif mid == "M5":
                # All 4 matrices are stored together in M5's data
                m5 = data.get("m5_pos_inr") or {}
                m6 = data.get("m6_pos_pct") or {}
                m7d = data.get("m7_count") or {}
                m8 = data.get("m8_count_pct") or {}
                meta = data.get("metadata") or {}
                if meta:
                    lines.append(f"  Period: {meta.get('period_T1', '?')} → {meta.get('period_T', '?')}")
                lines.append("  DPD Transition (% of POS by bucket):")
                lines.append(_format_matrix(m6, m7d))
                # Key diagonal stats
                cc_pos_pct = m6.get("Current", {}).get("Current", 0)
                cc_cnt_pct = m8.get("Current", {}).get("Current", 0)
                lines.append(f"  Current→Current (POS %): {cc_pos_pct:.4f}%")
                lines.append(f"  Current→Current (Count %): {cc_cnt_pct:.4f}%")

            elif mid in ("M6", "M7", "M8"):
                # These are stored inside M5 data — skip to avoid duplication
                lines.append("  (Included in M5 above)")

            elif mid == "M9":
                if isinstance(data, list):
                    lines.append(f"  Vintage cohorts: {len(data)} disbursement months")
                    # Extract key fields for every cohort so the chat agent can rank/compare them
                    COHORT_KEY_FIELDS = [
                        "cohort", "disbursement_month", "loans_disbursed", "total_disbursed_cr",
                        "ever_dpd30_pct", "ever_dpd60_pct", "ever_dpd90_pct",
                        "npa_rate_pct", "collection_efficiency_pct", "write_off_rate_pct",
                        "outstanding_cr", "par_30_pct", "par_60_pct", "par_90_pct",
                    ]
                    for row in data:
                        if not isinstance(row, dict):
                            continue
                        cohort = row.get("cohort") or row.get("disbursement_month") or ""
                        parts = []
                        for field in COHORT_KEY_FIELDS:
                            if field in row and field not in ("cohort", "disbursement_month"):
                                val = row[field]
                                if isinstance(val, float):
                                    parts.append(f"{field}={val:.2f}")
                                else:
                                    parts.append(f"{field}={val}")
                        if not parts:  # fallback: dump whatever is in the row
                            parts_str = json.dumps({k: v for k, v in row.items() if k != 'cohort'}, default=str)[:150]
                        else:
                            parts_str = ", ".join(parts)
                        lines.append(f"    {cohort}: {parts_str}")
                elif isinstance(data, dict):
                    lines.append(f"  Vintage data: {json.dumps(data, default=str)[:400]}")

        except Exception:
            lines.append(f"  [raw] {json.dumps(data, default=str)[:200]}")

        if insight:
            lines.append(f"  AI Insight: {insight[:500]}")

    return "\n".join(lines)


def answer_question(
    session_state: dict,
    question: str,
    history: list[dict] | None = None,
) -> str:
    """Answer a user question about the portfolio using the pipeline state.

    Args:
        session_state: The full pipeline result dict (schema, metrics, validation).
        question:      User's natural-language question.
        history:       Previous chat turns [{\"role\": \"user\"/\"assistant\", \"content\": \"...\"}].

    Returns:
        Answer string from the LLM.
    """
    from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

    llm = get_llm(temperature=0.1)
    context = _build_context(session_state)

    messages = [SystemMessage(content=_SYSTEM_PROMPT.format(context=context))]

    # Include last 8 turns of history so multi-turn conversation works
    for turn in (history or [])[-8:]:
        role = turn.get("role", "user")
        content = turn.get("content", "")
        if role == "user":
            messages.append(HumanMessage(content=content))
        else:
            messages.append(AIMessage(content=content))

    messages.append(HumanMessage(content=question))
    response = llm.invoke(messages)
    return extract_text(response)
