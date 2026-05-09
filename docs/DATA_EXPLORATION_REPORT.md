# Data Exploration Report — Both Loan Tapes

## 1. Dataset Overview

| Property | Large Dataset (Loan Tape 1) | Medium Dataset (Loan Tape 2) |
|----------|----------------------------|------------------------------|
| **Files** | 3 CSVs (consolidated) | 5 CSVs (split by domain) |
| **Total Loans** | 70,000 | 84,278 |
| **Active Loans** | 59,826 | 65,848 |
| **Closed Loans** | 8,793 | 14,320 |
| **NPA/Written Off** | 1,381 | 4,110 |
| **Transaction Rows** | 1,730,587 | 2,374,572 |
| **Date Range** | Jan 2021 – Mar 2026 | Jan 2017 – Mar 2026 |
| **Snapshot Date** | last_observation_month (varies per loan) | portfolio_observation_date = 2026-03-31 |
| **POS (Total)** | ₹41,541 Cr | ₹8,193 Cr |
| **Products** | 6 types | 6 types (same) |
| **States** | 12 | 19 |
| **Cities** | 96 | varies |

---

## 2. File Structure Comparison

### Large Dataset — 3 Files (Consolidated)
```
borrowers.csv      → 65,000 rows × 56 columns (Borrower + Credit Bureau)
loans.csv          → 70,000 rows × 57 columns (Loan + Collateral + Current Status)
transactions.csv   → 1,730,587 rows × 40 columns (Schedule + Payment + Collections)
```

### Medium Dataset — 5 Files (Split by Domain)
```
01_Borrowers.csv                    → 84,278 rows × 63 columns (Borrower + Bureau + KYC)
02_Collateral.csv                   → 84,278 rows × 43 columns (Vehicle + Property details)
03_Loan_Facilities.csv              → 84,278 rows × 52 columns (Loan + Current Status)
04_Payment_Schedule_Transactions.csv → 2,374,572 rows × 23 columns (Schedule + Payment)
05_Collections.csv                  → 198,341 rows × 32 columns (Collection activity)
```

**Key Structural Difference**: The Large dataset merges collateral info INTO loans.csv, and merges collections info INTO transactions.csv. The Medium dataset keeps them in separate files.

---

## 3. Critical Schema Differences

### 3.1 DPD Bucket Labels (MUST NORMALIZE)

| Standard Bucket | Large Dataset Label | Medium Dataset Label |
|----------------|--------------------|--------------------|
| Current (0 DPD) | `Current (DPD 0)` | `Current` |
| DPD 1–30 | `SMA-0 (DPD 1-30)` | `DPD 01-30` |
| DPD 31–60 | `SMA-1 (DPD 31-60)` | `DPD 31-60` |
| DPD 61–90 | `SMA-2 (DPD 61-90)` | `DPD 61-90` |
| DPD 90+ | `NPA (DPD 90+)` | `DPD 91-180` + `DPD 181+` ← **TWO buckets** |

**Action Required**: Medium dataset splits 90+ into two sub-buckets. For the 5-bucket standard model, merge `DPD 91-180` and `DPD 181+` into a single `DPD 90+` bucket.

### 3.2 Column Name Mapping

| Canonical Field | Large Dataset | Medium Dataset |
|----------------|---------------|----------------|
| **loan_id** | `loan_id` | `loan_id` |
| **borrower_id** | `borrower_id` | `borrower_id` |
| **product_type** | `product_type` | `product_type` |
| **disbursement_date** | `disbursement_date` | `disbursement_date` |
| **maturity_date** | `maturity_date` | `maturity_date` |
| **sanctioned_amount** | `sanctioned_amount` | `principal_sanctioned_INR` |
| **disbursed_amount** | `disbursed_amount` | `principal_disbursed_INR` |
| **interest_rate** | `annual_interest_rate_pct` | `annual_interest_rate_pct` |
| **tenor_months** | `tenor_months` | `tenor_months` |
| **emi_amount** | `emi_amount` | `emi_amount_INR` |
| **loan_status** | `loan_status` | `loan_status` |
| **current_pos** | `current_outstanding_principal` | `current_outstanding_principal_INR` |
| **current_dpd** | `current_dpd` | `current_dpd` |
| **dpd_bucket** | `current_dpd_bucket` | `dpd_bucket` |
| **branch_state** | `branch_state` | `branch_state` |
| **branch_city** | `branch_city` | *(via branch_code/branch_name)* |
| **npa_date** | `npa_date` | `npa_date` |
| **region (filter)** | `branch_state` | `branch_state` |
| **city (filter)** | `branch_city` | `branch_name` (extract city) |

### 3.3 Transaction Column Mapping

| Canonical Field | Large (transactions.csv) | Medium (04_Payment_Schedule.csv) |
|----------------|--------------------------|----------------------------------|
| **observation_month** | `observation_month_year` | *(derived from due_date)* |
| **instalment_number** | `installment_number` | `installment_number` |
| **due_date** | `scheduled_due_date` | `due_date` |
| **opening_pos** | `opening_outstanding_principal` | `opening_principal_balance_INR` |
| **scheduled_emi** | `scheduled_emi` | `emi_amount_scheduled_INR` |
| **scheduled_principal** | `scheduled_principal` | `principal_component_scheduled` |
| **scheduled_interest** | `scheduled_interest` | `interest_component_scheduled` |
| **actual_payment_date** | `actual_payment_date` | `actual_payment_date` |
| **actual_total_paid** | `actual_total_paid` | `actual_amount_paid_INR` |
| **actual_principal_paid** | `actual_principal_paid` | `principal_paid_INR` |
| **actual_interest_paid** | `actual_interest_paid` | `interest_paid_INR` |
| **payment_mode** | `payment_mode` | *(not in schedule, in loans: repayment_mode)* |
| **penalty_charges** | `penalty_charges_levied` | *(not present)* |
| **days_past_due** | `days_past_due` | `days_past_due` |
| **dpd_bucket** | `dpd_bucket` | `dpd_bucket` |
| **closing_pos** | `closing_outstanding_principal` | `actual_outstanding_principal_INR` |
| **cumulative_principal** | `cumulative_principal_collected` | `cumulative_principal_paid_INR` |
| **cumulative_interest** | `cumulative_interest_collected` | `cumulative_interest_paid_INR` |
| **bounce_flag** | *(not explicit, infer from payment)* | `bounce_flag` (Y/N) |
| **bounce_charges** | *(not present)* | `bounce_charges_INR` |
| **payment_status** | *(not present, infer)* | `payment_status` (Paid/Unpaid/Partial/Moratorium) |

---

## 4. Product Types (Identical Across Both)

| Product Type | Large Count | Medium Count |
|-------------|-------------|-------------|
| Commercial Vehicle | major | 46,303 |
| Other Vehicle Finance | present | 10,056 |
| Loan Against Property | present | 8,498 |
| Housing Finance | present | 8,385 |
| Construction Equipment | present | 6,742 |
| Tractor Finance | present | 4,294 |

---

## 5. Loan Status Values

| Status | Large Dataset | Medium Dataset |
|--------|--------------|---------------|
| Active | `Active` | `Active` |
| Closed | `Closed` | `Closed` |
| NPA | `NPA` | `NPA` |
| Written Off | `Written Off` | `Written Off` |

---

## 6. Metric-to-CSV Mapping

### LARGE DATASET (3 files)

| Metric | Primary Source | Key Columns Used |
|--------|---------------|-----------------|
| **M1: Portfolio Summary** | `loans.csv` | `current_outstanding_principal`, `annual_interest_rate_pct`, `maturity_date`, `loan_status` |
| **M2: POS by DPD Bucket** | `loans.csv` | `current_outstanding_principal`, `current_dpd_bucket` |
| **M3: Collections Efficiency (Time Series)** | `transactions.csv` | `observation_month_year`, `scheduled_emi`, `actual_total_paid`, `actual_principal_paid`, `actual_interest_paid` |
| **M4: Collections Efficiency by DPD** | `transactions.csv` | `observation_month_year`, `dpd_bucket` (prev month), `scheduled_emi`, `actual_total_paid` |
| **M5: POS Transition Matrix (INR)** | `transactions.csv` | `loan_id`, `observation_month_year`, `dpd_bucket`, `closing_outstanding_principal` |
| **M6: POS Transition Matrix (%)** | Same as M5 | Same as M5 |
| **M7: Loan Count Transition Matrix** | `transactions.csv` | `loan_id`, `observation_month_year`, `dpd_bucket` |
| **M8: Loan Count Transition (%)** | Same as M7 | Same as M7 |
| **M9: Repayment Rate by Cohort** | `loans.csv` + `transactions.csv` | `disbursement_date` (cohort), `disbursed_amount`, `cumulative_principal_collected`, `observation_month_year` |
| **Interest Outstanding** | `transactions.csv` | `overdue_interest` OR derive from schedule vs actual |
| **Filters (Product)** | `loans.csv` → join to `transactions.csv` | `product_type` |
| **Filters (Region/City)** | `loans.csv` | `branch_state`, `branch_city` |
| **Collateral data** | `loans.csv` (embedded) | `collateral_type`, `asset_valuation_at_origination`, `ltv_at_origination`, `current_ltv` |
| **Borrower demographics** | `borrowers.csv` | `gender`, `employment_type`, `cibil_score`, city/state |

### MEDIUM DATASET (5 files)

| Metric | Primary Source | Key Columns Used |
|--------|---------------|-----------------|
| **M1: Portfolio Summary** | `03_Loan_Facilities.csv` | `current_outstanding_principal_INR`, `annual_interest_rate_pct`, `maturity_date`, `loan_status` |
| **M2: POS by DPD Bucket** | `03_Loan_Facilities.csv` | `current_outstanding_principal_INR`, `dpd_bucket` |
| **M3: Collections Efficiency (Time Series)** | `04_Payment_Schedule.csv` | `due_date`, `emi_amount_scheduled_INR`, `actual_amount_paid_INR`, `principal_paid_INR`, `interest_paid_INR` |
| **M4: Collections Efficiency by DPD** | `04_Payment_Schedule.csv` | `due_date`, `dpd_bucket` (prev period), `emi_amount_scheduled_INR`, `actual_amount_paid_INR` |
| **M5: POS Transition Matrix (INR)** | `04_Payment_Schedule.csv` | `loan_id`, `due_date`, `dpd_bucket`, `actual_outstanding_principal_INR` |
| **M6: POS Transition Matrix (%)** | Same as M5 | Same as M5 |
| **M7: Loan Count Transition Matrix** | `04_Payment_Schedule.csv` | `loan_id`, `due_date`, `dpd_bucket` |
| **M8: Loan Count Transition (%)** | Same as M7 | Same as M7 |
| **M9: Repayment Rate by Cohort** | `03_Loan_Facilities.csv` + `04_Payment_Schedule.csv` | `disbursement_date`, `principal_disbursed_INR`, `cumulative_principal_paid_INR`, `due_date` |
| **Bounce Rate** | `04_Payment_Schedule.csv` | `bounce_flag`, `bounce_charges_INR` |
| **Filters (Product)** | `03_Loan_Facilities.csv` → join | `product_type` |
| **Filters (Region/City)** | `03_Loan_Facilities.csv` | `branch_state`, `branch_name` |
| **Collateral data** | `02_Collateral.csv` | `collateral_type`, `collateral_value_INR`, `vehicle_*`, `property_*` |
| **Collections activity** | `05_Collections.csv` | `collection_stage`, `amount_collected_this_month_INR`, `dpd_bucket` |
| **Borrower demographics** | `01_Borrowers.csv` | `gender`, `employment_type`, `cibil_score`, `current_city`, `current_state` |

---

## 7. How to Compute Each Metric — Source Details

### Metric 1: Portfolio Summary Table
**What we need**: POS, Interest Outstanding, Active Count, Weighted Avg Rate, Weighted Avg Tenor

| Field | Large Dataset Source | Medium Dataset Source |
|-------|---------------------|---------------------|
| POS | `loans.csv` → `SUM(current_outstanding_principal)` WHERE `loan_status='Active'` | `03_Loan_Facilities.csv` → `SUM(current_outstanding_principal_INR)` WHERE `loan_status='Active'` |
| Interest Outstanding | `transactions.csv` → latest month → `SUM(overdue_interest)` | Derive: `SUM(cumulative_interest_scheduled - cumulative_interest_paid)` from `04_Payment_Schedule.csv` |
| Active Count | `loans.csv` → `COUNT(*)` WHERE `loan_status='Active'` | `03_Loan_Facilities.csv` → `COUNT(*)` WHERE `loan_status='Active'` |
| Weighted Rate | `loans.csv` → `SUM(rate × POS) / SUM(POS)` | `03_Loan_Facilities.csv` → same formula with `_INR` suffix |
| Weighted Tenor | `loans.csv` → `SUM(remaining_months × POS) / SUM(POS)` | Same |
| MoM Delta | Compare latest vs prior month from `transactions.csv` | Compare from `04_Payment_Schedule.csv` |

### Metric 2: POS Distribution by DPD Bucket
| Large | Medium |
|-------|--------|
| `loans.csv` → GROUP BY `current_dpd_bucket`, SUM `current_outstanding_principal` | `03_Loan_Facilities.csv` → GROUP BY `dpd_bucket`, SUM `current_outstanding_principal_INR`. **Merge DPD 91-180 + DPD 181+ → DPD 90+** |

### Metric 3: Collections Efficiency (Time Series)
| Large | Medium |
|-------|--------|
| `transactions.csv` → GROUP BY `observation_month_year`: SUM `scheduled_emi` (EMI Due), SUM `actual_principal_paid + actual_interest_paid` (Collected, excl penalties) | `04_Payment_Schedule.csv` → derive month from `due_date`, GROUP BY month: SUM `emi_amount_scheduled_INR`, SUM `principal_paid_INR + interest_paid_INR` |

### Metric 4: Collections Efficiency by DPD
- Need **prior month-end DPD bucket** for each loan
- Large: From `transactions.csv`, for month M, get each loan's DPD bucket from month M-1, then aggregate month M's EMI Due vs Collected by that prior bucket
- Medium: Same from `04_Payment_Schedule.csv`, use prior month's `dpd_bucket`

### Metrics 5-8: Transition Matrices
- Both datasets: For each loan, get DPD bucket at month-end T-1 and T
- Large: `transactions.csv` — extract last record per `loan_id` per `observation_month_year`, use `dpd_bucket` and `closing_outstanding_principal`
- Medium: `04_Payment_Schedule.csv` — extract last record per `loan_id` per month (from `due_date`), use `dpd_bucket` and `actual_outstanding_principal_INR`
- Build pivot: rows = from_bucket, cols = to_bucket, values = SUM(POS) or COUNT(loan_id)

### Metric 9: Repayment Rate by Cohort
- **Cohort** = disbursement month from loans file
- **MOB** = months since disbursement
- Large: Join `loans.csv` (for `disbursement_date`, `disbursed_amount`) with `transactions.csv` (for `cumulative_principal_collected` at each month)
- Medium: Join `03_Loan_Facilities.csv` with `04_Payment_Schedule.csv` (for `cumulative_principal_paid_INR`)

---

## 8. Data Available ONLY in One Dataset

### Medium Has, Large Doesn't:
| Data | Medium Source | Notes |
|------|-------------|-------|
| **Separate collateral file** | `02_Collateral.csv` | Vehicle details (make, model, year, RTO), property details (area, market value) |
| **Bounce flag** | `04_Payment_Schedule.csv` → `bounce_flag` | Direct Y/N flag per instalment |
| **Bounce charges** | `04_Payment_Schedule.csv` → `bounce_charges_INR` | Amount per bounce |
| **Payment status** | `04_Payment_Schedule.csv` → `payment_status` | Paid/Unpaid/Partial/Moratorium Deferred/Paid (Foreclosure) |
| **COVID moratorium** | `04_Payment_Schedule.csv` → `covid_moratorium_applied` | Y/N flag |
| **Dedicated collections file** | `05_Collections.csv` | Detailed collection activity log |
| **Equifax score** | `01_Borrowers.csv` → `equifax_score` | Second bureau score |
| **KYC details** | `01_Borrowers.csv` → `kyc_status`, `kyc_date`, `kyc_mode` | KYC compliance |
| **Foreclosure flag/date** | `03_Loan_Facilities.csv` | Direct foreclosure tracking |
| **Write-off date** | `03_Loan_Facilities.csv` | Direct write-off date |
| **NACH status** | `03_Loan_Facilities.csv` → `nach_status` | Mandate status |
| **Total bounces** | `03_Loan_Facilities.csv` → `total_bounces_to_date` | Aggregate bounce count |
| **Customer segment** | `01_Borrowers.csv` → `customer_segment` | Prime/Near-Prime/Sub-Prime |
| **Risk category** | `01_Borrowers.csv` → `risk_category` | Low/Medium/High Risk |

### Large Has, Medium Doesn't:
| Data | Large Source | Notes |
|------|-------------|-------|
| **Collateral in loans** | `loans.csv` | Embedded: `collateral_type`, `asset_make`, `asset_model`, `current_asset_value`, `current_ltv` |
| **Collections in transactions** | `transactions.csv` | Embedded: `collections_flag`, `collections_channel`, `promise_to_pay_*`, `field_visit_done`, `legal_notice_issued` |
| **IFRS9 stage** | `loans.csv` + `transactions.csv` | Stage 1/2/3 per period |
| **Provision rate & amount** | `loans.csv` + `transactions.csv` | Pre-computed provisioning |
| **Max DPD ever** | `loans.csv` → `max_dpd_ever` | Lifetime worst DPD |
| **DPD episode count** | `loans.csv` → `number_of_dpd_episodes` | How many times loan went delinquent |
| **Observation varies per loan** | `loans.csv` → `last_observation_month` | Different loans may have different latest months |

---

## 9. Data Quality Observations

### Large Dataset
- ✅ No null values in transaction payment fields
- ✅ DPD bucket matches standard 5-bucket model
- ⚠️ `last_observation_month` varies per loan (2026-01, 2026-02, 2026-03) — need to pick a consistent snapshot
- ⚠️ Collateral data is embedded in loans.csv — some columns may be empty for unsecured products
- ⚠️ Interest outstanding not directly available — must derive from `overdue_interest` in transactions

### Medium Dataset
- ✅ No null values in payment schedule fields
- ✅ Clean file separation by domain
- ⚠️ DPD 90+ is split into `DPD 91-180` and `DPD 181+` — **must merge for standard 5-bucket**
- ⚠️ `npa_date` and `write_off_date` have mixed types — needs careful parsing
- ⚠️ 84,278 borrowers = 84,278 collateral = 84,278 loans (1:1:1 relationship, no multi-loan borrowers)
- ⚠️ `portfolio_observation_date` is single value (2026-03-31) — snapshot is fixed
- ✅ Bounce data directly available (`bounce_flag`, `bounce_charges_INR`)
- ✅ Payment status directly available (Paid/Unpaid/Partial/Moratorium)

---

## 10. Normalization Mapping for Schema Discovery Agent

```python
# DPD Bucket Normalization
DPD_BUCKET_MAP = {
    # Large Dataset
    "Current (DPD 0)": "Current",
    "SMA-0 (DPD 1-30)": "DPD 1-30",
    "SMA-1 (DPD 31-60)": "DPD 31-60",
    "SMA-2 (DPD 61-90)": "DPD 61-90",
    "NPA (DPD 90+)": "DPD 90+",
    
    # Medium Dataset
    "Current": "Current",
    "DPD 01-30": "DPD 1-30",
    "DPD 31-60": "DPD 31-60",
    "DPD 61-90": "DPD 61-90",
    "DPD 91-180": "DPD 90+",   # Merge into 90+
    "DPD 181+": "DPD 90+",     # Merge into 90+
}

# Column Name Normalization
COLUMN_MAP_LARGE = {
    "current_outstanding_principal": "pos",
    "annual_interest_rate_pct": "interest_rate",
    "disbursed_amount": "disbursed_amount",
    "sanctioned_amount": "sanctioned_amount",
    "current_dpd_bucket": "dpd_bucket",
    "current_dpd": "dpd",
    "scheduled_emi": "emi_due",
    "actual_principal_paid": "principal_collected",
    "actual_interest_paid": "interest_collected",
    "actual_total_paid": "total_collected",
    "closing_outstanding_principal": "closing_pos",
    "opening_outstanding_principal": "opening_pos",
    "observation_month_year": "snapshot_month",
}

COLUMN_MAP_MEDIUM = {
    "current_outstanding_principal_INR": "pos",
    "annual_interest_rate_pct": "interest_rate",
    "principal_disbursed_INR": "disbursed_amount",
    "principal_sanctioned_INR": "sanctioned_amount",
    "dpd_bucket": "dpd_bucket",
    "current_dpd": "dpd",
    "emi_amount_scheduled_INR": "emi_due",
    "principal_paid_INR": "principal_collected",
    "interest_paid_INR": "interest_collected",
    "actual_amount_paid_INR": "total_collected",
    "actual_outstanding_principal_INR": "closing_pos",
    "opening_principal_balance_INR": "opening_pos",
    # snapshot_month derived from due_date
}
```

---

## 11. Join Keys

### Large Dataset
```
borrowers.csv ──(borrower_id)──▶ loans.csv ──(loan_id)──▶ transactions.csv
```

### Medium Dataset
```
01_Borrowers.csv ──(borrower_id)──▶ 03_Loan_Facilities.csv ──(loan_id)──▶ 04_Payment_Schedule.csv
                                      │                                       
                                      ├──(loan_id)──▶ 02_Collateral.csv      
                                      └──(loan_id)──▶ 05_Collections.csv     
```

---

## 12. Summary: What You CAN and CANNOT Compute

| Metric | Computable from Both? | Notes |
|--------|----------------------|-------|
| M1: Portfolio Summary | ✅ Yes | Interest outstanding needs derivation |
| M2: POS by DPD | ✅ Yes | Normalize bucket labels |
| M3: Collections Efficiency | ✅ Yes | Exclude penalties/charges |
| M4: CE by DPD Bucket | ✅ Yes | Use prior-month bucket |
| M5: POS Transition Matrix (INR) | ✅ Yes | Monthly snapshots from transaction data |
| M6: POS Transition Matrix (%) | ✅ Yes | Derived from M5 |
| M7: Count Transition Matrix | ✅ Yes | Same source as M5 |
| M8: Count Transition (%) | ✅ Yes | Derived from M7 |
| M9: Repayment by Cohort | ✅ Yes | Join loans + transactions |
| Bounce Rate | ⚠️ Medium only | Large has no explicit bounce flag |
| Collections Activity Detail | ⚠️ Different structure | Large: embedded in txns. Medium: separate file |
| Foreclosure Tracking | ⚠️ Medium better | Medium has explicit flag/date |
| IFRS9 Staging | ⚠️ Large only | Large has `ifrs9_stage` per period |
| Provisioning | ⚠️ Large only | Large has `provision_rate_pct`, `provision_amount` |
