"""
Canonical field definitions — the Python representation of SKILLS.md.
Used by Schema Discovery Agent for column matching.

Each field definition includes:
  - semantic: what the field means (for future LLM matching)
  - possible_names: all known column name variations
  - dtype: expected data type
  - derivation: list of derivation strategies (tried in order)
  - required_by: which metrics need this field
"""

from __future__ import annotations

# ── Standard DPD bucket order ─────────────────────────────────────────────
DPD_BUCKET_ORDER = ["Current", "DPD 1-30", "DPD 31-60", "DPD 61-90", "DPD 90+"]

# ── DPD bucket normalisation map (all known variations → standard) ────────
DPD_BUCKET_NORM: dict[str, str] = {
    # Current
    "current (dpd 0)": "Current",
    "current": "Current",
    "0": "Current",
    "standard": "Current",
    "bucket 0": "Current",
    "dpd 0": "Current",
    "0 dpd": "Current",
    "no overdue": "Current",
    # DPD 1-30
    "sma-0 (dpd 1-30)": "DPD 1-30",
    "dpd 01-30": "DPD 1-30",
    "dpd 1-30": "DPD 1-30",
    "1-30": "DPD 1-30",
    "sma-0": "DPD 1-30",
    "sma0": "DPD 1-30",
    "bucket 1": "DPD 1-30",
    "1 to 30": "DPD 1-30",
    "01-30": "DPD 1-30",
    # DPD 31-60
    "sma-1 (dpd 31-60)": "DPD 31-60",
    "dpd 31-60": "DPD 31-60",
    "31-60": "DPD 31-60",
    "sma-1": "DPD 31-60",
    "sma1": "DPD 31-60",
    "bucket 2": "DPD 31-60",
    "31 to 60": "DPD 31-60",
    # DPD 61-90
    "sma-2 (dpd 61-90)": "DPD 61-90",
    "dpd 61-90": "DPD 61-90",
    "61-90": "DPD 61-90",
    "sma-2": "DPD 61-90",
    "sma2": "DPD 61-90",
    "bucket 3": "DPD 61-90",
    "61 to 90": "DPD 61-90",
    # DPD 90+  (including sub-buckets that must merge)
    "npa (dpd 90+)": "DPD 90+",
    "dpd 90+": "DPD 90+",
    "dpd 91-180": "DPD 90+",
    "dpd 181+": "DPD 90+",
    "90+": "DPD 90+",
    "npa": "DPD 90+",
    "bucket 4": "DPD 90+",
    "loss": "DPD 90+",
    "91-180": "DPD 90+",
    "181+": "DPD 90+",
    "91 to 180": "DPD 90+",
    "above 90": "DPD 90+",
    "90 and above": "DPD 90+",
    ">90": "DPD 90+",
    "doubtful": "DPD 90+",
}

# ── Active loan status values ─────────────────────────────────────────────
ACTIVE_STATUSES = {
    "active", "Active", "ACTIVE",
    "live", "Live", "LIVE",
    "regular", "Regular", "REGULAR",
    "running", "Running",
    "open", "Open", "OPEN",
    "disbursed", "Disbursed",
}

CLOSED_STATUSES = {
    "closed", "Closed", "CLOSED",
    "fully paid", "Fully Paid",
    "settled", "Settled",
    "matured", "Matured",
    "prepaid", "Prepaid",
}

NPA_STATUSES = {
    "npa", "NPA", "Npa",
    "non performing", "Non-Performing",
    "default", "Default", "DEFAULT",
}

WRITTEN_OFF_STATUSES = {
    "written off", "Written Off", "WRITTEN OFF",
    "write off", "Write Off",
    "write-off", "Write-Off",
    "w/o", "W/O",
}


def normalise_dpd_bucket(raw: str) -> str:
    """Normalise any DPD bucket label to standard 5-bucket format."""
    if not raw or str(raw).strip() == "" or str(raw).lower() == "nan":
        return ""
    key = str(raw).strip().lower()
    return DPD_BUCKET_NORM.get(key, "")


def dpd_to_bucket(dpd: int) -> str:
    """Convert numeric DPD to standard bucket."""
    if dpd <= 0:
        return "Current"
    elif dpd <= 30:
        return "DPD 1-30"
    elif dpd <= 60:
        return "DPD 31-60"
    elif dpd <= 90:
        return "DPD 61-90"
    else:
        return "DPD 90+"


def is_active_status(status: str) -> bool:
    """Check if a loan status means the loan is active."""
    s = str(status).strip()
    if s in ACTIVE_STATUSES:
        return True
    if s in CLOSED_STATUSES or s in WRITTEN_OFF_STATUSES:
        return False
    # NPA loans are still "active" (have outstanding balance) unless explicitly closed
    if s in NPA_STATUSES:
        return True
    return False


# ═══════════════════════════════════════════════════════════════════════════
#  CANONICAL FIELD DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════

LOAN_FIELDS: dict[str, dict] = {
    "loan_id": {
        "semantic": "Unique identifier for each loan account or facility",
        "possible_names": [
            "loan_id", "loan_no", "account_id", "facility_id",
            "loan_account_number", "account_no", "loan_number",
            "loan_reference", "agreement_id", "agreement_no",
            "contract_id", "lan", "loan_ref",
        ],
        "dtype": "string",
        "mandatory": True,
        "required_by": ["M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8", "M9"],
    },
    "borrower_id": {
        "semantic": "Unique identifier linking loan to its borrower",
        "possible_names": [
            "borrower_id", "customer_id", "cust_id", "client_id",
            "borrower_no", "applicant_id", "party_id", "member_id",
            "customer_number",
        ],
        "dtype": "string",
        "mandatory": False,
        "required_by": ["filters"],
    },
    "product_type": {
        "semantic": "Loan product category such as Commercial Vehicle, Housing, LAP",
        "possible_names": [
            "product_type", "product", "loan_type", "product_name",
            "product_category", "scheme", "loan_product", "product_code",
            "loan_category", "facility_type", "product_desc",
        ],
        "dtype": "category",
        "mandatory": False,
        "required_by": ["filters"],
    },
    "disbursement_date": {
        "semantic": "Date when the loan principal was disbursed to the borrower",
        "possible_names": [
            "disbursement_date", "disb_date", "disbursement_dt",
            "funded_date", "disbursal_date", "disbursed_date",
            "date_of_disbursement", "drawdown_date", "booking_date",
            "disb_dt",
        ],
        "dtype": "date",
        "mandatory": True,
        "required_by": ["M9"],
    },
    "maturity_date": {
        "semantic": "Scheduled end date of the loan, the last EMI date",
        "possible_names": [
            "maturity_date", "maturity_dt", "end_date", "last_emi_date",
            "loan_end_date", "expiry_date", "termination_date",
            "final_due_date", "loan_maturity_date",
        ],
        "dtype": "date",
        "mandatory": False,
        "required_by": ["M1"],
        "derivation": [
            {"method": "formula", "formula": "disbursement_date + tenor_months", "needs": ["disbursement_date", "tenor_months"]},
        ],
    },
    "sanctioned_amount": {
        "semantic": "Total loan amount approved or sanctioned by the lender",
        "possible_names": [
            "sanctioned_amount", "sanction_amt", "approved_amount",
            "loan_amount", "sanctioned_amt", "principal_sanctioned",
            "principal_sanctioned_INR", "sanction_amount",
            "credit_limit", "facility_amount",
        ],
        "dtype": "numeric",
        "mandatory": False,
        "required_by": ["validation"],
    },
    "disbursed_amount": {
        "semantic": "Actual principal amount disbursed to the borrower",
        "possible_names": [
            "disbursed_amount", "disb_amt", "disbursed_principal",
            "principal_disbursed", "principal_disbursed_INR",
            "disbursement_amount", "funded_amount", "loan_disbursed",
            "net_disbursement",
        ],
        "dtype": "numeric",
        "mandatory": True,
        "required_by": ["M9"],
        "derivation": [
            {"method": "fallback_column", "fallback": "sanctioned_amount"},
        ],
    },
    "interest_rate": {
        "semantic": "Annual interest rate on the loan as a percentage",
        "possible_names": [
            "annual_interest_rate_pct", "interest_rate", "roi", "rate",
            "interest_pct", "annual_rate", "rate_of_interest",
            "lending_rate", "applicable_rate", "contracted_rate",
            "interest_rate_pct", "coupon_rate",
        ],
        "dtype": "numeric",
        "mandatory": True,
        "required_by": ["M1"],
    },
    "tenor_months": {
        "semantic": "Original loan tenor or term in months",
        "possible_names": [
            "tenor_months", "tenure", "loan_term", "tenor",
            "tenure_months", "loan_tenure", "term_months",
            "repayment_period", "number_of_installments",
            "total_installments", "number_of_installments_scheduled",
            "no_of_emis",
        ],
        "dtype": "integer",
        "mandatory": False,
        "required_by": ["M1"],
        "derivation": [
            {"method": "formula", "formula": "(maturity_date - disbursement_date).months", "needs": ["maturity_date", "disbursement_date"]},
        ],
    },
    "emi_amount": {
        "semantic": "Scheduled equated monthly instalment amount",
        "possible_names": [
            "emi_amount", "emi", "monthly_payment", "instalment_amount",
            "emi_amount_INR", "emi_amt", "installment_amount",
            "scheduled_emi", "monthly_instalment", "repayment_amount",
        ],
        "dtype": "numeric",
        "mandatory": False,
        "required_by": ["validation"],
    },
    "loan_status": {
        "semantic": "Current status of the loan such as Active, Closed, NPA, Written Off",
        "possible_names": [
            "loan_status", "status", "account_status", "loan_state",
            "current_status", "facility_status", "contract_status",
        ],
        "dtype": "category",
        "mandatory": True,
        "required_by": ["M1", "M2"],
    },
    "branch_state": {
        "semantic": "State or region where the loan was originated or serviced",
        "possible_names": [
            "branch_state", "state", "region", "branch_region",
            "loan_state", "origination_state", "current_address_state",
            "current_state", "borrower_state",
        ],
        "dtype": "category",
        "mandatory": False,
        "required_by": ["filters"],
    },
    "branch_city": {
        "semantic": "City where the loan was originated or serviced",
        "possible_names": [
            "branch_city", "city", "branch_name", "loan_city",
            "origination_city", "current_address_city", "current_city",
            "borrower_city", "branch_location",
        ],
        "dtype": "category",
        "mandatory": False,
        "required_by": ["filters"],
    },
    "current_pos": {
        "semantic": "Current principal outstanding or unpaid principal balance at latest snapshot",
        "possible_names": [
            "current_outstanding_principal", "current_outstanding_principal_INR",
            "outstanding_principal", "pos", "principal_outstanding",
            "current_balance", "outstanding_balance", "principal_balance",
            "current_pos", "balance_outstanding", "net_outstanding",
        ],
        "dtype": "numeric",
        "mandatory": True,
        "required_by": ["M1", "M2"],
        "derivation": [
            {"method": "formula", "formula": "disbursed_amount - cumulative_principal_collected", "needs": ["disbursed_amount"]},
        ],
    },
    "current_dpd": {
        "semantic": "Current Days Past Due as a number at latest snapshot",
        "possible_names": [
            "current_dpd", "dpd", "days_past_due", "dpd_days",
            "overdue_days", "current_days_past_due", "delinquency_days",
        ],
        "dtype": "integer",
        "mandatory": False,
        "required_by": ["M2"],
    },
    "current_dpd_bucket": {
        "semantic": "DPD bucket label at latest snapshot like Current or DPD 1-30 or NPA",
        "possible_names": [
            "current_dpd_bucket", "dpd_bucket", "dpd_band",
            "delinquency_bucket", "dpd_category", "bucket",
            "asset_classification", "current_bucket", "overdue_bucket",
        ],
        "dtype": "category",
        "mandatory": True,
        "required_by": ["M2"],
        "derivation": [
            {"method": "from_dpd_numeric", "source": "current_dpd"},
        ],
    },
    "npa_date": {
        "semantic": "Date when the loan was classified as NPA",
        "possible_names": [
            "npa_date", "npa_dt", "npa_classification_date",
            "default_date", "npa_start_date",
        ],
        "dtype": "date",
        "mandatory": False,
        "required_by": [],
    },
    "cumulative_principal_collected_loan": {
        "semantic": "Total cumulative principal collected for this loan from the loan file",
        "possible_names": [
            "cumulative_principal_collected", "total_principal_paid_INR",
            "total_principal_paid", "cum_principal_paid",
            "total_principal_collected",
        ],
        "dtype": "numeric",
        "mandatory": False,
        "required_by": ["M9"],
    },
}


TRANSACTION_FIELDS: dict[str, dict] = {
    "txn_loan_id": {
        "semantic": "Foreign key linking transaction record to a loan",
        "possible_names": [
            "loan_id", "loan_no", "account_id", "facility_id",
            "loan_account_number", "account_no", "loan_number",
            "agreement_id", "contract_id",
        ],
        "dtype": "string",
        "mandatory": True,
        "required_by": ["M3", "M4", "M5", "M6", "M7", "M8", "M9"],
    },
    "observation_month": {
        "semantic": "The month this transaction or schedule record belongs to for time-series grouping",
        "possible_names": [
            "observation_month_year", "observation_month", "period",
            "reporting_month", "statement_month", "emi_month",
            "payment_month", "month_year",
        ],
        "dtype": "string",
        "mandatory": False,
        "required_by": ["M3", "M4", "M5", "M6", "M7", "M8", "M9"],
        "derivation": [
            {"method": "extract_month", "source": "due_date"},
            {"method": "extract_month", "source": "actual_payment_date"},
        ],
    },
    "instalment_number": {
        "semantic": "Sequential EMI instalment number starting from 1",
        "possible_names": [
            "installment_number", "instalment_number", "emi_no",
            "emi_number", "installment_no", "schedule_no",
            "sequence_number", "inst_no", "period_number",
        ],
        "dtype": "integer",
        "mandatory": False,
        "required_by": ["validation"],
    },
    "due_date": {
        "semantic": "Scheduled EMI payment due date",
        "possible_names": [
            "due_date", "scheduled_due_date", "emi_due_date",
            "payment_due_date", "instalment_due_date", "due_dt",
            "schedule_date", "repayment_date",
        ],
        "dtype": "date",
        "mandatory": True,
        "required_by": ["M3", "M4"],
    },
    "opening_pos": {
        "semantic": "Principal outstanding at the start of this period or instalment",
        "possible_names": [
            "opening_outstanding_principal", "opening_principal_balance_INR",
            "opening_balance", "opening_pos", "begin_balance",
            "balance_bf", "start_balance", "opening_principal",
        ],
        "dtype": "numeric",
        "mandatory": False,
        "required_by": ["validation"],
    },
    "scheduled_emi": {
        "semantic": "Total EMI amount scheduled for this instalment",
        "possible_names": [
            "scheduled_emi", "emi_amount_scheduled_INR", "emi_amount",
            "emi_due", "scheduled_instalment", "instalment_amount",
            "emi_scheduled", "total_emi_due", "expected_payment",
        ],
        "dtype": "numeric",
        "mandatory": True,
        "required_by": ["M3", "M4"],
        "derivation": [
            {"method": "formula", "formula": "scheduled_principal + scheduled_interest", "needs": ["scheduled_principal", "scheduled_interest"]},
        ],
    },
    "scheduled_principal": {
        "semantic": "Principal component of the scheduled EMI",
        "possible_names": [
            "scheduled_principal", "principal_component_scheduled",
            "principal_component", "principal_due",
            "scheduled_principal_component", "emi_principal",
            "principal_scheduled",
        ],
        "dtype": "numeric",
        "mandatory": False,
        "required_by": ["M3"],
    },
    "scheduled_interest": {
        "semantic": "Interest component of the scheduled EMI",
        "possible_names": [
            "scheduled_interest", "interest_component_scheduled",
            "interest_component", "interest_due",
            "scheduled_interest_component", "emi_interest",
            "interest_scheduled",
        ],
        "dtype": "numeric",
        "mandatory": False,
        "required_by": ["M1"],
    },
    "actual_payment_date": {
        "semantic": "Date when the actual payment was received from borrower",
        "possible_names": [
            "actual_payment_date", "payment_date", "txn_date",
            "transaction_date", "receipt_date", "collection_date",
            "value_date", "paid_date", "actual_date",
        ],
        "dtype": "date",
        "mandatory": False,
        "required_by": [],
    },
    "actual_total_paid": {
        "semantic": "Total amount actually paid for this instalment including all components",
        "possible_names": [
            "actual_total_paid", "actual_amount_paid_INR", "amount_paid",
            "paid_amount", "receipt_amount", "collected_amount",
            "actual_paid", "total_paid", "amount_received",
            "payment_amount",
        ],
        "dtype": "numeric",
        "mandatory": False,
        "required_by": ["M3", "M4"],
    },
    "actual_principal_paid": {
        "semantic": "Principal portion of the actual payment received",
        "possible_names": [
            "actual_principal_paid", "principal_paid_INR", "principal_paid",
            "principal_collected", "principal_received", "actual_principal",
            "principal_repaid", "prin_paid",
        ],
        "dtype": "numeric",
        "mandatory": True,
        "required_by": ["M3", "M4", "M9"],
        "derivation": [
            {"method": "formula", "formula": "actual_total_paid - actual_interest_paid", "needs": ["actual_total_paid", "actual_interest_paid"]},
            {"method": "formula", "formula": "opening_pos - closing_pos", "needs": ["opening_pos", "closing_pos"]},
        ],
    },
    "actual_interest_paid": {
        "semantic": "Interest portion of the actual payment received",
        "possible_names": [
            "actual_interest_paid", "interest_paid_INR", "interest_paid",
            "interest_collected", "interest_received", "actual_interest",
            "interest_repaid", "int_paid",
        ],
        "dtype": "numeric",
        "mandatory": True,
        "required_by": ["M3", "M4"],
        "derivation": [
            {"method": "formula", "formula": "actual_total_paid - actual_principal_paid", "needs": ["actual_total_paid", "actual_principal_paid"]},
        ],
    },
    "txn_dpd": {
        "semantic": "Days Past Due at this instalment or observation point as a number",
        "possible_names": [
            "days_past_due", "dpd", "dpd_days", "overdue_days",
            "current_dpd",
        ],
        "dtype": "integer",
        "mandatory": False,
        "required_by": ["M5", "M6", "M7", "M8"],
    },
    "txn_dpd_bucket": {
        "semantic": "DPD bucket label at this instalment or observation point",
        "possible_names": [
            "dpd_bucket", "dpd_band", "delinquency_bucket", "bucket",
            "dpd_category", "overdue_bucket",
        ],
        "dtype": "category",
        "mandatory": True,
        "required_by": ["M4", "M5", "M6", "M7", "M8"],
        "derivation": [
            {"method": "from_dpd_numeric", "source": "txn_dpd"},
        ],
    },
    "closing_pos": {
        "semantic": "Principal outstanding at end of this period after payment applied",
        "possible_names": [
            "closing_outstanding_principal", "actual_outstanding_principal_INR",
            "closing_balance", "closing_pos", "end_balance",
            "balance_cf", "outstanding_after_payment",
            "remaining_principal",
        ],
        "dtype": "numeric",
        "mandatory": True,
        "required_by": ["M5", "M6"],
        "derivation": [
            {"method": "formula", "formula": "opening_pos - actual_principal_paid", "needs": ["opening_pos", "actual_principal_paid"]},
        ],
    },
    "cumulative_principal_collected": {
        "semantic": "Running total of principal collected from loan inception to this period",
        "possible_names": [
            "cumulative_principal_collected", "cumulative_principal_paid_INR",
            "cum_principal", "total_principal_paid",
            "total_principal_paid_INR", "cumulative_principal",
            "running_principal",
        ],
        "dtype": "numeric",
        "mandatory": False,
        "required_by": ["M9"],
        "derivation": [
            {"method": "cumsum", "source": "actual_principal_paid"},
        ],
    },
    "cumulative_interest_collected": {
        "semantic": "Running total of interest collected from inception to this period",
        "possible_names": [
            "cumulative_interest_collected", "cumulative_interest_paid_INR",
            "cum_interest", "total_interest_paid",
            "total_interest_paid_INR", "cumulative_interest",
            "running_interest",
        ],
        "dtype": "numeric",
        "mandatory": False,
        "required_by": ["M1"],
    },
    "overdue_principal": {
        "semantic": "Principal amount currently overdue and unpaid",
        "possible_names": [
            "overdue_principal", "overdue_principal_INR",
            "principal_overdue", "past_due_principal",
            "arrears_principal", "outstanding_overdue",
        ],
        "dtype": "numeric",
        "mandatory": False,
        "required_by": [],
    },
    "overdue_interest": {
        "semantic": "Interest amount currently overdue, accrued but uncollected",
        "possible_names": [
            "overdue_interest", "overdue_interest_INR",
            "interest_overdue", "past_due_interest",
            "arrears_interest", "accrued_interest_uncollected",
        ],
        "dtype": "numeric",
        "mandatory": False,
        "required_by": ["M1"],
    },
    "bounce_flag": {
        "semantic": "Whether the payment attempt bounced or failed, yes or no",
        "possible_names": [
            "bounce_flag", "payment_bounce", "ecs_bounce",
            "nach_bounce", "mandate_bounce", "bounce_indicator",
            "payment_failed", "dishonour_flag",
        ],
        "dtype": "category",
        "mandatory": False,
        "required_by": [],
    },
    "payment_status": {
        "semantic": "Status of this instalment payment such as Paid Unpaid or Partial",
        "possible_names": [
            "payment_status", "emi_status", "instalment_status",
            "payment_outcome", "collection_status",
        ],
        "dtype": "category",
        "mandatory": False,
        "required_by": [],
    },
    "penalty_charges": {
        "semantic": "Penalty or penal charges levied for late payment",
        "possible_names": [
            "penalty_charges_levied", "penalty_charges", "penal_charges",
            "late_fee", "penalty_amount", "penal_interest",
            "bounce_charges_INR", "bounce_charges",
            "fees_and_charges_paid_INR", "fees_and_charges_paid",
        ],
        "dtype": "numeric",
        "mandatory": False,
        "required_by": ["M3"],
    },
}


# ── Metric requirements map ───────────────────────────────────────────────
# For each metric: what canonical fields are MANDATORY vs OPTIONAL

METRIC_REQUIREMENTS: dict[str, dict] = {
    "M1": {
        "name": "Portfolio Summary Table",
        "mandatory_loan": ["loan_id", "current_pos", "loan_status", "interest_rate", "maturity_date"],
        "optional_loan": ["tenor_months", "disbursement_date"],
        "mandatory_txn": [],
        "optional_txn": ["overdue_interest", "scheduled_interest", "actual_interest_paid"],
        "description": "KPI cards: POS, Interest Outstanding, Active Count, Wtd Avg Rate, Wtd Avg Tenor",
    },
    "M2": {
        "name": "POS Distribution by DPD Bucket",
        "mandatory_loan": ["loan_id", "current_pos", "current_dpd_bucket", "loan_status"],
        "optional_loan": ["current_dpd"],
        "mandatory_txn": [],
        "optional_txn": [],
        "description": "Bar chart of POS across 5 DPD buckets",
    },
    "M3": {
        "name": "Overall Collections Efficiency — Time Series",
        "mandatory_loan": [],
        "optional_loan": [],
        "mandatory_txn": ["txn_loan_id", "scheduled_emi", "actual_principal_paid", "actual_interest_paid"],
        "optional_txn": ["observation_month", "due_date", "actual_total_paid", "penalty_charges"],
        "description": "EMI Due vs Amount Collected monthly/quarterly with CE% line",
    },
    "M4": {
        "name": "Collections Efficiency by DPD Bucket",
        "mandatory_loan": [],
        "optional_loan": [],
        "mandatory_txn": ["txn_loan_id", "scheduled_emi", "actual_principal_paid", "actual_interest_paid", "txn_dpd_bucket"],
        "optional_txn": ["observation_month", "due_date"],
        "description": "CE% per DPD bucket for user-selected month",
    },
    "M5": {
        "name": "POS Transition Matrix (INR Amount)",
        "mandatory_loan": [],
        "optional_loan": [],
        "mandatory_txn": ["txn_loan_id", "txn_dpd_bucket", "closing_pos"],
        "optional_txn": ["observation_month", "due_date"],
        "description": "5x5 heatmap of POS flow between DPD buckets",
    },
    "M6": {
        "name": "POS Transition Matrix (Percentage)",
        "mandatory_loan": [],
        "optional_loan": [],
        "mandatory_txn": ["txn_loan_id", "txn_dpd_bucket", "closing_pos"],
        "optional_txn": ["observation_month", "due_date"],
        "description": "5x5 heatmap of POS flow as % (rows sum to 100%)",
    },
    "M7": {
        "name": "Loan Count Transition Matrix (Count)",
        "mandatory_loan": [],
        "optional_loan": [],
        "mandatory_txn": ["txn_loan_id", "txn_dpd_bucket"],
        "optional_txn": ["observation_month", "due_date"],
        "description": "5x5 heatmap of loan count migration",
    },
    "M8": {
        "name": "Loan Count Transition Matrix (Percentage)",
        "mandatory_loan": [],
        "optional_loan": [],
        "mandatory_txn": ["txn_loan_id", "txn_dpd_bucket"],
        "optional_txn": ["observation_month", "due_date"],
        "description": "5x5 heatmap of loan count migration as %",
    },
    "M9": {
        "name": "Principal Repayment Rate by Cohort",
        "mandatory_loan": ["loan_id", "disbursement_date", "disbursed_amount"],
        "optional_loan": [],
        "mandatory_txn": ["txn_loan_id", "actual_principal_paid"],
        "optional_txn": ["observation_month", "due_date", "cumulative_principal_collected"],
        "description": "Multi-line vintage chart: cumulative repayment % by cohort × MOB",
    },
}
