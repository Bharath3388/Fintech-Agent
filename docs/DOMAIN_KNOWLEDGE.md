# Loan Portfolio Analytics — Domain Knowledge Documentation

## Table of Contents
1. [Overview](#1-overview)
2. [Core Domain Concepts](#2-core-domain-concepts)
3. [Loan Lifecycle](#3-loan-lifecycle)
4. [Data Domains & Canonical Model](#4-data-domains--canonical-model)
5. [DPD & Asset Classification](#5-dpd--asset-classification)
6. [Portfolio Metrics Deep Dive](#6-portfolio-metrics-deep-dive)
7. [Transition Matrix Theory](#7-transition-matrix-theory)
8. [Vintage & Cohort Analysis](#8-vintage--cohort-analysis)
9. [Collections Analytics](#9-collections-analytics)
10. [Indian NBFC/Lending Regulatory Context](#10-indian-nbfclending-regulatory-context)
11. [Key Formulas & Computation Notes](#11-key-formulas--computation-notes)
12. [Glossary](#12-glossary)

---

## 1. Overview

This document provides comprehensive domain knowledge for building a **Loan Portfolio Analytics Dashboard** as specified by Parse.ai. The system must ingest raw loan tape data (schema-agnostic), compute 17 portfolio metrics, and render interactive visualisations — all orchestrated by an agentic AI architecture.

### Business Context
- **Target users**: Credit, Risk, Collections, and Sales teams at NBFCs and banks
- **Purpose**: Enable business users to build, validate, and productionise predictive models without writing code
- **Key constraint**: The system must handle unknown/varying CSV schemas without manual configuration

---

## 2. Core Domain Concepts

### 2.1 Loan Tape
A **loan tape** is a structured dataset (typically CSV) containing all relevant information about a portfolio of loans. It includes borrower information, loan facility details, payment schedules, actual payment transactions, collateral, and guarantor data. Loan tapes are the standard format for sharing portfolio data between financial institutions, servicers, and analytics platforms.

### 2.2 Principal Outstanding (POS)
The **unpaid principal balance** of a loan at a given point in time (snapshot date).

```
POS = Disbursed Principal − Cumulative Principal Repaid (as at snapshot date)
```

- Excludes accrued interest, fees, and penalties
- This is the PRIMARY exposure measure for most metrics
- Expressed in INR, typically scaled to Crore (1 Crore = 10,000,000 INR)

### 2.3 Active Loan
A loan is **Active** if:
- It has been disbursed
- It has NOT been fully repaid, foreclosed, written off, or otherwise closed

**Important**: Loans in ANY DPD bucket (including 90+) remain Active unless explicitly marked as closed/written-off.

### 2.4 Snapshot Date Convention
- All portfolio metrics are computed at **month-end** snapshot dates
- When computing transitions: start state = prior month-end DPD, end state = current month-end DPD
- A borrower paying on the last day of the month is treated as **Current** for that month

### 2.5 EMI (Equated Monthly Instalment)
The scheduled periodic payment comprising:
- **Principal component**: Portion reducing the outstanding principal
- **Interest component**: Portion covering interest charges

```
Total EMI Due (month) = SUM of all scheduled instalments due across all active loans in that month
```

### 2.6 Disbursement Cohort
A group of loans whose **disbursement date** falls within the same calendar month.
- Labelled by disbursement month (e.g., Apr-2023, May-2023)
- **Month on Book (MOB)** = number of complete calendar months elapsed since disbursement month

---

## 3. Loan Lifecycle

```
┌──────────┐    ┌──────────┐    ┌──────────────┐    ┌─────────────┐
│Application│───▶│ Sanction  │───▶│ Disbursement │───▶│   Active    │
└──────────┘    └──────────┘    └──────────────┘    └──────┬──────┘
                                                           │
                    ┌──────────────────────────────────────┼──────────────────┐
                    │                                      │                  │
                    ▼                                      ▼                  ▼
            ┌──────────────┐                    ┌──────────────┐    ┌──────────────┐
            │   Current    │                    │  Delinquent  │    │  Foreclosed  │
            │   (0 DPD)    │◀──────────────────▶│  (1-90+ DPD) │    │              │
            └──────┬───────┘                    └──────┬───────┘    └──────────────┘
                   │                                   │
                   ▼                                   ▼
            ┌──────────────┐                    ┌──────────────┐
            │  Fully Paid  │                    │  Written Off │
            │   (Closed)   │                    │    (NPA)     │
            └──────────────┘                    └──────────────┘
```

### Key States:
| State | Description |
|-------|-------------|
| **Sanctioned** | Loan approved but not yet disbursed |
| **Disbursed** | Funds released to borrower |
| **Current** | All payments up to date (0 DPD) |
| **Delinquent** | One or more payments overdue (DPD > 0) |
| **NPA** | Non-Performing Asset (DPD > 90 days per RBI norms) |
| **Written Off** | Lender has written off the loan as a loss |
| **Foreclosed** | Borrower has prepaid/closed the loan early |
| **Closed** | Loan fully repaid as per schedule |

---

## 4. Data Domains & Canonical Model

The loan tape data spans 7 domains. Your Schema Discovery Agent must map incoming CSV columns to these canonical domains:

### 4.1 Borrower-Level Information
| Canonical Field | Description | Example Column Names |
|----------------|-------------|---------------------|
| `borrower_id` | Unique borrower identifier | customer_id, cust_id, borrower_no |
| `borrower_name` | Full name | name, customer_name, full_name |
| `date_of_birth` | DOB | dob, birth_date, date_of_birth |
| `gender` | Gender | sex, gender, m_f |
| `address_city` | City | city, borrower_city, location |
| `address_state` | State/Region | state, region, province |
| `address_pincode` | Postal code | pincode, zip, postal_code |
| `phone` | Contact number | mobile, phone_no, contact |
| `email` | Email address | email, email_id |
| `employment_type` | Salaried/Self-employed | emp_type, employment, occupation |
| `annual_income` | Annual income | income, annual_income, yearly_salary |

### 4.2 Borrower Credit History
| Canonical Field | Description | Example Column Names |
|----------------|-------------|---------------------|
| `bureau_score` | Credit score (CIBIL/Experian) | cibil_score, credit_score, bureau_score |
| `bureau_enquiries` | Number of recent enquiries | enquiry_count, num_enquiries |
| `existing_loans_count` | Active loans with other lenders | num_active_loans, existing_obligations |
| `total_outstanding_debt` | Total debt across all lenders | total_debt, outstanding_amt |
| `delinquency_history` | Past delinquency records | dpd_history, past_due_info |
| `credit_utilisation` | Credit utilisation ratio | utilisation_pct, credit_usage |

### 4.3 Loan Facility-Level Data
| Canonical Field | Description | Example Column Names |
|----------------|-------------|---------------------|
| `loan_id` | Unique loan identifier | loan_no, account_id, facility_id |
| `product_type` | Loan product category | product, loan_type, scheme |
| `disbursement_date` | Date funds released | disb_date, disbursement_dt, funded_date |
| `sanctioned_amount` | Approved loan amount | sanction_amt, approved_amount, loan_amount |
| `disbursed_amount` | Actual amount disbursed | disb_amt, disbursed_principal |
| `interest_rate` | Annual interest rate (%) | roi, rate, interest_pct, annual_rate |
| `tenor_months` | Original loan tenor in months | tenure, loan_term, tenor |
| `maturity_date` | Loan end date | maturity_dt, end_date, last_emi_date |
| `loan_status` | Current status | status, account_status, loan_state |
| `emi_amount` | Monthly instalment amount | emi, monthly_payment, instalment |

### 4.4 Payment Schedule (Amortisation)
| Canonical Field | Description | Example Column Names |
|----------------|-------------|---------------------|
| `loan_id` | FK to loan facility | loan_no, account_id |
| `instalment_number` | EMI sequence number | emi_no, instalment_seq |
| `due_date` | Scheduled payment date | emi_due_date, payment_due_dt |
| `emi_due_amount` | Total EMI due | emi_amount, instalment_due |
| `principal_component` | Principal portion of EMI | prin_component, scheduled_principal |
| `interest_component` | Interest portion of EMI | int_component, scheduled_interest |
| `opening_balance` | POS before this instalment | opening_pos, balance_before |
| `closing_balance` | POS after this instalment (if paid) | closing_pos, balance_after |

### 4.5 Payment Transaction Data
| Canonical Field | Description | Example Column Names |
|----------------|-------------|---------------------|
| `loan_id` | FK to loan facility | loan_no, account_id |
| `transaction_date` | Actual payment date | payment_date, txn_date, receipt_date |
| `amount_received` | Total amount received | paid_amount, receipt_amt, collection |
| `principal_collected` | Principal portion collected | principal_paid, prin_received |
| `interest_collected` | Interest portion collected | interest_paid, int_received |
| `charges_collected` | Penalties/fees collected | penalty, charges, fees_collected |
| `payment_mode` | Method of payment | mode, payment_method, channel |

### 4.6 Collateral-Level Data
| Canonical Field | Description | Example Column Names |
|----------------|-------------|---------------------|
| `loan_id` | FK to loan facility | loan_no, account_id |
| `collateral_type` | Type of security | security_type, asset_type, collateral_category |
| `collateral_value` | Assessed value | security_value, asset_value, valuation |
| `valuation_date` | Date of assessment | valuation_dt, assessment_date |
| `ltv_ratio` | Loan-to-Value ratio | ltv, loan_to_value |

### 4.7 Guarantor-Level Data
| Canonical Field | Description | Example Column Names |
|----------------|-------------|---------------------|
| `loan_id` | FK to loan facility | loan_no, account_id |
| `guarantor_name` | Guarantor full name | guarantor, guar_name |
| `guarantor_income` | Guarantor annual income | guar_income, guarantor_salary |
| `guarantor_bureau_score` | Guarantor credit score | guar_cibil, guarantor_score |

---

## 5. DPD & Asset Classification

### 5.1 Days Past Due (DPD) Calculation

**DPD** = Number of calendar days elapsed since the **earliest unpaid instalment** was due, assessed at each month-end snapshot date.

```python
# Pseudocode for DPD calculation
def calculate_dpd(loan, snapshot_date):
    unpaid_instalments = get_unpaid_instalments(loan, up_to=snapshot_date)
    if not unpaid_instalments:
        return 0  # Current
    earliest_unpaid_due_date = min(inst.due_date for inst in unpaid_instalments)
    dpd = (snapshot_date - earliest_unpaid_due_date).days
    return max(0, dpd)
```

### 5.2 Standard DPD Bucket Definitions

| Bucket | DPD Range | RBI Classification | Risk Level | Colour Code |
|--------|-----------|-------------------|------------|-------------|
| **Current** | 0 days | Standard | Low | 🟢 Green |
| **DPD 1–30** | 1–30 days | Special Mention / Standard Watch | Moderate | 🟡 Amber |
| **DPD 31–60** | 31–60 days | Sub-Standard | High | 🟠 Orange |
| **DPD 61–90** | 61–90 days | Sub-Standard / Doubtful | Very High | 🟠 Deep Orange |
| **DPD 90+** | > 90 days | Non-Performing (NPL/NPA) / Loss | Critical | 🔴 Red |

### 5.3 RBI Asset Classification (Indian Context)

| Category | Criteria | Provisioning |
|----------|----------|-------------|
| **Standard** | Current, no overdue | 0.40% |
| **Sub-Standard** | NPA for ≤ 12 months | 15% (unsecured: 25%) |
| **Doubtful** | NPA for > 12 months | 25-100% depending on period |
| **Loss** | Identified as uncollectible | 100% |

### 5.4 Key Rules
- DPD is ALWAYS assessed at **month-end**
- A borrower paying on the **last day of the month** is treated as Current
- Partial payments: If payment is less than EMI due, the shortfall accumulates
- **Curing**: A loan can move from delinquent back to Current if all overdue amounts are paid

---

## 6. Portfolio Metrics Deep Dive

### Metric 1: Portfolio Summary Table
**Purpose**: High-level health check of the entire portfolio at the latest snapshot.

| KPI | Formula | Unit |
|-----|---------|------|
| Principal Outstanding | `SUM(POS_i)` for all active loans | INR Crore |
| Interest Outstanding | `SUM(accrued_interest_i)` for all active loans | INR Crore |
| Number of Active Loans | `COUNT(loans WHERE status = Active)` | Count |
| Weighted Avg. Interest Rate | `SUM(Rate_i × POS_i) / SUM(POS_i)` | % p.a. |
| Weighted Avg. Tenor | `SUM(RemainingTenor_i × POS_i) / SUM(POS_i)` | Months |

**Remaining Tenor** = (Original Maturity Date − Snapshot Date) in months

**Visualisation**: KPI cards with month-on-month delta indicators.

---

### Metric 2: POS Distribution by DPD Bucket
**Purpose**: Shows concentration of exposure across risk buckets.

```
For each bucket b:
  POS_b = SUM(POS_i) WHERE loan_i DPD falls in bucket b
  
Percentage = POS_b / Total_POS × 100
```

**Business Insight**: A healthy portfolio has >95% in Current bucket. Migration towards higher buckets signals deteriorating asset quality.

---

### Metric 3: Overall Collections Efficiency — Time Series
**Purpose**: Tracks how effectively the institution collects payments over time.

```
Collections Efficiency Rate = (Total Amount Collected / Total EMI Due) × 100%
```

- **Total EMI Due (Month)**: Sum of all scheduled EMIs across active loans in that month
- **Total Amount Collected**: Sum of actual payments received (principal + interest only, excluding penalties/bounce charges)

**Views**: Monthly and Quarterly aggregation with toggle.

**Business Insight**: 
- Rate > 100%: Over-collection (prepayments, arrears cleared)
- Rate = 100%: Perfect collection
- Rate < 100%: Under-collection (delinquency building)

---

### Metric 4: Collections Efficiency by DPD Bucket
**Purpose**: Identifies which delinquency segments are hardest to collect from.

```
CE_Rate(bucket_b, month_m) = Amount_Collected_from_bucket_b / EMI_Due_from_bucket_b × 100%
```

**Important**: A loan's DPD bucket is determined at the **start** of the month (prior month-end snapshot).

**Business Insight**: Typically, Current bucket has ~100% efficiency, while DPD 90+ may show 10-30%. This drives collection strategy allocation.

---

### Metric 5: POS Transition Matrix (INR Amount)
**Purpose**: Shows how much principal outstanding migrated between risk buckets.

Matrix Cell[i,j] = Total POS that moved from bucket i → bucket j in the period.

**Time Windows**:
- Monthly: Prior month-end → current month-end
- Quarterly: Prior quarter-end → current quarter-end
- N-Month Average: Simple average of N monthly matrices

---

### Metric 6: POS Transition Matrix (Percentage)
Same structure as Metric 5 but expressed as percentages.

```
Cell[i,j]% = POS_flow(i→j) / Total_POS_in_bucket_i_at_start × 100%
```

Each row sums to 100%. Diagonal = **Stabilisation Rate** (% staying in same bucket).

---

### Metric 7: Loan Count Transition Matrix (Absolute)
Same as Metric 5 but counts number of loans instead of POS amounts.

---

### Metric 8: Loan Count Transition Matrix (Percentage)
Same as Metric 6 but for loan counts.

```
Cell[i,j]% = Count_flow(i→j) / Total_count_in_bucket_i_at_start × 100%
```

**Note**: Metrics 5-8 share a single control panel with 4 tabs.

---

### Metric 9: Principal Repayment Rate by Cohort (Vintage Curve)
**Purpose**: Compares how different cohorts repay principal over time.

```
Repayment_Rate(cohort_c, MOB_m) = Cumulative_Principal_Collected_c_up_to_MOB_m / Total_Disbursed_Principal_c × 100%
```

**Business Insight**: Steeper curves = faster repayment. Flattening or diverging curves indicate vintage deterioration (newer cohorts performing worse than older ones).

---

### Metric 10: Delinquency Rate (PAR — Portfolio at Risk)
**Purpose**: Measures the percentage of the portfolio that is at risk of default.

```
PAR_x = SUM(POS where DPD > x) / Total_POS × 100%

Common variants:
- PAR 0: Any overdue (DPD > 0)
- PAR 30: DPD > 30
- PAR 60: DPD > 60  
- PAR 90: DPD > 90 (NPA ratio)
```

**Time Series**: Track PAR rates over multiple months to see trends.

---

### Metric 11: Roll Rate Analysis
**Purpose**: Shows the probability of loans moving ("rolling") from one DPD bucket to a worse bucket.

```
Roll_Rate(bucket_i → bucket_j) = Count_or_POS_migrating(i→j) / Total_in_bucket_i × 100%

Key Roll Rates:
- Current → DPD 1-30 (Flow Rate / Fresh Slippage)
- DPD 1-30 → DPD 31-60 
- DPD 31-60 → DPD 61-90
- DPD 61-90 → DPD 90+ (NPA formation rate)
```

**Business Insight**: High roll rates from DPD 31-60 → 61-90 indicate collection team effectiveness issues. Rising fresh slippage (Current → DPD 1-30) signals early-warning deterioration.

---

### Metric 12: NPA Rate & Movement
**Purpose**: Tracks Non-Performing Asset formation and resolution.

```
Gross NPA Rate = POS(DPD > 90) / Total_POS × 100%
Net NPA Rate = (Gross NPA - Provisions) / (Total_POS - Provisions) × 100%

NPA Additions (month) = POS newly entering DPD 90+ bucket
NPA Reductions (month) = POS cured (moved back to < 90 DPD) + Write-offs + Recoveries
```

---

### Metric 13: Prepayment & Foreclosure Analysis
**Purpose**: Tracks early loan closures which impact portfolio yield.

```
Prepayment Rate = POS_of_foreclosed_loans / Total_POS × 100%
Foreclosure Count Rate = Count_foreclosed / Total_Active_Count × 100%
```

Track monthly/quarterly trends and segment by product, tenor, and rate.

---

### Metric 14: Disbursement Trends
**Purpose**: Shows portfolio growth patterns.

```
Monthly Disbursement = SUM(disbursed_amount) for all loans disbursed in that month
Loan Count = COUNT(loans disbursed in that month)
Average Ticket Size = Monthly_Disbursement / Loan_Count
```

Segment by product type, region.

---

### Metric 15: Concentration Risk
**Purpose**: Identifies over-exposure to specific segments.

```
Concentration by Product = POS_product / Total_POS × 100% (for each product)
Concentration by Region = POS_region / Total_POS × 100% (for each region)
Concentration by Ticket Size Bucket = POS_bucket / Total_POS × 100%
```

**Business Insight**: Regulators watch for excessive concentration (e.g., >25% in one sector).

---

### Metric 16: Interest Income & Yield Analysis
**Purpose**: Measures portfolio profitability.

```
Portfolio Yield = (Interest_Collected_Annual / Average_POS) × 100%
Spread = Portfolio_Yield - Cost_of_Funds
Interest Accrued but Not Collected = Interest_Due - Interest_Collected
```

---

### Metric 17: Bounce Rate / Payment Failure Analysis
**Purpose**: Tracks failed payment attempts (ECS/NACH bounces).

```
Bounce Rate = Failed_Payment_Attempts / Total_Payment_Presentations × 100%
```

Segment by:
- First EMI bounce (early warning for fraud/inability to pay)
- Repeated bounces (chronic stress)
- Technical bounces vs. financial bounces

---

## 7. Transition Matrix Theory

### 7.1 What is a Transition Matrix?
A transition matrix (or migration matrix) is an N×N matrix showing how accounts/balances move between states over a defined time period. In loan portfolio analytics, it tracks DPD bucket migrations.

### 7.2 Structure
```
              To Bucket →
            Current  1-30  31-60  61-90  90+
From    Current  [a11]  [a12]  [a13]  [a14]  [a15]
Bucket  1-30     [a21]  [a22]  [a23]  [a24]  [a25]
↓       31-60    [a31]  [a32]  [a33]  [a34]  [a35]
        61-90    [a41]  [a42]  [a43]  [a44]  [a45]
        90+      [a51]  [a52]  [a53]  [a54]  [a55]
```

### 7.3 Reading the Matrix
- **Diagonal** (a11, a22, ...): Loans that stayed in the same bucket (stability)
- **Below diagonal** (a21, a31, ...): Loans that improved (cured/upgraded)
- **Above diagonal** (a12, a13, ...): Loans that deteriorated (downgraded)

### 7.4 Key Interpretations
| Pattern | Meaning |
|---------|---------|
| High diagonal values | Stable portfolio — most loans stay in their bucket |
| High above-diagonal values | Deteriorating portfolio — loans slipping into worse buckets |
| High below-diagonal values | Recovery — loans being cured/brought current |
| High a15 (Current → 90+) | Direct NPA formation (severe; skip-delinquency) |
| High a51 (90+ → Current) | NPA resolution / recovery success |

### 7.5 Averaging Transition Matrices
For N-month averages:
```
Average_Matrix = (Matrix_1 + Matrix_2 + ... + Matrix_N) / N
```
This smooths seasonality and provides a more stable view of portfolio behaviour.

### 7.6 Additional Column: "Paid Off"
The reference images show a 6th column "Paid Off" capturing loans that were closed during the period. This accounts for the portion of loans that leave the active portfolio.

---

## 8. Vintage & Cohort Analysis

### 8.1 Purpose
Vintage analysis compares the performance of loans originated in different time periods (cohorts) to identify:
- Underwriting quality changes over time
- Economic cycle impacts
- Portfolio maturation patterns

### 8.2 Month on Book (MOB)
```
MOB = Number of complete calendar months since disbursement month

Example:
- Loan disbursed: March 2023
- Snapshot: June 2023
- MOB = 3
```

### 8.3 Vintage Delinquency Curve
Plots the % of loans (or POS) that have ever become delinquent (or reached a specific DPD threshold), indexed by MOB.

```
Vintage_Delinquency(cohort_c, MOB_m) = 
  Count(loans in cohort_c that reached DPD > threshold by MOB_m) / 
  Total_loans_in_cohort_c × 100%
```

### 8.4 Vintage Repayment Curve (Metric 9)
```
Cumulative_Repayment%(cohort_c, MOB_m) = 
  Cumulative_Principal_Collected_from_cohort_c_up_to_MOB_m / 
  Total_Disbursed_of_cohort_c × 100%
```

### 8.5 Reading Vintage Curves
- **Steeper curves** → faster repayment / quicker delinquency build-up
- **Curves diverging upward** → newer cohorts performing worse (underwriting deterioration)
- **Curves converging** → portfolio stabilising / improvement
- **Target/expected curve** = theoretical amortisation schedule (dashed reference line)

### 8.6 Cohort Size Considerations
Always report cohort size alongside vintage metrics. Small cohorts may show volatile rates that don't reflect true trends.

---

## 9. Collections Analytics

### 9.1 Collections Funnel
```
Total EMI Due (Demand)
    │
    ├── Collected on time (Current)
    ├── Collected late (Arrears cleared)
    ├── Partially collected (Shortfall)
    └── Not collected (Delinquent)
```

### 9.2 Collections Efficiency Formula
```
CE% = Amount_Collected / EMI_Due × 100%
```

**Exclusions from Amount Collected**:
- Penalty/penal interest charges
- Bounce charges
- Legal fees recovered

**Include only**: Principal + Interest components of actual payments received.

### 9.3 Collections by DPD Bucket
Different collection strategies apply to different buckets:

| Bucket | Strategy | Typical CE% |
|--------|----------|-------------|
| Current | Auto-debit (NACH/ECS) | 98-100% |
| DPD 1-30 | Soft reminders, SMS, calls | 70-90% |
| DPD 31-60 | Intensive calling, field visits | 40-60% |
| DPD 61-90 | Legal notice, settlement offers | 20-40% |
| DPD 90+ | Legal action, recovery agents | 5-20% |

### 9.4 Resolution Categories
For movement tracking purposes, delinquent loans can resolve via:
- **Cure**: All overdue amounts paid, loan becomes Current
- **Partial cure**: Some payment made, DPD reduced but not fully cleared
- **Restructure**: Loan terms modified (new schedule)
- **Settlement**: Negotiated payoff at discount
- **Write-off**: Deemed uncollectible, removed from portfolio
- **Recovery (post-write-off)**: Amount collected after write-off

---

## 10. Indian NBFC/Lending Regulatory Context

### 10.1 Key Regulatory Framework
| Regulator | Scope |
|-----------|-------|
| **RBI** (Reserve Bank of India) | Overall banking/NBFC regulation |
| **NHB** (National Housing Bank) | Housing finance companies |
| **SEBI** | Securitisation and capital markets |

### 10.2 NPA Recognition (RBI Master Circular)
- **90-day norm**: An asset becomes NPA when interest/principal remains overdue for > 90 days
- **For agricultural loans**: Two harvest seasons but not exceeding 2 crop seasons
- **For micro/small enterprise**: 90 days for term loans; for CC/OD accounts when outstanding continuously exceeds sanctioned limit

### 10.3 NBFC-Specific Rules (IRAC Norms)
- Income Recognition: Stop accruing income once loan becomes NPA
- Asset Classification: Standard → Sub-Standard → Doubtful → Loss
- Provisioning: Percentage of outstanding to be set aside as loss provision

### 10.4 Digital Lending Guidelines (RBI 2022)
- All digital loan disbursements to borrower's bank account
- KYC compliance mandatory
- Transparent disclosure of annual percentage rate (APR)
- Cooling-off period for borrower to exit

### 10.5 Key Metrics Watched by Regulators
| Metric | Regulatory Threshold |
|--------|---------------------|
| Gross NPA Ratio | < 6% (comfort zone) |
| Net NPA Ratio | < 3% |
| Capital Adequacy (CRAR) | > 15% for NBFCs |
| Provision Coverage Ratio | > 70% |
| Concentration (single borrower) | < 15% of capital funds |

### 10.6 Common Loan Products (Indian NBFC Context)
| Product | Typical Tenor | Typical Rate | Collateral |
|---------|--------------|-------------|------------|
| Personal Loan | 12-60 months | 12-24% p.a. | Unsecured |
| Two-Wheeler Loan | 12-36 months | 14-20% p.a. | Vehicle |
| Used Car Loan | 12-60 months | 12-18% p.a. | Vehicle |
| Gold Loan | 3-12 months | 10-18% p.a. | Gold |
| Home Loan | 60-360 months | 8-12% p.a. | Property |
| LAP (Loan Against Property) | 36-180 months | 10-14% p.a. | Property |
| Business Loan | 12-60 months | 14-24% p.a. | Mixed |
| Microfinance (JLG) | 12-24 months | 20-26% p.a. | Group guarantee |

---

## 11. Key Formulas & Computation Notes

### 11.1 Complete Formula Reference

```python
# ═══════════════════════════════════════════════════════════
# METRIC 1: Portfolio Summary
# ═══════════════════════════════════════════════════════════
principal_outstanding = sum(pos_i for loan_i in active_loans)
interest_outstanding = sum(accrued_interest_i for loan_i in active_loans)
active_loan_count = len(active_loans)
weighted_avg_rate = sum(rate_i * pos_i for loan_i in active_loans) / sum(pos_i)
remaining_tenor_i = (maturity_date_i - snapshot_date).months
weighted_avg_tenor = sum(remaining_tenor_i * pos_i) / sum(pos_i)

# ═══════════════════════════════════════════════════════════
# METRIC 2: POS Distribution by DPD Bucket
# ═══════════════════════════════════════════════════════════
for bucket in [CURRENT, DPD_1_30, DPD_31_60, DPD_61_90, DPD_90_PLUS]:
    pos_bucket = sum(pos_i for loan_i where dpd_bucket(loan_i) == bucket)
    pct_bucket = pos_bucket / total_pos * 100

# ═══════════════════════════════════════════════════════════
# METRIC 3: Collections Efficiency Time Series
# ═══════════════════════════════════════════════════════════
for month in reporting_months:
    emi_due = sum(scheduled_emi for all active loans with due_date in month)
    amount_collected = sum(principal_collected + interest_collected for receipts in month)
    ce_rate = amount_collected / emi_due * 100

# ═══════════════════════════════════════════════════════════
# METRIC 4: Collections Efficiency by DPD Bucket
# ═══════════════════════════════════════════════════════════
# DPD bucket assigned based on PRIOR month-end snapshot
for bucket in dpd_buckets:
    for month in selected_month:
        emi_due_bucket = sum(emi_due for loans in bucket at start_of_month)
        collected_bucket = sum(collected for loans in bucket during month)
        ce_bucket = collected_bucket / emi_due_bucket * 100

# ═══════════════════════════════════════════════════════════
# METRICS 5-8: Transition Matrices
# ═══════════════════════════════════════════════════════════
# For each loan, determine:
#   start_bucket = DPD bucket at period_start (prior month-end)
#   end_bucket = DPD bucket at period_end (current month-end)
# Then aggregate:

# Metric 5 (POS Amount):
matrix_pos[i][j] = sum(pos for loans where start=i and end=j)

# Metric 6 (POS Percentage):
matrix_pos_pct[i][j] = matrix_pos[i][j] / row_total_pos[i] * 100

# Metric 7 (Count):
matrix_count[i][j] = count(loans where start=i and end=j)

# Metric 8 (Count Percentage):
matrix_count_pct[i][j] = matrix_count[i][j] / row_total_count[i] * 100

# N-Month Average:
avg_matrix = sum(monthly_matrices) / N

# ═══════════════════════════════════════════════════════════
# METRIC 9: Principal Repayment Rate by Cohort
# ═══════════════════════════════════════════════════════════
for cohort in cohorts:
    total_disbursed = sum(disbursed_amount for loans in cohort)
    for mob in range(1, max_mob + 1):
        cum_principal = sum(principal_collected up_to mob months after disbursement)
        repayment_rate = cum_principal / total_disbursed * 100
```

### 11.2 Edge Cases & Business Rules

| Scenario | Handling |
|----------|----------|
| Loan disbursed mid-month | First MOB starts from next calendar month |
| EMI due date falls on holiday | DPD still counts from original due date |
| Partial payment received | Apply waterfall: charges → interest → principal |
| Multiple payments in a month | Sum all receipts for that month |
| Loan restructured | Treat as new schedule from restructure date; original cohort retained |
| Zero EMI due (moratorium) | Exclude from CE calculation for that period |
| Negative remaining tenor | Matured but not closed — flag as data quality issue |
| Loan closed mid-month | Include in start-of-period count but mark as "Paid Off" in transition |

### 11.3 Unit Conversions
```
1 Crore = 10,000,000 (1 × 10^7)
1 Lakh = 100,000 (1 × 10^5)
100 Lakh = 1 Crore

When displaying in Crore: value_in_crore = value_in_inr / 10_000_000
When displaying in Billion: value_in_billion = value_in_inr / 1_000_000_000
```

---

## 12. Glossary

| Term | Definition |
|------|-----------|
| **AUM** | Assets Under Management — total POS of the lending portfolio |
| **Bounce** | Failed auto-debit attempt (ECS/NACH/e-mandate) |
| **Bureau Score** | Credit score from CIBIL, Experian, Equifax, or CRIF (India: 300-900 range) |
| **CE** | Collections Efficiency |
| **Cohort** | Group of loans disbursed in the same month |
| **CRAR** | Capital to Risk-weighted Assets Ratio |
| **Current** | Loan with 0 DPD — fully up to date |
| **DPD** | Days Past Due — days since earliest unpaid instalment was due |
| **ECS** | Electronic Clearing Service (legacy auto-debit system) |
| **EMI** | Equated Monthly Instalment |
| **FLDG** | First Loss Default Guarantee |
| **Foreclosure** | Early closure/prepayment of loan by borrower |
| **GNPA** | Gross Non-Performing Assets |
| **IRAC** | Income Recognition and Asset Classification (RBI norms) |
| **KYC** | Know Your Customer |
| **LAP** | Loan Against Property |
| **LGD** | Loss Given Default |
| **LTV** | Loan-to-Value ratio |
| **MOB** | Month on Book — months since disbursement |
| **NACH** | National Automated Clearing House (auto-debit system) |
| **NBFC** | Non-Banking Financial Company |
| **Net NPA** | Gross NPA minus provisions |
| **NPA** | Non-Performing Asset (DPD > 90 days) |
| **NPL** | Non-Performing Loan (synonym for NPA) |
| **OD** | Overdraft |
| **PAR** | Portfolio at Risk |
| **PD** | Probability of Default |
| **POS** | Principal Outstanding (unpaid principal balance) |
| **Provisioning** | Setting aside funds to cover expected losses |
| **Roll Rate** | % of loans moving from one DPD bucket to the next worse bucket |
| **SMA** | Special Mention Account (early stress indicator, DPD 1-90) |
| **Snapshot** | Point-in-time view of portfolio (always month-end) |
| **Tenor** | Duration/term of the loan in months |
| **Vintage** | Performance analysis indexed by MOB for each cohort |
| **Write-off** | Accounting removal of uncollectible loan from books |
| **Yield** | Effective return on the loan portfolio |

---

## Appendix A: Visualisation Colour Scheme

```
DPD Severity Palette:
- Current (0 DPD):     #4CAF50 (Green)
- DPD 1-30:           #FFC107 (Amber)  
- DPD 31-60:          #FF9800 (Orange)
- DPD 61-90:          #FF5722 (Deep Orange)
- DPD 90+:            #F44336 (Red)

Transition Matrix Heatmap:
- Diagonal (no change):   #E0E0E0 (Light Grey)
- Above diagonal (worse): Red gradient (intensity ∝ value)
- Below diagonal (better): Green gradient (intensity ∝ value)

Collections Chart:
- EMI Due bar:            #4682B4 (Steel Blue)
- Amount Collected bar:   #008080 (Teal Green)
- Efficiency rate line:   #FF6600 (Orange line)
```

## Appendix B: Filter Dimensions

All metrics must support slicing by:
| Filter | Description |
|--------|-------------|
| **Product** | Loan product type (Personal, Vehicle, Home, etc.) |
| **Region** | Geographic state/zone |
| **City** | Specific city |
| **Cohort** | Disbursement month |
| **Time Period** | Snapshot month/quarter selection |

## Appendix C: Data Quality Checks (Validation Agent)

The Data Validation Agent should check:

| Check Category | Specific Checks |
|----------------|----------------|
| **Completeness** | Null/missing values in critical fields (loan_id, dates, amounts) |
| **Referential Integrity** | All payment records have matching loan_id in facility table |
| **Temporal Consistency** | disbursement_date < maturity_date; payment_date ≥ disbursement_date |
| **Value Ranges** | Interest rate 0-50%; tenor 1-360 months; amounts > 0 |
| **Duplicates** | No duplicate loan_ids; no duplicate transactions |
| **Business Rules** | POS ≤ sanctioned_amount; cumulative_paid ≤ disbursed_amount |
| **Cross-field** | EMI amount consistent with rate/tenor/principal (within tolerance) |
| **Date Format** | Consistent date parsing across all date columns |

---

*Document Version: 1.0 | Created for Parse.ai Loan Portfolio Analytics Case Study*
