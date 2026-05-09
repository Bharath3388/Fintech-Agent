"""
Chart Generator — Produces PNG charts from metric result data
==============================================================
Matches the visual style from the Parse.ai case study document:
  M1  → Portfolio Summary KPI table
  M2  → Horizontal bar chart: POS by DPD Bucket
  M3  → Line chart: Collections Efficiency time series
  M4  → Grouped bar chart: CE% by DPD Bucket
  M5  → Heatmap: POS Transition Matrix (INR)
  M6  → Heatmap: POS Transition Matrix (%)
  M7  → Heatmap: Loan Count Transition Matrix
  M8  → Heatmap: Loan Count Transition Matrix (%)
  M9  → Multi-line chart: Vintage Cohort Repayment Curves
  B1  → Bar charts: Borrower Demographics
  B2  → Histogram + bars: Credit Profile
  B3  → Heatmap / bars: Risk Segmentation
"""

from __future__ import annotations
import os
import io
import base64
import json
import numpy as np
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

# ── Dark theme matching the document ──────────────────────────────────────
DARK_BG = "#1a1a2e"
DARK_FACE = "#16213e"
GRID_COLOR = "#2a2a4a"
TEXT_COLOR = "#e0e0e0"
ACCENT_GREEN = "#4ade80"
ACCENT_RED = "#ef4444"
ACCENT_ORANGE = "#f59e0b"
ACCENT_BLUE = "#3b82f6"
BUCKET_COLORS = ["#4ade80", "#facc15", "#f59e0b", "#f97316", "#ef4444"]

plt.rcParams.update({
    "figure.facecolor": DARK_BG,
    "axes.facecolor": DARK_FACE,
    "axes.edgecolor": GRID_COLOR,
    "axes.labelcolor": TEXT_COLOR,
    "xtick.color": TEXT_COLOR,
    "ytick.color": TEXT_COLOR,
    "text.color": TEXT_COLOR,
    "grid.color": GRID_COLOR,
    "grid.alpha": 0.3,
    "font.size": 11,
})


def _to_base64(fig) -> str:
    """Convert matplotlib figure to base64 PNG string."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


def _save_and_encode(fig, output_dir: str | None, filename: str) -> dict:
    """Save figure to file and return base64 + path."""
    b64 = _to_base64(fig)
    path = None
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        path = os.path.join(output_dir, filename)
        with open(path, "wb") as f:
            f.write(base64.b64decode(b64))
    return {"base64": b64, "filename": filename, "path": path}


# ═══════════════════════════════════════════════════════════════════════════
#  M1 — Portfolio Summary Table
# ═══════════════════════════════════════════════════════════════════════════
def chart_m1(data: dict, output_dir: str | None = None) -> dict:
    if not data or "error" in data:
        return {}
    fig, ax = plt.subplots(figsize=(8, 0.6))  # will be resized below
    ax.axis("off")

    # Known pretty labels (order preserved); any extra keys get auto-labeled
    KNOWN_LABELS = {
        "total_pos_cr": "Total POS (₹ Cr)",
        "total_pos": "Total POS (₹ Cr)",
        "interest_outstanding_cr": "Interest Outstanding (₹ Cr)",
        "interest_outstanding": "Interest Outstanding (₹ Cr)",
        "active_count": "Active Loan Count",
        "active_loan_count": "Active Loan Count",
        "total_active_loans": "Active Loan Count",
        "wtd_avg_rate": "Wtd. Avg. Interest Rate (%)",
        "weighted_avg_interest_rate": "Wtd. Avg. Interest Rate (%)",
        "weighted_average_interest_rate": "Wtd. Avg. Interest Rate (%)",
        "wtd_avg_tenor": "Wtd. Avg. Residual Tenor (months)",
        "weighted_avg_residual_tenor": "Wtd. Avg. Residual Tenor (months)",
        "weighted_average_residual_tenor": "Wtd. Avg. Residual Tenor (months)",
    }
    SKIP_KEYS = {"error", "reason", "metric_id", "name", "status"}

    rows = []
    for key, val in data.items():
        if key in SKIP_KEYS or val is None:
            continue
        label = KNOWN_LABELS.get(key, key.replace("_", " ").title())
        if isinstance(val, float):
            rows.append([label, f"{val:,.2f}"])
        elif isinstance(val, int):
            rows.append([label, f"{val:,}"])
        else:
            rows.append([label, str(val)])

    if not rows:
        return {}

    # Dynamically size the figure height based on row count
    fig_h = max(2.5, 0.6 * len(rows) + 1.5)
    fig.set_size_inches(8, fig_h)

    table = ax.table(cellText=rows, colLabels=["KPI", "Value"],
                     loc="center", cellLoc="left")
    table.auto_set_font_size(False)
    table.set_fontsize(12)
    table.scale(1.2, 1.8)

    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor(GRID_COLOR)
        if row == 0:
            cell.set_facecolor("#2563eb")
            cell.set_text_props(color="white", fontweight="bold")
        else:
            cell.set_facecolor(DARK_FACE)
            cell.set_text_props(color=TEXT_COLOR)

    fig.suptitle("Portfolio Summary", fontsize=16, fontweight="bold", y=0.98)
    return _save_and_encode(fig, output_dir, "m1_portfolio_summary.png")


# ═══════════════════════════════════════════════════════════════════════════
#  M2 — POS by DPD Bucket (Horizontal Bar Chart)
# ═══════════════════════════════════════════════════════════════════════════
def chart_m2(data: dict, output_dir: str | None = None) -> dict:
    if not data or "error" in data:
        return {}
    fig, ax = plt.subplots(figsize=(12, 5))

    buckets = data.get("buckets", [])
    pos_values = data.get("pos_cr", data.get("pos_inr", []))
    pct_values = data.get("pct", [])

    # Handle list-of-dicts format: {"distribution": [{dpd_bucket, pos_amount_crores, ...}, ...]}
    dist_list = data.get("distribution", data.get("dpd_distribution", []))
    if not buckets and isinstance(dist_list, list) and dist_list:
        buckets = [d.get("dpd_bucket", d.get("bucket", d.get("dpd", ""))) for d in dist_list]
        pos_values = [
            d.get("pos_amount_crores", d.get("pos_cr", d.get("pos_inr",
                d.get("current_outstanding_principal_INR", d.get("outstanding", 0)))))
            for d in dist_list
        ]
        pct_values = [
            d.get("pos_percentage", d.get("pct", d.get("percentage", 0)))
            for d in dist_list
        ]

    # Last resort: dict keys as buckets (only scalar values)
    if not buckets and isinstance(data, dict):
        scalar_items = [(k, v) for k, v in data.items()
                        if isinstance(v, (int, float)) and k not in ("total_pos_crores", "total_pos")]
        if scalar_items:
            buckets = [k for k, _ in scalar_items]
            pos_values = [v for _, v in scalar_items]

    if not buckets:
        plt.close(fig)
        return {}

    # Ensure buckets are strings
    buckets = [str(b) for b in buckets]
    colors = BUCKET_COLORS[:len(buckets)]
    bars = ax.barh(buckets, pos_values, color=colors, height=0.6)

    ax.set_xlabel("Outstanding Balance", fontsize=12)
    ax.set_title("DPD Bucket Distribution (POS)", fontsize=16, fontweight="bold")
    ax.invert_yaxis()
    ax.tick_params(axis="y", labelsize=12)
    ax.grid(axis="x", alpha=0.2)

    # Human-readable x-axis (Cr / Lakhs / raw)
    max_val = max(pos_values) if pos_values else 0
    if max_val >= 1e7:
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"₹{x / 1e7:,.0f} Cr"))
    elif max_val >= 1e5:
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"₹{x / 1e5:,.0f} L"))
    else:
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"₹{x:,.0f}"))

    for i, (bar, val) in enumerate(zip(bars, pos_values)):
        pct = pct_values[i] if i < len(pct_values) else None
        if pct is not None and pct != "":
            label = f"{float(pct):.2f}%"
        elif isinstance(val, (int, float)):
            label = f"{val:,.0f}"
        else:
            label = str(val)
        ax.text(bar.get_width() + max_val * 0.01, bar.get_y() + bar.get_height() / 2,
                label, va="center", fontsize=10, color=TEXT_COLOR)

    fig.tight_layout()
    return _save_and_encode(fig, output_dir, "m2_pos_by_dpd.png")


# ═══════════════════════════════════════════════════════════════════════════
#  M3 — Collections Efficiency Time Series (Line Chart)
# ═══════════════════════════════════════════════════════════════════════════
def chart_m3(data: dict, output_dir: str | None = None) -> dict:
    if not data or "error" in data:
        return {}
    fig, ax = plt.subplots(figsize=(14, 5))

    ts = data.get("time_series", [])
    if not ts:
        plt.close(fig)
        return {}

    months = [t.get("month", t.get("period", "")) for t in ts]
    ce_pct = [t.get("ce_pct", t.get("CE%", 0)) for t in ts]

    ax.plot(months, ce_pct, color=ACCENT_GREEN, marker="o", linewidth=2, markersize=4)
    ax.fill_between(range(len(months)), ce_pct, alpha=0.15, color=ACCENT_GREEN)

    ax.axhline(y=100, color=ACCENT_ORANGE, linestyle="--", linewidth=1, alpha=0.5, label="100% target")

    ax.set_xlabel("Month", fontsize=12)
    ax.set_ylabel("Collections Efficiency %", fontsize=12)
    ax.set_title("Overall Collections Efficiency — Time Series", fontsize=16, fontweight="bold")
    ax.legend(loc="lower right")
    ax.grid(True, alpha=0.2)

    if len(months) > 12:
        ax.set_xticks(range(0, len(months), max(1, len(months) // 12)))
    plt.xticks(rotation=45, ha="right")

    fig.tight_layout()
    return _save_and_encode(fig, output_dir, "m3_ce_time_series.png")


# ═══════════════════════════════════════════════════════════════════════════
#  M4 — CE% by DPD Bucket (Grouped Bar Chart)
# ═══════════════════════════════════════════════════════════════════════════
def chart_m4(data: dict, output_dir: str | None = None) -> dict:
    if not data or "error" in data:
        return {}
    fig, ax = plt.subplots(figsize=(10, 5))

    buckets = data.get("buckets", [])
    ce_pct = data.get("ce_pct", [])

    # Handle list-of-dicts format: {"summary": [{dpd_bucket, ce_percentage, ...}]}
    summary = data.get("summary", data.get("dpd_summary", []))
    if not buckets and isinstance(summary, list) and summary:
        buckets = [s.get("dpd_bucket", s.get("bucket", "")) for s in summary]
        ce_pct = [s.get("ce_percentage", s.get("ce_pct", s.get("CE%", 0))) for s in summary]

    if not buckets:
        plt.close(fig)
        return {}

    colors = BUCKET_COLORS[:len(buckets)]
    bars = ax.bar(buckets, ce_pct, color=colors, width=0.5)

    for bar, val in zip(bars, ce_pct):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                f"{val:.1f}%", ha="center", va="bottom", fontsize=10, color=TEXT_COLOR)

    ax.set_xlabel("DPD Bucket", fontsize=12)
    ax.set_ylabel("Collections Efficiency %", fontsize=12)
    ax.set_title("Collections Efficiency by DPD Bucket", fontsize=16, fontweight="bold")
    ax.axhline(y=100, color=ACCENT_ORANGE, linestyle="--", linewidth=1, alpha=0.5)
    ax.grid(axis="y", alpha=0.2)

    fig.tight_layout()
    return _save_and_encode(fig, output_dir, "m4_ce_by_dpd.png")


# ═══════════════════════════════════════════════════════════════════════════
#  M5-M8 — Transition Matrix Heatmaps
# ═══════════════════════════════════════════════════════════════════════════
def _chart_transition_heatmap(matrix_data: dict, title: str, fmt: str,
                               filename: str, output_dir: str | None) -> dict:
    """Generic heatmap for transition matrices."""
    if not matrix_data or "error" in matrix_data:
        return {}

    bucket_order = ["Current", "DPD 1-30", "DPD 31-60", "DPD 61-90", "DPD 90+", "Paid Off"]

    # Build the matrix array
    rows_present = []
    cols_present = []
    for from_b in bucket_order:
        if from_b in matrix_data:
            rows_present.append(from_b)
            for to_b in bucket_order:
                if to_b in matrix_data[from_b] and to_b not in cols_present:
                    cols_present.append(to_b)

    if not rows_present:
        # Maybe the data is flat — try parsing as generic dict of dicts
        rows_present = list(matrix_data.keys())
        if rows_present:
            cols_present = list(matrix_data[rows_present[0]].keys()) if isinstance(matrix_data[rows_present[0]], dict) else []

    if not rows_present or not cols_present:
        return {}

    n_rows = len(rows_present)
    n_cols = len(cols_present)
    arr = np.zeros((n_rows, n_cols))
    annot = []

    for i, from_b in enumerate(rows_present):
        row_annot = []
        for j, to_b in enumerate(cols_present):
            val = 0
            if isinstance(matrix_data.get(from_b), dict):
                val = matrix_data[from_b].get(to_b, 0)
            try:
                val = float(val)
            except (TypeError, ValueError):
                val = 0
            arr[i, j] = val
            if fmt == "pct":
                row_annot.append(f"{val:.1f}%")
            elif fmt == "count":
                row_annot.append(f"{int(val):,}")
            else:
                if val >= 1e9:
                    row_annot.append(f"{val / 1e9:.2f}B")
                elif val >= 1e7:
                    row_annot.append(f"{val / 1e7:.2f}Cr")
                elif val >= 1e6:
                    row_annot.append(f"{val / 1e6:.1f}M")
                else:
                    row_annot.append(f"{val:,.0f}")
        annot.append(row_annot)

    fig, ax = plt.subplots(figsize=(12, 7))

    cmap = plt.cm.Reds if fmt != "pct" else plt.cm.RdYlGn_r
    im = ax.imshow(arr, cmap=cmap, aspect="auto")
    plt.colorbar(im, ax=ax, shrink=0.8)

    ax.set_xticks(range(n_cols))
    ax.set_xticklabels(cols_present, fontsize=10)
    ax.set_yticks(range(n_rows))
    ax.set_yticklabels(rows_present, fontsize=10)
    ax.set_xlabel("To Bucket", fontsize=12)
    ax.set_ylabel("From Bucket", fontsize=12)
    ax.set_title(title, fontsize=16, fontweight="bold")

    for i in range(n_rows):
        for j in range(n_cols):
            text_color = "white" if arr[i, j] > arr.max() * 0.5 else TEXT_COLOR
            ax.text(j, i, annot[i][j], ha="center", va="center",
                    fontsize=9, color=text_color)

    fig.tight_layout()
    return _save_and_encode(fig, output_dir, filename)


def chart_m5(data: dict, output_dir: str | None = None) -> dict:
    matrix = data.get("m5_pos_inr", data)
    return _chart_transition_heatmap(matrix, "POS (Balance) Transition — Absolute", "inr",
                                      "m5_pos_transition_inr.png", output_dir)


def chart_m6(data: dict, output_dir: str | None = None) -> dict:
    matrix = data.get("m6_pos_pct", data)
    return _chart_transition_heatmap(matrix, "POS (Balance) Transition — %", "pct",
                                      "m6_pos_transition_pct.png", output_dir)


def chart_m7(data: dict, output_dir: str | None = None) -> dict:
    matrix = data.get("m7_count", data)
    return _chart_transition_heatmap(matrix, "Loan Count Transition — Absolute", "count",
                                      "m7_count_transition.png", output_dir)


def chart_m8(data: dict, output_dir: str | None = None) -> dict:
    matrix = data.get("m8_count_pct", data)
    return _chart_transition_heatmap(matrix, "Loan Count Transition — %", "pct",
                                      "m8_count_transition_pct.png", output_dir)


# ═══════════════════════════════════════════════════════════════════════════
#  M9 — Vintage Cohort Repayment Curves (Multi-Line)
# ═══════════════════════════════════════════════════════════════════════════
def chart_m9(data: dict, output_dir: str | None = None) -> dict:
    if not data or "error" in data:
        return {}
    fig, ax = plt.subplots(figsize=(14, 6))

    vintage = data.get("vintage_data", [])
    cohorts_list = data.get("cohorts", [])

    if not vintage:
        plt.close(fig)
        return {}

    # Group by cohort
    from collections import defaultdict
    cohort_data = defaultdict(lambda: {"mob": [], "pct": []})
    for item in vintage:
        c = item.get("cohort", "")
        cohort_data[c]["mob"].append(item.get("mob", 0))
        cohort_data[c]["pct"].append(item.get("repay_pct", 0))

    colors = plt.cm.viridis(np.linspace(0.2, 0.9, len(cohort_data)))

    for (cohort, cdata), color in zip(sorted(cohort_data.items()), colors):
        sorted_pairs = sorted(zip(cdata["mob"], cdata["pct"]))
        mobs = [p[0] for p in sorted_pairs]
        pcts = [p[1] for p in sorted_pairs]
        ax.plot(mobs, pcts, marker="o", markersize=3, linewidth=1.5,
                color=color, label=cohort)

    ax.set_xlabel("Months on Book (MOB)", fontsize=12)
    ax.set_ylabel("Cumul. Principal Repaid %", fontsize=12)
    ax.set_title("Vintage Curves — Cumulative Principal Repayment", fontsize=16, fontweight="bold")
    ax.legend(loc="upper left", fontsize=8, ncol=2)
    ax.grid(True, alpha=0.2)

    fig.tight_layout()
    return _save_and_encode(fig, output_dir, "m9_vintage_cohort.png")


# ═══════════════════════════════════════════════════════════════════════════
#  B1 — Borrower Demographics
# ═══════════════════════════════════════════════════════════════════════════
def _extract_numeric(d: dict) -> dict:
    """Flatten {key: {count: N, ...}} → {key: N} and skip non-numeric leaves."""
    out = {}
    for k, v in d.items():
        if isinstance(v, (int, float)):
            out[k] = v
        elif isinstance(v, dict):
            out[k] = v.get("count", v.get("value", v.get("percentage", 0)))
    return out


def chart_b1(data: dict, output_dir: str | None = None) -> dict:
    if not data or "error" in data:
        return {}
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    # Gender distribution
    ax = axes[0, 0]
    gender = _extract_numeric(data.get("gender_distribution", {}))
    if gender:
        labels = list(gender.keys())
        vals = list(gender.values())
        ax.pie(vals, labels=labels, autopct="%1.1f%%",
               colors=[ACCENT_BLUE, "#ec4899", ACCENT_ORANGE], textprops={"color": TEXT_COLOR})
        ax.set_title("Gender Distribution", fontweight="bold")

    # Employment type
    ax = axes[0, 1]
    emp = _extract_numeric(data.get("employment_type_distribution", data.get("employment_distribution", {})))
    if emp:
        labels = list(emp.keys())[:8]
        vals = list(emp.values())[:8]
        ax.barh(labels, vals, color=ACCENT_BLUE)
        ax.set_title("Employment Type", fontweight="bold")
        ax.invert_yaxis()

    # Top states
    ax = axes[1, 0]
    states = data.get("top_states", data.get("top_10_states", {}))
    if states:
        if isinstance(states, list):
            labels = [s.get("state", "") for s in states[:10]]
            vals = [s.get("count", 0) for s in states[:10]]
        else:
            states = _extract_numeric(states)
            labels = list(states.keys())[:10]
            vals = list(states.values())[:10]
        ax.barh(labels, vals, color=ACCENT_GREEN)
        ax.set_title("Top 10 States", fontweight="bold")
        ax.invert_yaxis()

    # Borrower type
    ax = axes[1, 1]
    btype = _extract_numeric(data.get("borrower_type_distribution", data.get("borrower_type", {})))
    if btype:
        labels = list(btype.keys())
        vals = list(btype.values())
        ax.pie(vals, labels=labels, autopct="%1.1f%%",
               colors=[ACCENT_BLUE, ACCENT_GREEN, ACCENT_ORANGE], textprops={"color": TEXT_COLOR})
        ax.set_title("Borrower Type", fontweight="bold")

    fig.suptitle("Borrower Demographics Summary", fontsize=16, fontweight="bold", y=1.02)
    fig.tight_layout()
    return _save_and_encode(fig, output_dir, "b1_demographics.png")


# ═══════════════════════════════════════════════════════════════════════════
#  B2 — Credit Profile
# ═══════════════════════════════════════════════════════════════════════════
def chart_b2(data: dict, output_dir: str | None = None) -> dict:
    if not data or "error" in data:
        return {}
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))

    # CIBIL score buckets
    ax = axes[0]
    cibil = _extract_numeric(data.get("cibil_score_distribution", data.get("cibil_buckets", {})))
    if cibil:
        labels = list(cibil.keys())
        vals = list(cibil.values())
        ax.bar(labels, vals, color=ACCENT_BLUE)
        ax.set_title("CIBIL Score Distribution", fontweight="bold")
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha="right")

    # Risk category
    ax = axes[1]
    risk = _extract_numeric(data.get("risk_category_distribution", data.get("risk_distribution", {})))
    if risk:
        labels = list(risk.keys())
        vals = list(risk.values())
        colors = [ACCENT_GREEN if "low" in l.lower() else ACCENT_ORANGE if "med" in l.lower() else ACCENT_RED for l in labels]
        ax.bar(labels, vals, color=colors)
        ax.set_title("Risk Category", fontweight="bold")

    # Customer segment
    ax = axes[2]
    seg = _extract_numeric(data.get("customer_segment_distribution", data.get("segment_distribution", {})))
    if seg:
        labels = list(seg.keys())
        vals = list(seg.values())
        ax.bar(labels, vals, color=ACCENT_GREEN)
        ax.set_title("Customer Segment", fontweight="bold")

    fig.suptitle("Credit Profile Analysis", fontsize=16, fontweight="bold", y=1.02)
    fig.tight_layout()
    return _save_and_encode(fig, output_dir, "b2_credit_profile.png")


# ═══════════════════════════════════════════════════════════════════════════
#  B3 — Risk Segmentation
# ═══════════════════════════════════════════════════════════════════════════
def chart_b3(data: dict, output_dir: str | None = None) -> dict:
    if not data or "error" in data:
        return {}
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Avg CIBIL by risk
    ax = axes[0]
    avg_cibil = _extract_numeric(data.get("avg_cibil_by_risk", {}))
    if avg_cibil:
        labels = list(avg_cibil.keys())
        vals = list(avg_cibil.values())
        colors = [ACCENT_GREEN if "low" in l.lower() else ACCENT_ORANGE if "med" in l.lower() else ACCENT_RED for l in labels]
        ax.bar(labels, vals, color=colors)
        ax.set_title("Avg. CIBIL Score by Risk Category", fontweight="bold")
        ax.set_ylabel("CIBIL Score")

    # DPD history
    ax = axes[1]
    dpd_hist = _extract_numeric(data.get("dpd_history_distribution", data.get("highest_dpd_distribution", {})))
    if dpd_hist:
        labels = list(dpd_hist.keys())
        vals = list(dpd_hist.values())
        ax.bar(labels, vals, color=ACCENT_BLUE)
        ax.set_title("Highest DPD (Last 24 Months)", fontweight="bold")
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha="right")

    fig.suptitle("Risk Segmentation Analysis", fontsize=16, fontweight="bold", y=1.02)
    fig.tight_layout()
    return _save_and_encode(fig, output_dir, "b3_risk_segmentation.png")


# ═══════════════════════════════════════════════════════════════════════════
#  Router — generate all applicable charts
# ═══════════════════════════════════════════════════════════════════════════
CHART_GENERATORS = {
    "M1": chart_m1,
    "M2": chart_m2,
    "M3": chart_m3,
    "M4": chart_m4,
    "M5": chart_m5,
    "M6": chart_m6,
    "M7": chart_m7,
    "M8": chart_m8,
    "M9": chart_m9,
    "B1": chart_b1,
    "B2": chart_b2,
    "B3": chart_b3,
}


def generate_charts(metrics: dict, output_dir: str | None = None) -> dict[str, dict]:
    """Generate charts for all successfully computed metrics.

    Args:
        metrics: dict of metric_id → MetricResultItem
        output_dir: optional directory to save PNG files

    Returns:
        dict of metric_id → {base64, filename, path}
    """
    charts = {}
    for mid, m in metrics.items():
        if m.get("status") != "ok":
            continue
        data = m.get("data")
        if not data or (isinstance(data, dict) and "error" in data):
            continue
        gen = CHART_GENERATORS.get(mid)
        if gen:
            try:
                result = gen(data, output_dir)
                if result:
                    charts[mid] = result
            except Exception as e:
                charts[mid] = {"error": str(e)}
    return charts
