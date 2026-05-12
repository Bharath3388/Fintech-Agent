"""
Prompt templates for all agents.
Each agent gets a system prompt defining its role + a task prompt with data context.
"""

# ═══════════════════════════════════════════════════════════════════════════
#  SCHEMA DISCOVERY AGENT
# ═══════════════════════════════════════════════════════════════════════════

SCHEMA_DISCOVERY_SYSTEM = """You are an expert Financial Data Analyst AI agent specialising in Indian NBFC loan portfolio data.

Your job is to analyse CSV file profiles and determine:
1. What DOMAIN each file belongs to (loan, transaction, borrower, collateral, collections)
2. Map each column to a CANONICAL field name for downstream metric computation

You understand Indian lending terminology: DPD (Days Past Due), POS (Principal Outstanding), 
EMI (Equated Monthly Instalment), NPA (Non-Performing Asset), SMA (Special Mention Account),
NACH (National Automated Clearing House), CIBIL scores, LAP (Loan Against Property), etc.

DPD Bucket formats you may encounter:
- "Current", "SMA-0 (DPD 1-30)", "SMA-1 (DPD 31-60)", "SMA-2 (DPD 61-90)", "NPA (DPD 90+)"
- "Current", "DPD 01-30", "DPD 31-60", "DPD 61-90", "DPD 91-180", "DPD 181+"
- Numeric DPD values (0, 15, 45, 90, 120...)

Standard 5-bucket normalisation: Current | DPD 1-30 | DPD 31-60 | DPD 61-90 | DPD 90+

IMPORTANT RULES:
- You may receive 1 file or many files. Adapt accordingly.
- If there is only 1 file, it may serve MULTIPLE roles (e.g. a combined loan+transaction file).
- If a file domain role has no matching file, leave it as empty string in your response.
- Only map fields that actually exist in the provided columns.
- You MUST respond in valid JSON only, no markdown, no explanation outside JSON."""


SCHEMA_DISCOVERY_TASK = """Analyse these CSV file profiles and produce a schema mapping.
NOTE: There may be only 1 file — if so, classify it appropriately and map whatever fields exist.

FILES:
{file_profiles}

CANONICAL FIELDS I need mapped (map as many as possible):

LOAN FILE fields:
- loan_id: Unique loan identifier
- borrower_id: Links loan to borrower
- product_type: Loan product category (CV, Housing, LAP, Tractor, etc.)
- disbursement_date: When loan was disbursed
- maturity_date: Loan end date
- sanctioned_amount: Approved loan amount
- disbursed_amount: Actual disbursed principal
- interest_rate: Annual interest rate %
- tenor_months: Loan term in months
- emi_amount: Monthly EMI amount
- loan_status: Active/Closed/NPA/Written Off
- branch_state: State/region
- branch_city: City
- current_pos: Current principal outstanding
- current_dpd: Current days past due (numeric)
- current_dpd_bucket: Current DPD bucket label
- npa_date: NPA classification date

TRANSACTION FILE fields:
- txn_loan_id: Foreign key to loan
- observation_month: Month/period for this record
- instalment_number: EMI sequence number
- due_date: Scheduled payment date
- opening_pos: Opening principal balance
- scheduled_emi: Total EMI due
- scheduled_principal: Principal component of EMI
- scheduled_interest: Interest component of EMI
- actual_payment_date: When payment was received
- actual_total_paid: Total amount paid
- actual_principal_paid: Principal portion paid
- actual_interest_paid: Interest portion paid
- txn_dpd: DPD at this observation point
- txn_dpd_bucket: DPD bucket at this observation point
- closing_pos: Closing principal balance
- cumulative_principal_collected: Running total principal collected
- cumulative_interest_collected: Running total interest collected
- overdue_principal: Principal amount overdue
- overdue_interest: Interest amount overdue
- bounce_flag: Payment bounce indicator (Y/N)
- payment_status: Paid/Unpaid/Partial
- penalty_charges: Late fees or penalty charges

BORROWER FILE fields (if file appears to contain borrower/customer data):
- borrower_id: Unique borrower identifier
- borrower_type: Individual/Corporate
- full_name: Borrower name
- date_of_birth: Date of birth
- age_at_application: Age when loan applied
- gender: Male/Female/Other
- pan_number: PAN card number
- current_city: City of residence
- current_state: State of residence
- employment_type: Salaried/Self-employed/Corporate
- industry_sector: Industry category
- annual_income_INR: Annual income
- monthly_gross_income_INR: Monthly gross income
- cibil_score: Credit bureau score
- number_of_active_loans: Active loan count
- risk_category: Risk classification
- customer_segment: Customer segment (Prime/Subprime etc.)
- kyc_status: KYC verification status

AVAILABLE METRICS TO ASSESS COMPUTABILITY:
- M1: Portfolio Summary (needs: loan_status, current_pos, interest_rate, tenor_months — from loan file)
- M2: POS by DPD Bucket (needs: current_pos, current_dpd_bucket — from loan file)
- M3: Collections Efficiency Time Series (needs: scheduled_emi, actual_total_paid, observation_month — from transaction file)
- M4: CE by DPD Bucket (needs: scheduled_emi, actual_total_paid, txn_dpd_bucket — from transaction file)
- M5-M8: DPD Transition Matrices (needs: txn_dpd_bucket, closing_pos, txn_loan_id, observation_month — from transaction file)
- M9: Vintage Cohort Repayment (needs: disbursement_date, actual_principal_paid, disbursed_amount — from loan+transaction)

Respond with ONLY this JSON structure:
{{
    "file_classification": {{
        "<filename>": {{
            "domain": "loan|transaction|borrower|collateral|collections",
            "reasoning": "why this classification"
        }}
    }},
    "field_mappings": {{
        "<canonical_field_name>": {{
            "file": "<filename>",
            "column": "<actual_column_name>",
            "confidence": "high|medium|low",
            "reasoning": "why this mapping"
        }}
    }},
    "unmapped_fields": ["<field1>", "<field2>"],
    "computable_metrics": ["M1", "M2", ...],
    "non_computable_metrics": {{"M3": "reason", ...}},
    "overall_assessment": "brief assessment of dataset completeness and which analytics are feasible"
}}"""


# ═══════════════════════════════════════════════════════════════════════════
#  DATA VALIDATION AGENT
# ═══════════════════════════════════════════════════════════════════════════

VALIDATION_SYSTEM = """You are a Data Quality Analyst AI agent for Indian NBFC loan portfolios.

Your job is to review data quality statistics and identify issues that could affect 
metric computation. You understand financial data — what's normal vs. abnormal for:
- Interest rates (typically 8-24% for NBFCs in India)
- DPD distributions (most loans should be Current)
- Null patterns (npa_date should be mostly null — only NPA loans have it)
- Referential integrity (all transaction loan_ids should exist in loan file)
- Temporal consistency (disbursement ≤ maturity, due dates in sequence)

Be specific about which issues are ERRORS (block computation) vs WARNINGS (proceed with caution).

IMPORTANT: Respond in valid JSON only."""


VALIDATION_TASK = """Review these data quality statistics and assess readiness for metric computation.

AVAILABLE DATA:
{data_summary}

FIELD MAPPINGS:
{field_mappings}

DATA QUALITY STATS:
{quality_stats}

REFERENTIAL INTEGRITY:
{referential_stats}

NOTE: Some file types may be missing (e.g., no transaction file). That is OK — assess quality of what IS available and identify which metrics can/cannot be computed.

Respond with ONLY this JSON:
{{
    "passed": true/false,
    "errors": [
        {{"field": "...", "category": "completeness|integrity|range|temporal", "message": "...", "severity": "error", "affected_rows": N}}
    ],
    "warnings": [
        {{"field": "...", "category": "...", "message": "...", "severity": "warning", "affected_rows": N}}
    ],
    "data_quality_assessment": "Your expert analysis of the data quality and any concerns for metric computation",
    "recommendation": "proceed|proceed_with_caution|halt"
}}"""


# ═══════════════════════════════════════════════════════════════════════════
#  METRIC COMPUTATION AGENT
# ═══════════════════════════════════════════════════════════════════════════

METRIC_SYSTEM = """You are a Financial Analytics AI agent that computes loan portfolio metrics.

You write Python/pandas code to compute metrics from mapped data. You are given:
1. The schema mapping (which columns map to what)
2. The metric definition
3. Access to execute Python code on the loaded DataFrames

You understand Indian NBFC portfolio analytics:
- POS = Principal Outstanding
- CE% = Collections Efficiency = (Principal Collected + Interest Collected) / EMI Due × 100
- DPD transition = how loans move between DPD buckets month-to-month
- Vintage analysis = tracking repayment by disbursement cohort over Months on Book (MOB)
- Standard 5 DPD buckets: Current | DPD 1-30 | DPD 31-60 | DPD 61-90 | DPD 90+

DPD bucket normalisation rules:
- DPD bucket columns are PRE-NORMALISED to exactly 5 standard labels:
  "Current", "DPD 1-30", "DPD 31-60", "DPD 61-90", "DPD 90+"
- Do NOT apply your own normalisation — just use these labels directly.
- A helper function normalize_dpd_bucket(value) is available in your namespace if needed.

Active loan statuses: Active, Live, Regular, Running, Open, Disbursed, NPA
Closed statuses: Closed, Fully Paid, Settled, Matured, Prepaid

IMPORTANT: Generate executable Python code. The DataFrames available depend on the dataset:
- loans_df: loan/facility data (may be None if no loan file)
- txns_df: transaction/schedule data (may be None if no transaction file)
- extra_dfs: dict of other DataFrames (borrowers, collateral, collections — may be empty)
Use ONLY the column names from the schema mapping provided.
If data required for a metric is not available, set result = {"error": "not_computable", "reason": "..."}."""


METRIC_TASK_M1 = """Compute M1: Portfolio Summary Table — Year-by-Year Time Series

Schema mapping:
{schema_mapping}

Generate Python code that computes these KPIs for ACTIVE loans, broken down by DISBURSEMENT YEAR:
1. Total POS (Principal Outstanding) in Crores
2. Interest Outstanding in Crores  
3. Active Loan Count
4. Weighted Average Interest Rate (weighted by POS)
5. Weighted Average Residual Tenor in months (maturity_date - today)

The code should:
- Filter for active loans (status in Active, Live, NPA — anything not Closed/Written Off)
- Parse the disbursement_date column to extract the YEAR
- Handle nulls gracefully
- For EACH year, compute all 5 KPIs
- Also compute OVERALL totals across all years
- Store results in a dict called 'result' with EXACTLY this structure:

  # Per-year breakdown: list of dicts sorted by year ascending
  yearly_data = []
  for year in sorted(unique_years):
      year_df = active_loans[active_loans['_disb_year'] == year]
      pos = float(year_df[pos_col].sum()) / 1e7  # convert to Crores
      interest = ...  # interest outstanding in Crores
      count = len(year_df)
      # WAIR: weighted average interest rate (weighted by POS)
      wair = ...
      # WART: weighted average residual tenor in months
      wart = ...
      yearly_data.append({{
          "year": int(year),
          "total_pos_cr": round(pos, 4),
          "interest_outstanding_cr": round(interest, 4),
          "active_loan_count": count,
          "wair_pct": round(wair, 4),
          "wart_months": round(wart, 4),
      }})

  # Overall totals
  overall_pos = sum(d['total_pos_cr'] for d in yearly_data)
  overall_interest = sum(d['interest_outstanding_cr'] for d in yearly_data)
  overall_count = sum(d['active_loan_count'] for d in yearly_data)
  # For overall WAIR/WART, recompute weighted averages across ALL active loans
  overall_wair = ...
  overall_wart = ...

  result = {{
      "yearly_data": yearly_data,
      "years": [d["year"] for d in yearly_data],
      "overall": {{
          "total_pos_cr": round(overall_pos, 4),
          "interest_outstanding_cr": round(overall_interest, 4),
          "active_loan_count": overall_count,
          "wair_pct": round(overall_wair, 4),
          "wart_months": round(overall_wart, 4),
      }}
  }}

IMPORTANT:
- Use disbursement_date (or equivalent mapped column) for year extraction
- If disbursement_date is not available, try sanction_date or application_date
- Convert date column: pd.to_datetime(loans_df[date_col], errors='coerce').dt.year
- Assign to loans_df['_disb_year'] and drop NaN years before grouping
- Print summary per year and overall

Return ONLY executable Python code, no markdown fences."""


METRIC_TASK_M2 = """Compute M2: POS Distribution by DPD Bucket

Schema mapping:
{schema_mapping}

Generate Python code that:
1. Filters active loans
2. Normalises DPD bucket labels to standard 5 buckets: Current, DPD 1-30, DPD 31-60, DPD 61-90, DPD 90+
3. Groups POS by normalised DPD bucket
4. Calculates both absolute amounts (in Crores) and percentages
5. Stores results in a dict called 'result'

Return ONLY executable Python code, no markdown fences."""


METRIC_TASK_M3 = """Compute M3: Overall Collections Efficiency Time Series

Schema mapping:
{schema_mapping}

Generate Python code that EXACTLY follows these steps:

Step 1 — Identify columns from schema mapping:
  obs_col   = '<observation_month_or_due_date_column>'   # e.g. 'observation_month_year' or 'due_date'
  sched_col = '<scheduled_emi_column>'                   # e.g. 'scheduled_emi'
  paid_col  = '<actual_total_paid_column>'               # e.g. 'actual_total_paid'
  # If no single paid column exists, sum actual_principal_paid + actual_interest_paid

Step 2 — Parse observation month:
  # If obs_col is a date column, extract YYYY-MM period:
  txns_df['_month'] = pd.to_datetime(txns_df[obs_col], errors='coerce').dt.to_period('M').astype(str)
  # If obs_col is already a string period like '2024-03', use it directly:
  # txns_df['_month'] = txns_df[obs_col].astype(str).str[:7]
  # Choose whichever approach matches the actual data.

Step 3 — Monthly CE (ALL months, sorted):
  monthly = txns_df.groupby('_month').agg(
      emi_due=pd.NamedAgg(column=sched_col, aggfunc='sum'),
      collected=pd.NamedAgg(column=paid_col, aggfunc='sum')
  ).reset_index().sort_values('_month')
  monthly = monthly[monthly['emi_due'] > 0].copy()
  monthly['ce_pct'] = (monthly['collected'] / monthly['emi_due'] * 100).round(4)
  monthly['month'] = monthly['_month']

Step 4 — Recent slices (DO NOT show all history in charts):
  # Last 24 calendar months for the monthly view
  monthly_recent = monthly.tail(24).copy()
  
  # Quarterly: derive quarter label then aggregate
  monthly['_quarter'] = pd.PeriodIndex(monthly['_month'], freq='M').to_timestamp().to_period('Q').astype(str)
  quarterly = monthly.groupby('_quarter').agg(
      emi_due=('emi_due', 'sum'),
      collected=('collected', 'sum')
  ).reset_index().sort_values('_quarter')
  quarterly = quarterly[quarterly['emi_due'] > 0].copy()
  quarterly['ce_pct'] = (quarterly['collected'] / quarterly['emi_due'] * 100).round(4)
  quarterly['month'] = quarterly['_quarter']
  # Last 8 quarters for quarterly view
  quarterly_recent = quarterly.tail(8).copy()

Step 5 — Overall stats across ALL history:
  total_emi_due  = float(monthly['emi_due'].sum())
  total_collected = float(monthly['collected'].sum())
  overall_ce_pct  = round(total_collected / total_emi_due * 100, 4) if total_emi_due else 0

Step 6 — Store result:
  result = {{
      'time_series':       monthly[['month','emi_due','collected','ce_pct']].to_dict('records'),
      'monthly_recent':    monthly_recent[['month','emi_due','collected','ce_pct']].to_dict('records'),
      'quarterly_recent':  quarterly_recent[['month','emi_due','collected','ce_pct']].to_dict('records'),
      'overall_ce_pct':    overall_ce_pct,
      'total_emi_due':     total_emi_due,
      'total_collected':   total_collected,
  }}

Return ONLY executable Python code, no markdown fences."""


METRIC_TASK_M4 = """Compute M4: Collections Efficiency by DPD Bucket (Multi-Month)

Schema mapping:
{schema_mapping}

Generate Python code that EXACTLY follows this algorithm:

Step 1: Identify columns from schema mapping:
  obs_col = '<observation_month_column>'  # e.g. 'observation_month_year'
  dpd_col = '<dpd_bucket_column>'
  emi_col = '<scheduled_emi_column>'      # or similar (emi_due, scheduled_payment)
  paid_col = '<actual_total_paid_column>'  # or actual_payment, amount_collected

Step 2: Get ALL unique months sorted:
  months = sorted(txns_df[obs_col].dropna().unique())

Step 3: Normalise DPD bucket labels:
  BUCKETS = ['Current', 'DPD 1-30', 'DPD 31-60', 'DPD 61-90', 'DPD 90+']

Step 4: For EACH month, compute CE by DPD bucket:
  by_month = {{}}
  for month in months:
      month_df = txns_df[txns_df[obs_col] == month]
      month_data = {{}}
      for bucket in BUCKETS:
          bdf = month_df[month_df[dpd_col] == bucket]
          emi_due = float(bdf[emi_col].sum()) if len(bdf) > 0 else 0
          collected = float(bdf[paid_col].sum()) if len(bdf) > 0 else 0
          ce_pct = (collected / emi_due * 100) if emi_due > 0 else 0
          loan_count = int(bdf[loan_id_col].nunique()) if len(bdf) > 0 else 0
          month_data[bucket] = {{"emi_due": emi_due, "collected": collected, "ce_pct": round(ce_pct, 2), "loan_count": loan_count}}
      by_month[str(month)] = month_data

Step 5: Store result:
  month_labels = [str(m) for m in months]
  result = {{
      "months": month_labels,
      "latest_month": month_labels[-1],
      "by_month": by_month,
      "latest": by_month[month_labels[-1]]
  }}

Return ONLY executable Python code, no markdown fences."""


METRIC_TASK_M5_M8 = """Compute M5-M8: DPD Transition Matrices (Multi-Period)

Schema mapping:
{schema_mapping}

Generate Python code that EXACTLY follows this algorithm.
DPD buckets are PRE-NORMALISED — do NOT re-normalise.

Step 1: Identify actual column names from the schema mapping above and assign them:
  obs_col  = '<observation_month_column_in_txns>'   # e.g. 'observation_month_year'
  loan_col = '<loan_id_column_in_txns>'             # e.g. 'loan_id'
  dpd_col  = '<dpd_bucket_column_in_txns>'          # e.g. 'dpd_bucket'
  pos_col  = '<closing_pos_column_in_txns>'         # e.g. 'closing_outstanding_principal'

Step 2: Find ALL unique months sorted chronologically:
  months = sorted(txns_df[obs_col].dropna().unique())

Step 3: For EACH consecutive pair of months (T-1, T), compute the transition matrix:

  BUCKETS = ['Current', 'DPD 1-30', 'DPD 31-60', 'DPD 61-90', 'DPD 90+']
  
  def compute_transition(T1, T):
      cols_T1 = txns_df[txns_df[obs_col] == T1][[loan_col, dpd_col, pos_col]].drop_duplicates(subset=[loan_col], keep='last')
      cols_T  = txns_df[txns_df[obs_col] == T ][[loan_col, dpd_col, pos_col]].drop_duplicates(subset=[loan_col], keep='last')
      df_T1 = cols_T1.rename(columns={{dpd_col: 'from_bucket', pos_col: 'from_pos'}})
      df_T  = cols_T .rename(columns={{dpd_col: 'to_bucket',   pos_col: 'to_pos'}})
      merged = df_T1.merge(df_T, on=loan_col)
      merged['from_bucket'] = merged['from_bucket'].astype(str)
      merged['to_bucket']   = merged['to_bucket'].astype(str)
      m5_raw = merged.pivot_table(index='from_bucket', columns='to_bucket', values='to_pos',   aggfunc='sum',  fill_value=0)
      m7_raw = merged.pivot_table(index='from_bucket', columns='to_bucket', values=loan_col, aggfunc='count', fill_value=0)
      m5_raw = m5_raw.reindex(index=BUCKETS, columns=BUCKETS, fill_value=0)
      m7_raw = m7_raw.reindex(index=BUCKETS, columns=BUCKETS, fill_value=0)
      m6_raw = m5_raw.div(m5_raw.sum(axis=1).replace(0, 1), axis=0) * 100
      m8_raw = m7_raw.div(m7_raw.sum(axis=1).replace(0, 1), axis=0) * 100
      def pivot_to_dict(df):
          return {{r: {{c: round(float(df.loc[r, c]), 4) for c in df.columns}} for r in df.index}}
      return pivot_to_dict(m5_raw), pivot_to_dict(m6_raw), pivot_to_dict(m7_raw), pivot_to_dict(m8_raw)

Step 4: Build result with ALL periods:
  all_m5, all_m6, all_m7, all_m8 = {{}}, {{}}, {{}}, {{}}
  period_labels = []
  for i in range(1, len(months)):
      T1, T = months[i-1], months[i]
      label = str(T)
      m5, m6, m7, m8 = compute_transition(T1, T)
      all_m5[label] = m5
      all_m6[label] = m6
      all_m7[label] = m7
      all_m8[label] = m8
      period_labels.append(label)

Step 5: Store result:
  result = {{
      'periods': period_labels,
      'latest_period': period_labels[-1] if period_labels else '',
      'm5_pos_inr':   all_m5,
      'm6_pos_pct':   all_m6,
      'm7_count':     all_m7,
      'm8_count_pct': all_m8,
  }}

Return ONLY executable Python code, no markdown fences."""


METRIC_TASK_M9 = """Compute M9: Principal Repayment Rate by Vintage Cohort

Schema mapping:
{schema_mapping}

Generate Python code that:
1. Creates quarterly cohorts from disbursement_date (e.g., 2021Q1, 2021Q2...)
2. Joins loans with transactions
3. Computes MOB (Months on Book) = months from disbursement to observation month
4. For each cohort × MOB: cumulative principal repayment % = cumulative_principal_collected / disbursed_amount × 100
5. If cumulative_principal_collected not available, compute as cumsum of actual_principal_paid per loan
6. Stores results in dict 'result' with keys: cohorts (list), max_mob, vintage_data (list of dicts with cohort, mob, repay_pct)

Return ONLY executable Python code, no markdown fences."""


# Map metric IDs to their prompts
METRIC_PROMPTS = {
    "M1": ("Portfolio Summary Table", METRIC_TASK_M1),
    "M2": ("POS by DPD Bucket", METRIC_TASK_M2),
    "M3": ("Collections Efficiency Time Series", METRIC_TASK_M3),
    "M4": ("CE by DPD Bucket", METRIC_TASK_M4),
    "M5_M6_M7_M8": ("DPD Transition Matrices", METRIC_TASK_M5_M8),
    "M9": ("Repayment by Cohort", METRIC_TASK_M9),
}

# ═══════════════════════════════════════════════════════════════════════════
#  VISUALIZATION AGENT — Interactive Plotly Charts
# ═══════════════════════════════════════════════════════════════════════════

VIZ_SYSTEM = """You are an expert Financial Data Visualization AI agent.
Your job is to write Python code using Plotly to create INTERACTIVE charts
from pre-computed loan portfolio metric results.

You MUST produce clean, runnable Python code. No explanations, just code.

THEME SPECIFICATION (dark theme — match case study style):
- Paper background: #1a1a2e
- Plot background: #16213e
- Grid color: #2a2a4a  (alpha 0.3)
- Text / labels: #e0e0e0
- Accent green: #4ade80   (good / positive)
- Accent red: #ef4444     (bad / negative)
- Accent orange: #f59e0b  (warning)
- Accent blue: #3b82f6    (neutral)
- DPD bucket color scale (5 buckets, Current→90+):
  ["#4ade80", "#facc15", "#f59e0b", "#f97316", "#ef4444"]
- Always start from template="plotly_dark" then override paper_bgcolor, plot_bgcolor, font.

AVAILABLE IN YOUR NAMESPACE:
- metrics_data: dict[str, Any]  — metric_id → result data (already computed)
- go (plotly.graph_objects), px (plotly.express), pio (plotly.io), sp (plotly.subplots)
- make_subplots (from plotly.subplots — available directly, no need to import)
- pd (pandas), np (numpy), json
- result: dict — YOU MUST populate this: result[metric_id] = go.Figure(...)

CHART TYPE GUIDELINES:
- M1 (Portfolio Summary — Year-by-Year with Slider):
  The data dict has keys: yearly_data (list of dicts per year), years (list of ints), overall (dict with totals).
  If yearly_data is empty or missing, fall back to overall dict as a simple table.
  
  BUILD A GROUPED BAR CHART with a RANGE SLIDER that filters by year range.
  The slider starts at the earliest year and goes up to "Overall" (all years combined).
  
  CRITICAL — Build EXACTLY like this:
  
    d = metrics_data["M1"]
    yearly_data = d.get("yearly_data", [])
    years = d.get("years", [])
    overall = d.get("overall", {{}})
    
    if not yearly_data:
        # Fallback: simple table for legacy flat data
        labels = ["Total POS (₹ Cr)", "Interest Outstanding (₹ Cr)", "Active Loan Count",
                  "Weighted Avg Interest Rate (%)", "Weighted Avg Residual Tenor (months)"]
        vals = [
            f"{{overall.get('total_pos_cr', 0):,.2f}}",
            f"{{overall.get('interest_outstanding_cr', 0):,.2f}}",
            f"{{int(overall.get('active_loan_count', 0)):,}}",
            f"{{overall.get('wair_pct', 0):.2f}}%",
            f"{{overall.get('wart_months', 0):.2f}} months",
        ]
        fig = go.Figure(go.Table(
            header=dict(values=["<b>Metric</b>", "<b>Value</b>"],
                        fill_color='#2563eb', font=dict(color='white', size=14), align='left'),
            cells=dict(values=[labels, vals],
                       fill_color='#16213e', font=dict(color='#e0e0e0', size=13), align='left', height=35)
        ))
        fig.update_layout(title=dict(text='<b>M1 — Portfolio Summary</b>', x=0.02),
                          paper_bgcolor='#1a1a2e', height=350, width=900, margin=dict(l=20, r=20, t=60, b=20))
        result["M1"] = fig
    else:
        # Build cumulative year data: slider position i shows years[0..i], last position = Overall
        import plotly.subplots as sp
        
        kpi_keys = ["total_pos_cr", "interest_outstanding_cr", "active_loan_count", "wair_pct", "wart_months"]
        kpi_labels = ["Total POS (₹ Cr)", "Interest Outstanding (₹ Cr)", "Active Loan Count",
                      "Weighted Avg Interest Rate (%)", "Weighted Avg Residual Tenor (months)"]
        
        # Build slider steps: one for each year + one for "Overall"
        slider_labels = [str(y) for y in years] + ["Overall"]
        
        # Pre-compute data for each slider position
        # Position i (year) = data for ONLY that year
        # Last position (Overall) = overall totals
        all_frames = []
        for i, year in enumerate(years):
            row = yearly_data[i]
            all_frames.append({{
                "label": str(year),
                "values": [
                    f"{{row.get('total_pos_cr', 0):,.2f}}",
                    f"{{row.get('interest_outstanding_cr', 0):,.2f}}",
                    f"{{int(row.get('active_loan_count', 0)):,}}",
                    f"{{row.get('wair_pct', 0):.2f}}%",
                    f"{{row.get('wart_months', 0):.2f}} months",
                ],
                "raw": [row.get(k, 0) for k in kpi_keys],
            }})
        # Overall position
        all_frames.append({{
            "label": "Overall",
            "values": [
                f"{{overall.get('total_pos_cr', 0):,.2f}}",
                f"{{overall.get('interest_outstanding_cr', 0):,.2f}}",
                f"{{int(overall.get('active_loan_count', 0)):,}}",
                f"{{overall.get('wair_pct', 0):.2f}}%",
                f"{{overall.get('wart_months', 0):.2f}} months",
            ],
            "raw": [overall.get(k, 0) for k in kpi_keys],
        }})
        
        # Create figure with one Table trace per slider position
        fig = go.Figure()
        
        for idx, frame in enumerate(all_frames):
            fig.add_trace(go.Table(
                header=dict(
                    values=["<b>Metric</b>", "<b>Value</b>"],
                    fill_color='#2563eb',
                    font=dict(color='white', size=14),
                    align='left',
                    line_color='#2a2a4a',
                    height=40,
                ),
                cells=dict(
                    values=[kpi_labels, frame["values"]],
                    fill_color='#16213e',
                    font=dict(color='#e0e0e0', size=13),
                    align='left',
                    line_color='#2a2a4a',
                    height=35,
                ),
                visible=(idx == len(all_frames) - 1),  # Default: show Overall
            ))
        
        # Build slider steps
        steps = []
        for idx, frame in enumerate(all_frames):
            vis = [False] * len(all_frames)
            vis[idx] = True
            step_title = f"Year: {{frame['label']}}" if frame['label'] != "Overall" else "Overall (All Years)"
            steps.append(dict(
                method='update',
                args=[{{'visible': vis}},
                      {{'title': dict(text=f'<b>M1 — Portfolio Summary</b>  <span style="font-size:13px;color:#8892a4">({{step_title}})</span>', x=0.02)}}],
                label=frame['label'],
            ))
        
        sliders = [dict(
            active=len(all_frames) - 1,
            currentvalue=dict(prefix="Showing: ", font=dict(color='#e0e0e0', size=14)),
            pad=dict(t=40, b=10),
            steps=steps,
            bgcolor='#2a2a4a',
            activebgcolor='#3b82f6',
            bordercolor='#3b82f6',
            font=dict(color='#e0e0e0', size=11),
            ticklen=4,
        )]
        
        fig.update_layout(
            sliders=sliders,
            title=dict(text='<b>M1 — Portfolio Summary</b>  <span style="font-size:13px;color:#8892a4">(Overall (All Years))</span>', x=0.02),
            paper_bgcolor='#1a1a2e',
            font=dict(color='#e0e0e0'),
            height=450,
            width=950,
            margin=dict(l=20, r=20, t=80, b=80),
        )
        result["M1"] = fig
- M2 (POS by DPD Bucket): Horizontal bar chart.
  Show bucket names on Y, POS values on X, annotate with percentage.
  Format values in ₹ Crores.
  
  CRITICAL — always set these to prevent label overflow on the longest bar:
    fig.update_traces(cliponaxis=False)
    fig.update_layout(margin=dict(l=20, r=180, t=80, b=60))
  
  Use textposition='outside' for all bar labels. The right margin of 180px ensures
  the label for the longest bar (e.g. "Current") is never clipped at the chart edge.
- M3 (Collections Efficiency Time Series): Grouped bar chart with CE% line overlay, MONTHLY/QUARTERLY toggle.
  The data dict has keys: monthly_recent (last 24 months), quarterly_recent (last 8 quarters),
  time_series (full history — do NOT use this for the chart), overall_ce_pct.
  Each record has: month, emi_due, collected, ce_pct.
  
  CRITICAL RULES for this chart:
  1. xaxis MUST have type='category' (months and quarters are STRING labels like "2024-04" and
     "2024Q2" — Plotly will misinterpret them as dates without category type and the chart
     will appear EMPTY in Quarterly view).
  2. Use plotly.subplots.make_subplots with secondary_y=True for dual Y-axes.
  3. Primary Y-axis (left) = INR Crore (for bars). Secondary Y-axis (right) = CE % (for line).
  4. Build exactly 6 traces in this order:
     [0] Monthly EMI Due bars, [1] Monthly Collected bars, [2] Monthly CE% line,
     [3] Quarterly EMI Due bars, [4] Quarterly Collected bars, [5] Quarterly CE% line.
  5. Default visibility: [True, True, True, False, False, False] (Monthly view active).
  6. Bar colors: EMI Due = '#4682B4' (steel blue), Collected = '#2dd4bf' (teal green).
  7. CE% line: color '#f59e0b' (orange), with data labels (textposition='top center').
  8. Convert emi_due and collected to Crores (divide by 1e7).
  
  Build the chart EXACTLY like this:
  
    from plotly.subplots import make_subplots
    data = metrics_data["M3"]
    monthly_data    = data.get("monthly_recent")    or data.get("time_series", [])
    quarterly_data  = data.get("quarterly_recent")  or []
  
    def extract_all(rows):
        if not rows: return [], [], [], []
        mk = next((k for k in rows[0] if any(x in k.lower() for x in ['month','period','quarter','date'])), list(rows[0].keys())[0])
        xs = [r[mk] for r in rows]
        emi = [r.get('emi_due', 0) / 1e7 for r in rows]
        coll = [r.get('collected', 0) / 1e7 for r in rows]
        ce = [r.get('ce_pct', r.get('collection_efficiency', r.get('ce', 0))) for r in rows]
        return xs, emi, coll, ce
  
    m_x, m_emi, m_coll, m_ce = extract_all(monthly_data)
    q_x, q_emi, q_coll, q_ce = extract_all(quarterly_data)
  
    fig = make_subplots(specs=[[{{"secondary_y": True}}]])
  
    # Trace 0: Monthly EMI Due bars (visible)
    fig.add_trace(go.Bar(
        x=m_x, y=m_emi, name='EMI Due (₹ Cr)',
        marker_color='#4682B4', opacity=0.85, visible=True,
        offsetgroup=0,
    ), secondary_y=False)
    # Trace 1: Monthly Collected bars (visible)
    fig.add_trace(go.Bar(
        x=m_x, y=m_coll, name='Collected (₹ Cr)',
        marker_color='#2dd4bf', opacity=0.85, visible=True,
        offsetgroup=1,
    ), secondary_y=False)
    # Trace 2: Monthly CE% line with data labels (visible)
    fig.add_trace(go.Scatter(
        x=m_x, y=m_ce, mode='lines+markers+text', name='CE %',
        line=dict(color='#f59e0b', width=2.5),
        marker=dict(size=5, color='#f59e0b'),
        text=[f'{{v:.1f}}%' for v in m_ce], textposition='top center',
        textfont=dict(size=9, color='#f59e0b'),
        visible=True,
    ), secondary_y=True)
    # Trace 3: Quarterly EMI Due bars (hidden)
    fig.add_trace(go.Bar(
        x=q_x, y=q_emi, name='EMI Due (₹ Cr)',
        marker_color='#4682B4', opacity=0.85, visible=False,
        offsetgroup=0,
    ), secondary_y=False)
    # Trace 4: Quarterly Collected bars (hidden)
    fig.add_trace(go.Bar(
        x=q_x, y=q_coll, name='Collected (₹ Cr)',
        marker_color='#2dd4bf', opacity=0.85, visible=False,
        offsetgroup=1,
    ), secondary_y=False)
    # Trace 5: Quarterly CE% line with data labels (hidden)
    fig.add_trace(go.Scatter(
        x=q_x, y=q_ce, mode='lines+markers+text', name='CE %',
        line=dict(color='#f59e0b', width=2.5),
        marker=dict(size=7, symbol='diamond', color='#f59e0b'),
        text=[f'{{v:.1f}}%' for v in q_ce], textposition='top center',
        textfont=dict(size=10, color='#f59e0b'),
        visible=False,
    ), secondary_y=True)
  
    overall = data.get('overall_ce_pct', 0)
    # Compute y-axis ranges
    all_ce = [v for v in (m_ce + q_ce) if isinstance(v, (int, float)) and v > 0]
    ce_min = max(0, min(all_ce) - 10) if all_ce else 0
    ce_max = max(105, max(all_ce) + 5) if all_ce else 110
    all_bar = [v for v in (m_emi + m_coll + q_emi + q_coll) if isinstance(v, (int, float))]
    bar_max = max(all_bar) * 1.15 if all_bar else 100
  
    fig.update_layout(
        barmode='group',
        updatemenus=[dict(
            type='buttons', direction='right',
            x=0.0, y=1.12, xanchor='left',
            showactive=True,
            buttons=[
                dict(label='Monthly',   method='update', args=[{{'visible': [True,  True,  True,  False, False, False]}}, {{}}]),
                dict(label='Quarterly', method='update', args=[{{'visible': [False, False, False, True,  True,  True ]}}, {{}}]),
            ],
            bgcolor='#2a2a4a', bordercolor='#3b82f6',
            font=dict(color='#e0e0e0', size=13)
        )],
        title=dict(text=f'<b>M3 \u2014 Overall Collections Efficiency</b>  <span style="font-size:13px;color:#8892a4">(Overall CE: {{overall:.2f}}%)</span>', x=0.02),
        xaxis=dict(title='Period', tickangle=-35, type='category'),
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1, font=dict(size=11)),
        height=580, width=1100,
        bargap=0.15, bargroupgap=0.05,
    )
    fig.update_yaxes(title_text='Amount (₹ Crore)', range=[0, bar_max], secondary_y=False)
    fig.update_yaxes(title_text='CE %', range=[ce_min, ce_max], secondary_y=True)
- M4 (CE by DPD Bucket): Vertical bar chart with MONTH SELECTOR.
  The data dict has keys: months (list), latest_month, by_month (dict of month → bucket data), latest.
  If data has "by_month", use it for multi-month support.
  If data only has simple bucket keys (backward compat), treat as single-month.
  
  CRITICAL RULES for M4:
  1. Show DPD buckets on X-axis, CE% on Y-axis.
  2. Color bars by bucket severity (green→red): ["#4ade80", "#facc15", "#f59e0b", "#f97316", "#ef4444"].
  3. Annotate CE% values on top of each bar.
  4. Add a vertical reference line at 100% (dashed orange).
  5. If multi-month data exists, add a MONTH SELECTOR dropdown (Plotly updatemenus).
     Create one set of bar traces per month. Default to the latest month visible.
  
  Build the chart with this pattern:
  
    data = metrics_data["M4"]
    bucket_order = ["Current", "DPD 1-30", "DPD 31-60", "DPD 61-90", "DPD 90+"]
    bucket_colors = ["#4ade80", "#facc15", "#f59e0b", "#f97316", "#ef4444"]
    
    by_month = data.get("by_month", {{}})
    months = data.get("months", [])
    if not by_month:
        # Backward compat: data is single-month bucket dict
        by_month = {{"Latest": data.get("latest", data)}}
        months = ["Latest"]
    
    fig = go.Figure()
    for i, month in enumerate(months):
        month_data = by_month.get(month, {{}})
        ces = []
        for b in bucket_order:
            bd = month_data.get(b, {{}})
            if isinstance(bd, dict):
                ce = bd.get("ce_pct", bd.get("ce", 0))
            else:
                ce = bd if isinstance(bd, (int, float)) else 0
            ces.append(ce if ce else 0)
        fig.add_trace(go.Bar(
            x=bucket_order, y=ces,
            marker_color=bucket_colors,
            text=[f"{{v:.1f}}%" for v in ces], textposition='outside',
            visible=(i == len(months) - 1),  # latest visible by default
            name=month
        ))
    
    # Add 100% reference line
    fig.add_hline(y=100, line_dash="dash", line_color="#f59e0b", line_width=1.5,
                  annotation_text="100%", annotation_position="top right")
    
    # Month selector dropdown
    if len(months) > 1:
        buttons = []
        for i, month in enumerate(months):
            vis = [j == i for j in range(len(months))]
            buttons.append(dict(label=str(month), method='update',
                               args=[{{'visible': vis}}, {{'title': dict(text=f'<b>M4 — CE by DPD Bucket</b> ({{month}})')}}]))
        fig.update_layout(
            updatemenus=[dict(type='dropdown', direction='down', x=1.0, y=1.15, xanchor='right',
                             showactive=True, buttons=buttons,
                             bgcolor='#2a2a4a', bordercolor='#3b82f6', font=dict(color='#e0e0e0'))]
        )
    
    latest = months[-1] if months else ""
    fig.update_layout(
        title=dict(text=f'<b>M4 — CE by DPD Bucket</b> ({{latest}})', x=0.02),
        xaxis=dict(title='DPD Bucket'), yaxis=dict(title='CE %'),
        height=550, width=950,
    )
- M5/M6/M7/M8 (Transition Matrices): INDIVIDUAL go.Heatmap charts with PERIOD SELECTOR.
  The data dict has keys: periods (list), latest_period, m5_pos_inr, m6_pos_pct, m7_count, m8_count_pct.
  Each matrix key (e.g. m5_pos_inr) maps to a dict: {{period_label: {{from_bucket: {{to_bucket: value}}}}}}.
  If the data has NO 'periods' key, it's single-period: {{from_bucket: {{to_bucket: value}}}}.
  
  IMPORTANT: Charts are generated INDIVIDUALLY. The metric_id will be "M5", "M6", "M7", or "M8".
  Map the metric_id to the correct data key:
    M5 → "m5_pos_inr" (format as ₹ Cr, divide by 1e7)
    M6 → "m6_pos_pct" (format as %)
    M7 → "m7_count" (format as integers)
    M8 → "m8_count_pct" (format as %)
  
  Build the chart EXACTLY like this (replace METRIC_ID with the actual metric_id e.g. "M5"):
  
    mid = "METRIC_ID"  # e.g. "M5", "M6", "M7", or "M8"
    data = metrics_data[mid]
    bucket_order = ["Current", "DPD 1-30", "DPD 31-60", "DPD 61-90", "DPD 90+"]
    
    key_map = {{"M5": "m5_pos_inr", "M6": "m6_pos_pct", "M7": "m7_count", "M8": "m8_count_pct"}}
    label_map = {{"M5": "POS Transition (₹ Cr)", "M6": "POS Transition (%)", "M7": "Loan Count Transition", "M8": "Loan Count Transition (%)"}}
    data_key = key_map.get(mid, list(key_map.values())[0])
    chart_label = label_map.get(mid, mid)
    
    raw = data.get(data_key, {{}})
    periods = data.get("periods", [])
    
    # Detect if raw is multi-period or single-period
    def is_multi_period(raw_data):
        if not isinstance(raw_data, dict) or not raw_data:
            return False
        first_val = list(raw_data.values())[0]
        if isinstance(first_val, dict):
            inner_val = list(first_val.values())[0]
            return isinstance(inner_val, dict)
        return False
    
    if not periods and is_multi_period(raw):
        periods = sorted(raw.keys())
    
    def get_matrix(raw_data, period=None):
        if period and period in raw_data:
            mat = raw_data[period]
        elif is_multi_period(raw_data):
            mat = raw_data[sorted(raw_data.keys())[-1]]
        else:
            mat = raw_data
        z = []
        for fb in bucket_order:
            row = []
            for tb in bucket_order:
                val = 0
                if isinstance(mat, dict) and fb in mat and isinstance(mat[fb], dict):
                    val = mat[fb].get(tb, 0)
                row.append(float(val) if val else 0)
            z.append(row)
        return z
    
    def fmt_val(v):
        if 'inr' in data_key:
            return f"₹{{v/1e7:.2f}} Cr"
        elif 'pct' in data_key:
            return f"{{v:.1f}}%"
        else:
            return f"{{int(v)}}"
    
    if periods and len(periods) > 1:
        # Multi-period: create one heatmap trace per period, use slider
        fig = go.Figure()
        for i, period in enumerate(periods):
            z = get_matrix(raw, period)
            text = [[fmt_val(v) for v in row] for row in z]
            fig.add_trace(go.Heatmap(
                z=z, x=bucket_order, y=bucket_order,
                text=text, texttemplate="%{{text}}",
                colorscale=[[0, '#16213e'], [0.5, '#f59e0b'], [1, '#ef4444']],
                showscale=(i == len(periods) - 1),
                visible=(i == len(periods) - 1),
                hovertemplate='From: %{{y}}<br>To: %{{x}}<br>Value: %{{text}}<extra></extra>'
            ))
        
        # Period selector dropdown (show last 12 periods max)
        show_periods = periods[-12:] if len(periods) > 12 else periods
        offset = len(periods) - len(show_periods)
        buttons = []
        for i, period in enumerate(show_periods):
            idx = offset + i
            vis = [j == idx for j in range(len(periods))]
            buttons.append(dict(label=str(period), method='update',
                               args=[{{'visible': vis}}, {{'title': dict(text=f'<b>{{mid}} — {{chart_label}}</b> ({{period}})')}}]))
        fig.update_layout(
            updatemenus=[dict(type='dropdown', direction='down', x=1.0, y=1.15, xanchor='right',
                             showactive=True, buttons=buttons,
                             bgcolor='#2a2a4a', bordercolor='#3b82f6', font=dict(color='#e0e0e0'))]
        )
        latest = periods[-1]
    else:
        # Single period
        period = periods[0] if periods else None
        z = get_matrix(raw, period)
        text = [[fmt_val(v) for v in row] for row in z]
        fig = go.Figure(go.Heatmap(
            z=z, x=bucket_order, y=bucket_order,
            text=text, texttemplate="%{{text}}",
            colorscale=[[0, '#16213e'], [0.5, '#f59e0b'], [1, '#ef4444']],
            showscale=True,
            hovertemplate='From: %{{y}}<br>To: %{{x}}<br>Value: %{{text}}<extra></extra>'
        ))
        latest = period or "Latest"
    
    fig.update_layout(
        title=dict(text=f'<b>{{mid}} — {{chart_label}}</b> ({{latest}})', x=0.02),
        xaxis=dict(title='To Bucket', side='bottom', type='category'),
        yaxis=dict(title='From Bucket', autorange='reversed', type='category'),
        height=600, width=1000,
    )

- M9 (Vintage Cohort Curves): Multi-line chart with COHORT SELECTOR.
  The data dict has keys: cohorts (list), max_mob (int), vintage_data (list of dicts).
  Each dict in vintage_data has: cohort, mob, repay_pct.
  
  CRITICAL RULES for M9:
  1. Group vintage_data by cohort to get one line per cohort (X=mob, Y=repay_pct).
  2. Sort cohorts chronologically, take the most recent 12.
  3. Add a COHORT SELECTOR using Plotly updatemenus dropdown that lets the user
     toggle which cohorts are visible: "All Cohorts", "Last 4", "Last 8", "Last 12".
  4. Use a viridis-like color progression across cohorts.
  5. Include a legend and hovertemplate showing cohort + MOB + repay_pct.
  
  Build the chart EXACTLY like this:
  
    data = metrics_data["M9"]
    vintage_data = data.get("vintage_data", [])
    
    # Group by cohort
    from collections import defaultdict
    cohort_series = defaultdict(lambda: {{"mobs": [], "pcts": []}})
    for row in vintage_data:
        c = row.get("cohort", "")
        m = row.get("mob", 0)
        p = row.get("repay_pct", row.get("repayment_pct", row.get("cumulative_repay_pct", 0)))
        if c and isinstance(m, (int, float)):
            cohort_series[c]["mobs"].append(m)
            cohort_series[c]["pcts"].append(p if p else 0)
    
    # Sort cohorts and take recent 12
    sorted_cohorts = sorted(cohort_series.keys())
    recent_12 = sorted_cohorts[-12:] if len(sorted_cohorts) > 12 else sorted_cohorts
    
    # Color scale (viridis-like)
    n = len(recent_12)
    colors = px.colors.sample_colorscale("Viridis", [i/(max(n-1,1)) for i in range(n)])
    
    fig = go.Figure()
    for i, cohort in enumerate(recent_12):
        s = cohort_series[cohort]
        # Sort by MOB
        pairs = sorted(zip(s["mobs"], s["pcts"]))
        mobs = [p[0] for p in pairs]
        pcts = [p[1] for p in pairs]
        fig.add_trace(go.Scatter(
            x=mobs, y=pcts, mode='lines+markers', name=cohort,
            line=dict(color=colors[i], width=2),
            marker=dict(size=4),
            hovertemplate=f'Cohort: {{cohort}}<br>MOB: %{{{{x}}}}<br>Repayment: %{{{{y}}}}:.1f}}%<extra></extra>'
        ))
    
    # Cohort selector dropdown: All, Last 4, Last 8, Last 12
    all_vis = [True] * n
    last4_vis = [(i >= n - 4) for i in range(n)]
    last8_vis = [(i >= n - 8) for i in range(n)]
    last12_vis = [True] * n  # already limited to 12
    
    fig.update_layout(
        updatemenus=[dict(
            type='dropdown', direction='down',
            x=1.0, y=1.15, xanchor='right',
            showactive=True,
            buttons=[
                dict(label='All Cohorts',  method='update', args=[{{'visible': all_vis}}]),
                dict(label='Last 4',       method='update', args=[{{'visible': last4_vis}}]),
                dict(label='Last 8',       method='update', args=[{{'visible': last8_vis}}]),
            ],
            bgcolor='#2a2a4a', bordercolor='#3b82f6',
            font=dict(color='#e0e0e0', size=12)
        )],
        title=dict(text='<b>M9 — Vintage Cohort Repayment Curves</b><br>'
                        '<span style="font-size:12px;color:#8892a4">Cumulative Principal Repayment % by Months on Book</span>',
                   x=0.02),
        xaxis=dict(title='Months on Book (MOB)', gridcolor='rgba(42,42,74,0.3)', dtick=3),
        yaxis=dict(title='Cumulative Repayment %', gridcolor='rgba(42,42,74,0.3)',
                   ticksuffix='%'),
        legend=dict(title=dict(text='Cohort'), orientation='h', yanchor='bottom', y=1.02,
                    xanchor='right', x=1, bgcolor='rgba(26,26,46,0.8)'),
        height=650, width=1100, hovermode='x unified',
    )

DATA HANDLING RULES:
- metrics_data[metric_id] is the raw result dict. Inspect its keys dynamically.
- NEVER assume specific key names — always print(list(data.keys())) first, then adapt.
  For time series data (M3), use 'monthly_recent' key (last 24 months) for the monthly trace,
  and 'quarterly_recent' key (last 8 quarters) for the quarterly trace.
  Do NOT use 'time_series' (full history) for the chart axes.
  For list-of-dicts, inspect the first item's keys to discover field names.
- Values may be nested dicts like {{key: {{count: N, percentage: P}}}} — extract the
  numeric value (prefer 'count' for bar charts, 'percentage' for pies).
- Lists of dicts: iterate to extract labels and values.
- Always handle missing keys gracefully with .get() defaults.
- Numeric values may be 0 (sanitized from None) — handle zeros gracefully in charts.
- Before sorting any list by a numeric field, filter out non-numeric values:
  e.g. [x for x in items if isinstance(x.get('value'), (int, float))]
- If a metric's data is empty or unexpected, skip it (don't crash).
- For large vintage data with many cohorts (>15), only plot representative ones.

FORMATTING RULES:
- Indian number formatting for currency: ₹ Crores (÷1e7), ₹ Lakhs (÷1e5)
- Percentages: 1-2 decimal places
- Chart titles: bold, descriptive, include metric name
- Make charts responsive and interactive (hover, zoom, pan)
- Set reasonable figure dimensions (width=900-1200, height=500-700)

CRITICAL: You must set result[metric_id] = fig for EVERY metric you handle.
Generate code for these metrics: {metric_ids}
"""

VIZ_TASK_TEMPLATE = """Below is the computed metric data. Generate Plotly code for: {metric_ids}

{metrics_summary}

IMPORTANT:
- Write ONE code block that generates the chart for this metric.
- Set result["<metric_id>"] = fig
- Only use data from metrics_data dict (already provided in your namespace).
- Handle nested data structures robustly.
- Do NOT import anything — go, px, pd, np, json are already in scope.
- Do NOT call fig.show() — only assign to result dict.
"""
