"""
Chat Agent — Answers natural-language questions about the analysed portfolio.

Two-layer context strategy:
  Layer 1 (always):  Compact summary of all metrics (~2-4K tokens).
  Layer 2 (on-demand): Detailed data slices injected only when the user's
                       question targets a specific metric/period.

This keeps context well within LLM limits even for 100+ month portfolios.
"""

from __future__ import annotations
import json, re
from .llm_config import get_llm, extract_text

# ── Constants ─────────────────────────────────────────────────────────────
_BUCKETS = ["Current", "DPD 1-30", "DPD 31-60", "DPD 61-90", "DPD 90+"]

_METRIC_NAMES = {
    "M1": "Portfolio Summary",
    "M2": "POS by DPD Bucket",
    "M3": "Collection Efficiency (Time Series)",
    "M4": "Collection Efficiency by DPD Bucket",
    "M5": "DPD Transition Matrix — POS INR",
    "M6": "DPD Transition Matrix — POS %",
    "M7": "DPD Transition Matrix — Loan Count",
    "M8": "DPD Transition Matrix — Count %",
    "M9": "Vintage Cohort Analysis",
}

# Keywords that signal which metric the user cares about
_METRIC_KEYWORDS: dict[str, list[str]] = {
    "M1": ["portfolio summary", "pos", "outstanding", "wair", "wart", "interest rate",
            "residual tenor", "active loan", "loan count", "m1"],
    "M2": ["dpd bucket", "dpd distribution", "par ", "gnpa", "npa", "delinquenc",
            "current bucket", "overdue", "m2"],
    "M3": ["collection efficiency", "ce ", "ce%", "emi due", "collected", "time series",
            "monthly ce", "quarterly", "m3"],
    "M4": ["ce by dpd", "ce by bucket", "bucket wise ce", "bucket-wise", "dpd ce",
            "collection efficiency by", "m4"],
    "M5": ["transition matrix", "dpd transition", "migration", "flow rate",
            "roll rate", "m5", "m6", "m7", "m8", "pos inr transition"],
    "M9": ["vintage", "cohort", "mob", "seasoning", "repay", "m9"],
}

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


# ═══════════════════════════════════════════════════════════════════════════
#  Layer 1 — Compact summary builders (always included, ~2-4K tokens)
# ═══════════════════════════════════════════════════════════════════════════

def _summary_dataset(state: dict) -> str:
    schema = state.get("schema") or {}
    file_keys = ["loan_file", "transaction_file", "borrower_file", "collateral_file", "collections_file"]
    detected = [k.replace("_file", "").replace("_", " ").title() for k in file_keys if schema.get(k)]
    computable = schema.get("computable_metrics", [])
    non_comp = schema.get("non_computable_metrics", {})
    lines = [
        "=== DATASET ===",
        f"Files detected: {', '.join(detected) if detected else 'Unknown'}",
        f"Fields mapped: {schema.get('fields_mapped', 0)}",
        f"Metrics computed: {', '.join(computable) if computable else 'N/A'}",
    ]
    if non_comp:
        lines.append(f"Metrics skipped: {', '.join(non_comp.keys())} (missing data)")
    return "\n".join(lines)


def _summary_quality(state: dict) -> str:
    val = state.get("validation") or {}
    lines = [
        "\n=== DATA QUALITY ===",
        f"Validation passed: {val.get('passed', False)}",
        f"Total loans: {val.get('total_loans', 0):,}",
        f"Total transactions: {val.get('total_transactions', 0):,}",
    ]
    errs = val.get("errors", [])
    warns = val.get("warnings", [])
    if errs:
        lines.append(f"Data errors: {len(errs)}")
    if warns:
        lines.append(f"Data warnings: {len(warns)}")
    return "\n".join(lines)


def _summary_m1(data: dict) -> str:
    """M1: Portfolio Summary — extract from overall + year range."""
    overall = data.get("overall") or data  # legacy flat or new nested
    years = data.get("years", [])
    lines = [
        f"  Total POS: {overall.get('total_pos_cr', 0):,.2f} Cr",
        f"  Active Loans: {overall.get('active_loan_count', 0):,}",
        f"  WAIR: {overall.get('wair_pct', 0):.4f}%",
        f"  WART: {overall.get('wart_months', 0):.2f} months",
    ]
    if overall.get("interest_outstanding_cr"):
        lines.append(f"  Interest Outstanding: {overall['interest_outstanding_cr']:,.2f} Cr")
    if years:
        lines.append(f"  Year range: {min(years)} – {max(years)} ({len(years)} years)")
    yearly = data.get("yearly_data", [])
    if yearly:
        first, last = yearly[0], yearly[-1]
        lines.append(f"  Year {first.get('year')}: POS {first.get('total_pos_cr', 0):,.2f} Cr, "
                      f"Loans {first.get('active_loan_count', 0):,}")
        lines.append(f"  Year {last.get('year')}: POS {last.get('total_pos_cr', 0):,.2f} Cr, "
                      f"Loans {last.get('active_loan_count', 0):,}")
    return "\n".join(lines)


def _summary_m2(data: dict) -> str:
    """M2: POS by DPD Bucket."""
    dist = data.get("distribution", [])
    total = data.get("total_active_pos_crores", 0)
    summary = data.get("summary", {})
    lines = []
    if dist:
        for row in dist:
            b = row.get("dpd_bucket", "")
            pos = row.get("pos_crores", 0)
            pct = row.get("percentage", 0)
            lines.append(f"  {b:<12}: {pos:>10,.2f} Cr  ({pct:.2f}%)")
    else:
        # Legacy flat dict
        vals = {k: v for k, v in data.items() if isinstance(v, (int, float))}
        total = sum(vals.values()) or 1
        for b in _BUCKETS:
            amt = data.get(b, 0)
            lines.append(f"  {b:<12}: {amt:>10,.2f} Cr  ({amt / total * 100:.2f}%)")
    if total:
        lines.insert(0, f"  Total Active POS: {total:,.2f} Cr")
    if summary:
        lines.append(f"  PAR 0+: {summary.get('par_0_plus_crores', 0):,.2f} Cr")
        lines.append(f"  PAR 90+ (GNPA): {summary.get('par_90_plus_crores', 0):,.2f} Cr")
    return "\n".join(lines)


def _summary_m3(data: dict) -> str:
    """M3: Collection Efficiency — overall + last 6 months + trend."""
    lines = []
    overall = data.get("overall_ce_pct") or data.get("overall_ce") or data.get("ce_pct")
    if overall is not None:
        lines.append(f"  Overall CE: {overall:.2f}%")
    total_due = data.get("total_emi_due") or data.get("total_scheduled")
    total_col = data.get("total_collected") or data.get("total_paid")
    if total_due:
        lines.append(f"  Total EMI Due: {total_due:,.2f} INR")
    if total_col:
        lines.append(f"  Total Collected: {total_col:,.2f} INR")
    ts = data.get("time_series") or data.get("monthly_ce") or []
    if ts:
        lines.append(f"  Data span: {len(ts)} months ({ts[0].get('month', '?')} to {ts[-1].get('month', '?')})")
        ce_vals = [(r.get("month", ""), r.get("ce_pct", 0)) for r in ts]
        min_m, min_v = min(ce_vals, key=lambda x: x[1])
        max_m, max_v = max(ce_vals, key=lambda x: x[1])
        avg_v = sum(v for _, v in ce_vals) / len(ce_vals)
        lines.append(f"  Lowest CE: {min_m} = {min_v:.2f}%")
        lines.append(f"  Highest CE: {max_m} = {max_v:.2f}%")
        lines.append(f"  Average CE: {avg_v:.2f}%")
        # Last 6 months only
        recent = ts[-6:]
        lines.append("  Recent months:")
        for r in recent:
            lines.append(f"    {r.get('month', '?')}: {r.get('ce_pct', 0):.2f}%")
    return "\n".join(lines)


def _summary_m4(data: dict) -> str:
    """M4: CE by DPD Bucket — latest month only."""
    latest = data.get("latest") or {}
    latest_month = data.get("latest_month", "?")
    months = data.get("months", [])
    lines = [f"  Latest month: {latest_month} (data spans {len(months)} months)"]
    if latest:
        for b in _BUCKETS:
            bdata = latest.get(b, {})
            if isinstance(bdata, dict):
                ce = bdata.get("ce_pct", 0)
                cnt = bdata.get("loan_count", 0)
                lines.append(f"  {b:<12}: CE = {ce:.2f}%  ({cnt:,} loans)")
            elif isinstance(bdata, (int, float)):
                lines.append(f"  {b:<12}: CE = {bdata:.2f}%")
    else:
        # Legacy flat
        for k, v in data.items():
            if isinstance(v, (int, float)):
                lines.append(f"  {k}: {v:.2f}%")
    return "\n".join(lines)


def _format_matrix_period(m6_period: dict, m7_period: dict | None = None) -> str:
    """Format a single period's 5x5 transition matrix as text table."""
    rows = []
    for fr in _BUCKETS:
        if fr not in m6_period:
            continue
        parts = [f"  From {fr}:"]
        for to in _BUCKETS:
            pct = m6_period.get(fr, {}).get(to, 0)
            cnt = int(m7_period.get(fr, {}).get(to, 0)) if m7_period else None
            if pct > 0.01:
                cnt_str = f" ({cnt:,} loans)" if cnt is not None else ""
                parts.append(f"    → {to}: {pct:.2f}%{cnt_str}")
        rows.append("\n".join(parts))
    return "\n".join(rows)


def _summary_m5(data: dict) -> str:
    """M5-M8: Transition matrices — latest period only."""
    periods = data.get("periods", [])
    latest = data.get("latest_period", "")
    m6_all = data.get("m6_pos_pct") or {}
    m7_all = data.get("m7_count") or {}
    m8_all = data.get("m8_count_pct") or {}

    lines = [f"  Data spans {len(periods)} monthly periods"]
    if latest:
        lines.append(f"  Latest period: {latest}")

    # Get latest period's data
    m6_latest = m6_all.get(latest, {})
    m7_latest = m7_all.get(latest, {})
    m8_latest = m8_all.get(latest, {})

    if m6_latest:
        lines.append(f"  DPD Transition (% of POS) for {latest}:")
        lines.append(_format_matrix_period(m6_latest, m7_latest))
        # Key stats
        cc_pos = m6_latest.get("Current", {}).get("Current", 0)
        cc_cnt = m8_latest.get("Current", {}).get("Current", 0)
        lines.append(f"  Current→Current: POS {cc_pos:.2f}%, Count {cc_cnt:.2f}%")
    elif isinstance(m6_all, dict) and not periods:
        # Legacy flat structure (single period, no periods key)
        lines.append("  DPD Transition (% of POS):")
        lines.append(_format_matrix_period(m6_all, m7_all))

    return "\n".join(lines)


def _summary_m9(data: dict) -> str:
    """M9: Vintage/Cohort — summary stats, not full MOB data."""
    if isinstance(data, dict):
        cohorts = data.get("cohorts", [])
        max_mob = data.get("max_mob", 0)
        vintage = data.get("vintage_data", [])
        lines = [f"  Cohorts: {len(cohorts)} ({cohorts[0]} to {cohorts[-1]})" if cohorts else "  Cohorts: N/A"]
        lines.append(f"  Max MOB (months on book): {max_mob}")
        # Summarise: for each cohort, get the latest (max mob) repay_pct
        if vintage:
            cohort_latest: dict[str, tuple[int, float]] = {}
            for row in vintage:
                c = row.get("cohort", "")
                mob = row.get("mob", 0)
                rp = row.get("repay_pct", 0)
                if c not in cohort_latest or mob > cohort_latest[c][0]:
                    cohort_latest[c] = (mob, rp)
            lines.append("  Latest repayment % by cohort (at max observed MOB):")
            for c in sorted(cohort_latest):
                mob, rp = cohort_latest[c]
                lines.append(f"    {c}: {rp:.2f}% at MOB {mob}")
    elif isinstance(data, list):
        lines = [f"  Vintage cohorts: {len(data)} entries"]
        lines.append(f"  [raw preview] {json.dumps(data[:2], default=str)[:200]}")
    else:
        lines = ["  No vintage data"]
    return "\n".join(lines)


_SUMMARY_BUILDERS = {
    "M1": _summary_m1,
    "M2": _summary_m2,
    "M3": _summary_m3,
    "M4": _summary_m4,
    "M5": _summary_m5,
    "M6": None,  # included in M5
    "M7": None,  # included in M5
    "M8": None,  # included in M5
    "M9": _summary_m9,
}


def _build_summary(state: dict) -> str:
    """Layer 1: Build compact summary of entire portfolio (~2-4K tokens)."""
    parts = [_summary_dataset(state), _summary_quality(state)]
    metrics = state.get("metrics") or {}

    for mid in ["M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8", "M9"]:
        m = metrics.get(mid) or {}
        if m.get("status") not in ("ok", "partial"):
            continue
        data = m.get("data") or {}
        builder = _SUMMARY_BUILDERS.get(mid)
        if builder is None:
            # M6/M7/M8 — skip, covered in M5
            continue
        name = _METRIC_NAMES.get(mid, mid)
        section = f"\n=== {mid}: {name} ===\n"
        try:
            section += builder(data)
        except Exception:
            section += f"  [raw] {json.dumps(data, default=str)[:200]}"
        insight = m.get("llm_insight", "")
        if insight:
            section += f"\n  AI Insight: {insight[:400]}"
        parts.append(section)

    return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════════════════
#  Layer 2 — Question-aware detail retrieval (on-demand)
# ═══════════════════════════════════════════════════════════════════════════

def _detect_relevant_metrics(question: str) -> set[str]:
    """Keyword-based detection of which metrics the question targets."""
    q = question.lower()
    hits: set[str] = set()
    for mid, keywords in _METRIC_KEYWORDS.items():
        for kw in keywords:
            if kw in q:
                hits.add(mid)
                break
    return hits


def _extract_periods_from_question(question: str) -> list[str]:
    """Extract YYYY-MM or YYYY or quarter patterns from the question."""
    patterns = re.findall(r'20\d{2}-(?:0[1-9]|1[0-2])', question)  # YYYY-MM
    patterns += re.findall(r'20\d{2}Q[1-4]', question, re.IGNORECASE)  # 2019Q1
    years = re.findall(r'\b(20\d{2})\b', question)
    return patterns + years


def _detail_m1(data: dict, question: str) -> str:
    """Full yearly breakdown for M1."""
    yearly = data.get("yearly_data", [])
    if not yearly:
        return ""
    lines = ["\n=== M1 DETAIL: Yearly Portfolio Summary ==="]
    for y in yearly:
        lines.append(
            f"  {y.get('year')}: POS {y.get('total_pos_cr', 0):,.2f} Cr, "
            f"Loans {y.get('active_loan_count', 0):,}, "
            f"WAIR {y.get('wair_pct', 0):.4f}%, "
            f"WART {y.get('wart_months', 0):.2f} mo, "
            f"Interest {y.get('interest_outstanding_cr', 0):,.2f} Cr"
        )
    return "\n".join(lines)


def _detail_m3(data: dict, question: str) -> str:
    """Monthly CE time series — filtered by mentioned periods or last 24 months."""
    ts = data.get("time_series") or []
    if not ts:
        return ""
    periods = _extract_periods_from_question(question)
    if periods:
        # Filter to matching year/months
        filtered = []
        for r in ts:
            m = r.get("month", "")
            if any(m.startswith(p) for p in periods):
                filtered.append(r)
        if not filtered:
            filtered = ts[-12:]  # fallback
    else:
        filtered = ts[-24:]  # default: last 24

    lines = [f"\n=== M3 DETAIL: Monthly CE ({len(filtered)} months) ==="]
    for r in filtered:
        lines.append(
            f"  {r.get('month', '?')}: CE {r.get('ce_pct', 0):.2f}%, "
            f"EMI Due {r.get('emi_due', 0):,.2f}, "
            f"Collected {r.get('collected', 0):,.2f}"
        )
    return "\n".join(lines)


def _detail_m4(data: dict, question: str) -> str:
    """CE by DPD bucket — for specific months or last 6."""
    by_month = data.get("by_month") or {}
    months = data.get("months") or sorted(by_month.keys())
    periods = _extract_periods_from_question(question)

    if periods:
        selected = [m for m in months if any(m.startswith(p) for p in periods)]
        if not selected:
            selected = months[-6:]
    else:
        selected = months[-6:]

    lines = [f"\n=== M4 DETAIL: CE by DPD Bucket ({len(selected)} months) ==="]
    for m in selected:
        mdata = by_month.get(m, {})
        row_parts = [f"  {m}:"]
        for b in _BUCKETS:
            bd = mdata.get(b, {})
            if isinstance(bd, dict):
                row_parts.append(f" {b}={bd.get('ce_pct', 0):.1f}%")
            elif isinstance(bd, (int, float)):
                row_parts.append(f" {b}={bd:.1f}%")
        lines.append(" ".join(row_parts))
    return "\n".join(lines)


def _detail_m5(data: dict, question: str) -> str:
    """Transition matrices for specific periods or last 3."""
    m6_all = data.get("m6_pos_pct") or {}
    m7_all = data.get("m7_count") or {}
    periods_list = data.get("periods") or sorted(m6_all.keys())
    periods = _extract_periods_from_question(question)

    if periods:
        selected = [p for p in periods_list if any(p.startswith(q) for q in periods)]
        if not selected:
            selected = periods_list[-3:]
    else:
        selected = periods_list[-3:]

    lines = [f"\n=== M5-M8 DETAIL: Transition Matrices ({len(selected)} periods) ==="]
    for p in selected:
        m6_p = m6_all.get(p, {})
        m7_p = m7_all.get(p, {})
        if m6_p:
            lines.append(f"\n  Period {p} (% of POS by bucket):")
            lines.append(_format_matrix_period(m6_p, m7_p))
    return "\n".join(lines)


def _detail_m9(data: dict, question: str) -> str:
    """Vintage data — for specific cohorts or all cohorts with MOB curve summary."""
    if not isinstance(data, dict):
        return ""
    vintage = data.get("vintage_data", [])
    cohorts_list = data.get("cohorts", [])
    if not vintage:
        return ""

    periods = _extract_periods_from_question(question)
    q_lower = question.lower()

    # Determine which cohorts to include
    if periods:
        target_cohorts = set()
        for c in cohorts_list:
            if any(c.startswith(p) or c.lower() == p.lower() for p in periods):
                target_cohorts.add(c)
        if not target_cohorts:
            target_cohorts = set(cohorts_list[-5:])
    elif "all" in q_lower or "every" in q_lower:
        target_cohorts = set(cohorts_list)
    else:
        target_cohorts = set(cohorts_list[-8:])  # default: last 8

    # Filter vintage data
    filtered = [r for r in vintage if r.get("cohort") in target_cohorts]
    lines = [f"\n=== M9 DETAIL: Vintage MOB Curves ({len(target_cohorts)} cohorts) ==="]
    current_cohort = None
    for r in sorted(filtered, key=lambda x: (x.get("cohort", ""), x.get("mob", 0))):
        c = r.get("cohort", "")
        if c != current_cohort:
            current_cohort = c
            lines.append(f"  Cohort {c}:")
        lines.append(f"    MOB {r.get('mob', 0):>3}: {r.get('repay_pct', 0):.2f}%")

    return "\n".join(lines)


_DETAIL_BUILDERS: dict[str, callable] = {
    "M1": _detail_m1,
    "M3": _detail_m3,
    "M4": _detail_m4,
    "M5": _detail_m5,
    "M9": _detail_m9,
}


def _build_detail(state: dict, question: str) -> str:
    """Layer 2: Build question-specific detail context."""
    metrics = state.get("metrics") or {}
    relevant = _detect_relevant_metrics(question)

    # If no specific metric detected, skip detail (summary is enough)
    if not relevant:
        return ""

    parts: list[str] = []
    for mid in sorted(relevant):
        # M6/M7/M8 → use M5's data
        lookup_mid = "M5" if mid in ("M6", "M7", "M8") else mid
        m = metrics.get(lookup_mid) or {}
        if m.get("status") not in ("ok", "partial"):
            continue
        data = m.get("data") or {}
        builder = _DETAIL_BUILDERS.get(lookup_mid)
        if builder:
            try:
                detail = builder(data, question)
                if detail:
                    parts.append(detail)
            except Exception:
                pass
    return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════════════════
#  Public API
# ═══════════════════════════════════════════════════════════════════════════

def _build_context(state: dict, question: str = "") -> str:
    """Build the two-layer context string for the LLM.

    Layer 1: Always-included compact summary (~2-4K tokens).
    Layer 2: Question-aware detailed data slices (only if relevant).
    """
    summary = _build_summary(state)
    detail = _build_detail(state, question) if question else ""

    if detail:
        return summary + "\n\n─── DETAILED DATA (for your question) ───" + detail
    return summary


def answer_question(
    session_state: dict,
    question: str,
    history: list[dict] | None = None,
) -> str:
    """Answer a user question about the portfolio using the pipeline state.

    Args:
        session_state: The full pipeline result dict (schema, metrics, validation).
        question:      User's natural-language question.
        history:       Previous chat turns [{"role": "user"/"assistant", "content": "..."}].

    Returns:
        Answer string from the LLM.
    """
    from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

    llm = get_llm(temperature=0.1)
    context = _build_context(session_state, question)

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
