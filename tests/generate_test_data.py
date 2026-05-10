"""
Generate synthetic test CSV datasets with known ground-truth for all 9 metrics.

Test Case 1 — "Clean Portfolio" (10 loans, all current, 100% CE, single vintage)
Test Case 2 — "Stressed Portfolio" (10 loans across all DPD buckets, varied CE, transitions)
Test Case 3 — "Edge Cases" (prepayments >100% CE, zero payments, single loan, NPA)

Each test case produces 5 CSV files matching the Medium-format schema:
  01_Borrowers, 02_Collateral, 03_Loan_Facilities,
  04_Payment_Schedule_Transactions, 05_Collections

Ground truth values are written to ground_truth.json alongside the CSVs.
"""
import os, json, csv, math
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

BASE = os.path.dirname(os.path.abspath(__file__))


# ─── Helpers ────────────────────────────────────────────────────────────────
def write_csv(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    print(f"  wrote {path}  ({len(rows)} rows)")


def borrower_row(bid, name="Test User", cibil=750, income=600000):
    return dict(
        borrower_id=bid, borrower_type="Individual", salutation="Mr.", first_name=name.split()[0],
        last_name=name.split()[-1], full_name=name, date_of_birth="1990-01-15", age_at_application=33,
        gender="Male", marital_status="Married", number_of_dependents=1, pan_number="ABCDE1234F",
        aadhaar_last4="1234", mobile_number="9876543210", alternate_mobile="", email_id="test@test.com",
        current_address_line1="123 Test Street", current_city="Mumbai", current_district="Mumbai",
        current_state="Maharashtra", current_pincode="400001", years_at_current_address=5,
        property_ownership_status="Owned", permanent_address_same_as_current="Y",
        education_level="Graduate", employment_type="Salaried", employer_name="Test Corp",
        employer_city="Mumbai", years_in_current_employment=5, total_work_experience_years=10,
        industry_sector="IT", business_name="", business_type="", years_in_business="",
        annual_business_turnover_INR="", gst_registration_number="", udyam_registration_number="",
        annual_income_INR=income, monthly_gross_income_INR=income//12,
        existing_monthly_obligations_INR=income//24, net_monthly_income_after_obligations_INR=income//24,
        income_type="Regular", cibil_score=cibil, cibil_score_date="2025-01-01",
        cibil_report_id="CIB000001", equifax_score=cibil-10,
        number_of_active_loans=1, number_of_overdue_accounts=0, credit_history_length_months=60,
        highest_dpd_last_24_months=0, derogatory_marks_count=0, written_off_in_past=0,
        bureau_enquiries_last_6_months=1, nach_mandate_registered="Y", nach_mandate_bank="SBI",
        nach_mandate_account_type="Savings", kyc_status="Completed", kyc_date="2025-01-01",
        kyc_mode="Aadhaar eKYC", co_borrower_flag="N", guarantor_flag="N",
        customer_segment="Prime", risk_category="Low Risk",
    )


def collateral_row(cid, lid, value_inr, ltv=0.75, ctype="Vehicle"):
    return dict(
        collateral_id=cid, loan_id=lid, collateral_type=ctype, collateral_value_INR=value_inr,
        ltv_at_origination=ltv, vehicle_category="Car", vehicle_type="Sedan",
        vehicle_make="Maruti", vehicle_model="Swift", year_of_manufacture=2023,
        vehicle_condition="New", registration_number="MH01AB1234", chassis_number="CHS001",
        engine_number="ENG001", hypothecation_noted_with_rto="Y", rc_book_collected="Y",
        form_35_lien_marked="Y", insurance_provider="ICICI Lombard", insurance_policy_number="POL001",
        insurance_validity_date="2027-01-01", insurance_type="Comprehensive",
        insurance_sum_insured_INR=value_inr, vehicle_valuation_INR=value_inr,
        valuation_date="2025-01-01", valuation_agency="CRISIL",
        property_type="", property_address_line1="", property_city="", property_state="",
        property_pincode="", property_area_sqft="", property_age_years="",
        property_market_value_INR="", property_guideline_value_INR="",
        property_valuation_date="", property_valuation_agency="",
        title_clear_status="", encumbrance_certificate_status="", legal_opinion_obtained="",
        mutation_completed="", property_insurance="", latitude="", longitude="",
    )


def loan_row(lid, bid, cid, principal, rate, tenor, disb_date, dpd, dpd_bucket, status,
             obs_date="2026-03-31", paid_prin=0, paid_int=0, emi=0, outstanding=None,
             npa_date="", n_installments_due=0):
    first_emi = (datetime.strptime(disb_date, "%Y-%m-%d") + relativedelta(months=1)).strftime("%Y-%m-%d")
    maturity = (datetime.strptime(disb_date, "%Y-%m-%d") + relativedelta(months=tenor)).strftime("%Y-%m-%d")
    if outstanding is None:
        outstanding = principal - paid_prin
    if emi == 0 and tenor > 0:
        r_m = rate / 100 / 12
        if r_m > 0:
            emi = round(principal * r_m * (1+r_m)**tenor / ((1+r_m)**tenor - 1), 2)
        else:
            emi = round(principal / tenor, 2)
    return dict(
        loan_id=lid, borrower_id=bid, collateral_id=cid, application_id=f"APP{lid[3:]}",
        product_type="Personal Loan", product_code="PL", loan_sub_type="Regular",
        branch_code="BR001", branch_name="Mumbai Main", branch_state="Maharashtra",
        loan_officer_id="LO001", channel_of_sourcing="Branch", loan_purpose="Personal",
        application_date=(datetime.strptime(disb_date, "%Y-%m-%d") - timedelta(days=15)).strftime("%Y-%m-%d"),
        sanction_date=(datetime.strptime(disb_date, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d"),
        disbursement_date=disb_date, first_emi_date=first_emi, maturity_date=maturity,
        principal_sanctioned_INR=principal, principal_disbursed_INR=principal,
        annual_interest_rate_pct=rate, repayment_frequency="Monthly", tenor_months=tenor,
        emi_amount_INR=emi, processing_fee_pct=1.0, processing_fee_amount_INR=round(principal*0.01,2),
        insurance_premium_INR=0, penal_interest_rate_pct_pa=2.0, prepayment_penalty_pct=3.0,
        ltv_at_origination=0.75, collateral_type="Vehicle",
        number_of_installments_scheduled=tenor, number_of_installments_due_to_date=n_installments_due,
        total_principal_paid_INR=paid_prin, total_interest_paid_INR=paid_int,
        total_fees_paid_INR=0, total_bounces_to_date=0,
        last_payment_date=obs_date if paid_prin > 0 else "",
        last_payment_amount_INR=emi if paid_prin > 0 else 0,
        current_outstanding_principal_INR=outstanding, current_dpd=dpd, dpd_bucket=dpd_bucket,
        asset_classification="Standard" if dpd < 90 else "NPA",
        loan_status=status, npa_date=npa_date, write_off_date="", foreclosure_flag="N",
        foreclosure_date="", restructuring_flag="N", collection_stage="Normal" if dpd == 0 else "Soft Collection",
        nach_status="Active", repayment_mode="NACH", portfolio_observation_date=obs_date,
    )


def txn_row(sid, lid, inst_num, due_date, emi_sched, prin_sched, int_sched, open_bal,
            actual_paid, prin_paid, int_paid, status, dpd, dpd_bucket, close_bal,
            cum_prin=0, cum_int=0, actual_date=None, bounce="N"):
    return dict(
        schedule_id=sid, loan_id=lid, installment_number=inst_num, due_date=due_date,
        emi_amount_scheduled_INR=emi_sched, principal_component_scheduled=prin_sched,
        interest_component_scheduled=int_sched, opening_principal_balance_INR=open_bal,
        closing_principal_balance_scheduled=close_bal,
        actual_payment_date=actual_date if actual_date else (due_date if status == "Paid" else ""),
        actual_amount_paid_INR=actual_paid, principal_paid_INR=prin_paid,
        interest_paid_INR=int_paid, fees_and_charges_paid_INR=0, payment_status=status,
        days_past_due=dpd, dpd_bucket=dpd_bucket, cumulative_principal_paid_INR=cum_prin,
        cumulative_interest_paid_INR=cum_int, actual_outstanding_principal_INR=close_bal,
        bounce_flag=bounce, bounce_charges_INR=0, covid_moratorium_applied="N",
    )


def coll_row(eid, lid, obs_month, inst, dpd, dpd_bucket, overdue_prin, overdue_emi,
             total_out, collected, stage="Normal"):
    return dict(
        collection_event_id=eid, loan_id=lid, observation_month=obs_month,
        installment_number=inst, dpd_as_of_observation_month=dpd, dpd_bucket=dpd_bucket,
        overdue_principal_INR=overdue_prin, overdue_emi_amount_INR=overdue_emi,
        total_outstanding_principal_INR=total_out, collection_stage=stage,
        field_agent_id="CA001", field_agent_name="Agent A", contact_attempt_count=1,
        last_contact_date=f"{obs_month}-15", last_contact_mode="Phone Call",
        contact_outcome="Promise to Pay", promise_to_pay_date="", promise_to_pay_amount_INR="",
        ptp_fulfilled="", amount_collected_this_month_INR=collected,
        legal_notice_sent="N", legal_notice_date="", sarfaesi_initiated="N",
        sarfaesi_initiation_date="", repossession_initiated="N", repossession_date="",
        asset_repossessed="N", auction_initiated="N", auction_recovery_amount_INR="",
        collection_notes="", write_off_flag="N", write_off_date="",
    )


# =============================================================================
# TEST CASE 1: "Clean Portfolio" — all current, 100% CE
# 10 identical loans, all disbursed 2025-04-01, 12 months, 12% rate
# All 12 installments paid on time → CE = 100%
# Observation date: 2026-03-31 (all 12 due)
# =============================================================================
def gen_test_case_1():
    d = os.path.join(BASE, "test_case_1")
    print("\n=== TEST CASE 1: Clean Portfolio ===")
    principal = 1_000_000  # 10 lakh each
    rate = 12.0
    tenor = 12
    n_loans = 10
    r_m = rate / 100 / 12  # 0.01
    emi = round(principal * r_m * (1+r_m)**tenor / ((1+r_m)**tenor - 1), 2)
    # emi ≈ 88848.79

    borrowers, collaterals, loans, txns, colls = [], [], [], [], []
    disb = "2025-04-01"

    total_scheduled = 0
    total_paid = 0
    total_prin_sched = 0
    total_int_sched = 0

    for i in range(1, n_loans+1):
        bid = f"BRW{i:08d}"
        lid = f"LN{i:08d}"
        cid = f"COL{i:08d}"

        borrowers.append(borrower_row(bid, f"User{i} Test"))
        collaterals.append(collateral_row(cid, lid, int(principal / 0.75)))

        balance = principal
        cum_prin = 0
        cum_int = 0
        for inst in range(1, tenor+1):
            due = (datetime(2025,4,1) + relativedelta(months=inst)).strftime("%Y-%m-%d")
            int_comp = round(balance * r_m, 2)
            prin_comp = round(emi - int_comp, 2)
            close = round(balance - prin_comp, 2)
            if inst == tenor:
                prin_comp = round(balance, 2)
                close = 0.0
            cum_prin = round(cum_prin + prin_comp, 2)
            cum_int = round(cum_int + int_comp, 2)
            total_scheduled += emi
            total_paid += emi
            total_prin_sched += prin_comp
            total_int_sched += int_comp
            txns.append(txn_row(
                f"SCH{i:04d}{inst:04d}", lid, inst, due, emi, prin_comp, int_comp,
                balance, emi, prin_comp, int_comp, "Paid", 0, "Current", close,
                cum_prin, cum_int, due,
            ))
            balance = close

        # Loan fully paid
        loans.append(loan_row(
            lid, bid, cid, principal, rate, tenor, disb, dpd=0, dpd_bucket="Current",
            status="Active", paid_prin=principal, paid_int=round(cum_int,2), emi=emi,
            outstanding=0, n_installments_due=12,
        ))

        # Collections: one row per month per loan (all current, full payment)
        for inst in range(1, tenor+1):
            month = (datetime(2025,4,1) + relativedelta(months=inst)).strftime("%Y-%m")
            colls.append(coll_row(
                f"CEV{i:04d}{inst:04d}", lid, month, inst, 0, "Current",
                0, 0, round(principal - (principal/tenor)*inst, 2), emi,
            ))

    write_csv(f"{d}/01_Borrowers.csv", borrowers)
    write_csv(f"{d}/02_Collateral.csv", collaterals)
    write_csv(f"{d}/03_Loan_Facilities.csv", loans)
    write_csv(f"{d}/04_Payment_Schedule_Transactions.csv", txns)
    write_csv(f"{d}/05_Collections.csv", colls)

    # Ground truth
    total_pos_cr = n_loans * principal / 1e7  # 10 Cr disbursed, but all paid → outstanding 0
    # For M1 POS = current_outstanding_principal, which is 0 for fully paid
    # BUT loan_status="Active" so active count = 10
    # WAIR = all same rate = 12%, weight by POS...
    # BUT outstanding is 0 for all. The pipeline may use disbursed amount for WAIR.
    # Let's use: WAIR=12% (all same), WART=0 (all matured), POS ≈ 0.0 Cr (all paid off)

    gt = {
        "M1": {
            "total_pos_cr": 0.0,  # all fully paid
            "active_loan_count": 10,
            "wair_pct": 12.0,  # all same rate
        },
        "M2": {
            "Current": 0.0,  # POS is 0 for all (fully paid)
            "DPD 1-30": 0.0,
            "DPD 31-60": 0.0,
            "DPD 61-90": 0.0,
            "DPD 90+": 0.0,
        },
        "M3": {
            "overall_ce_pct": 100.0,  # all paid on time
            "description": "100% CE — every EMI paid in full on time",
        },
        "M4": {
            "Current": 100.0,  # only current bucket, 100% CE
        },
        "M5_M6_M7_M8": {
            "description": "All loans stay Current → Current→Current = 100%",
            "current_to_current_pct": 100.0,
        },
        "M9": {
            "description": "Single vintage (2025-Q2), 10 loans, no delinquency",
            "cohort_count": 1,
        },
    }
    json.dump(gt, open(f"{d}/ground_truth.json","w"), indent=2)
    print(f"  Ground truth → {d}/ground_truth.json")
    return d


# =============================================================================
# TEST CASE 2: "Stressed Portfolio" — DPD distribution, transitions, varied CE
# 10 loans, disbursed 2025-01-01, 24-month tenor, 15% rate
# Different payment behaviors → different DPD buckets at observation
# Observation date: 2026-03-31 (15 installments due)
# =============================================================================
def gen_test_case_2():
    d = os.path.join(BASE, "test_case_2")
    print("\n=== TEST CASE 2: Stressed Portfolio ===")

    principal = 1_000_000  # 10 lakh each
    rate = 15.0
    tenor = 24
    n_loans = 10
    disb = "2025-01-01"
    obs = "2026-03-31"
    r_m = rate / 100 / 12  # 0.0125
    emi = round(principal * r_m * (1+r_m)**tenor / ((1+r_m)**tenor - 1), 2)
    # emi ≈ 48486.65

    # Loan behaviors (how many of the 15 due installments are paid):
    # L1-L4: All 15 paid on time → Current (DPD 0)    — 4 loans
    # L5-L6: Last 1 unpaid  → DPD 1-30                — 2 loans
    # L7:    Last 2 unpaid  → DPD 31-60               — 1 loan
    # L8:    Last 3 unpaid  → DPD 61-90               — 1 loan
    # L9:    Last 4 unpaid  → DPD 90+ (NPA)           — 1 loan
    # L10:   Paid 0 of 15   → DPD 90+ (NPA)           — 1 loan

    behaviors = {
        1:  (15, 0, "Current"),
        2:  (15, 0, "Current"),
        3:  (15, 0, "Current"),
        4:  (15, 0, "Current"),
        5:  (14, 30, "DPD 1-30"),      # missed inst 15 → ~30 DPD
        6:  (14, 25, "DPD 1-30"),
        7:  (13, 55, "DPD 31-60"),     # missed inst 14,15 → ~55 DPD
        8:  (12, 85, "DPD 61-90"),     # missed inst 13,14,15 → ~85 DPD
        9:  (11, 120, "DPD 90+"),      # missed 12,13,14,15 → ~120 DPD
        10: (0, 450, "DPD 90+"),       # zero payments → 450 DPD
    }

    borrowers, collaterals, loans, txns, colls = [], [], [], [], []

    # For CE computation
    total_sched_all = 0
    total_paid_all = 0
    monthly_sched = {}  # month → total scheduled
    monthly_paid = {}   # month → total paid

    for i in range(1, n_loans+1):
        bid = f"BRW{i:08d}"
        lid = f"LN{i:08d}"
        cid = f"COL{i:08d}"
        n_paid, dpd_val, dpd_bkt = behaviors[i]

        borrowers.append(borrower_row(bid, f"Stressed{i} User", cibil=650 if dpd_val>0 else 750))
        collaterals.append(collateral_row(cid, lid, int(principal/0.75)))

        balance = principal
        cum_prin = 0
        cum_int = 0
        for inst in range(1, 16):  # 15 installments due
            due = (datetime(2025,1,1) + relativedelta(months=inst)).strftime("%Y-%m-%d")
            month = (datetime(2025,1,1) + relativedelta(months=inst)).strftime("%Y-%m")
            int_comp = round(balance * r_m, 2)
            prin_comp = round(emi - int_comp, 2)
            close = round(balance - prin_comp, 2)
            paid = inst <= n_paid

            if paid:
                cum_prin = round(cum_prin + prin_comp, 2)
                cum_int = round(cum_int + int_comp, 2)
                actual_paid_amt = emi
                p_paid = prin_comp
                i_paid = int_comp
                pay_status = "Paid"
                inst_dpd = 0
                inst_bkt = "Current"
                balance = close
            else:
                actual_paid_amt = 0
                p_paid = 0
                i_paid = 0
                pay_status = "Overdue"
                inst_dpd = dpd_val
                inst_bkt = dpd_bkt
                # balance stays the same (nothing was paid)

            total_sched_all += emi
            total_paid_all += actual_paid_amt
            monthly_sched[month] = monthly_sched.get(month, 0) + emi
            monthly_paid[month] = monthly_paid.get(month, 0) + actual_paid_amt

            txns.append(txn_row(
                f"SCH{i:04d}{inst:04d}", lid, inst, due, emi, prin_comp, int_comp,
                balance if not paid else (balance + prin_comp), actual_paid_amt,
                p_paid, i_paid, pay_status, inst_dpd, inst_bkt,
                balance if not paid else close, cum_prin, cum_int,
                due if paid else "", "N" if paid else "Y",
            ))

        outstanding = balance
        npa = "2025-12-01" if dpd_val >= 90 else ""
        loans.append(loan_row(
            lid, bid, cid, principal, rate, tenor, disb, dpd=dpd_val, dpd_bucket=dpd_bkt,
            status="Active", paid_prin=cum_prin, paid_int=cum_int, emi=emi,
            outstanding=outstanding, n_installments_due=15,
            npa_date=npa,
        ))

        # Collections (one per month per loan)
        for inst in range(1, 16):
            month = (datetime(2025,1,1) + relativedelta(months=inst)).strftime("%Y-%m")
            paid = inst <= n_paid
            colls.append(coll_row(
                f"CEV{i:04d}{inst:04d}", lid, month, inst,
                0 if paid else dpd_val, "Current" if paid else dpd_bkt,
                0 if paid else round(emi*(15-n_paid),2), 0 if paid else emi,
                outstanding, emi if paid else 0,
                "Normal" if paid else "Soft Collection",
            ))

    write_csv(f"{d}/01_Borrowers.csv", borrowers)
    write_csv(f"{d}/02_Collateral.csv", collaterals)
    write_csv(f"{d}/03_Loan_Facilities.csv", loans)
    write_csv(f"{d}/04_Payment_Schedule_Transactions.csv", txns)
    write_csv(f"{d}/05_Collections.csv", colls)

    # ── Ground truth ────────────────────────────────────────
    # M1: POS = sum of outstanding principals (for active loans)
    # L1-L4: fully paid 15 installments → we need actual remaining balance
    # Let me compute programmatically for accuracy
    balances = {}
    for i in range(1, 11):
        n_paid_i = behaviors[i][0]
        bal = principal
        for inst in range(1, n_paid_i+1):
            int_c = round(bal * r_m, 2)
            prin_c = round(emi - int_c, 2)
            bal = round(bal - prin_c, 2)
        balances[i] = bal

    total_pos = sum(balances.values())
    # WAIR: weighted by outstanding
    wair_num = sum(balances[i] * rate for i in range(1,11))
    wair = wair_num / total_pos if total_pos > 0 else 0

    # M2: POS by DPD bucket
    m2 = {"Current": 0, "DPD 1-30": 0, "DPD 31-60": 0, "DPD 61-90": 0, "DPD 90+": 0}
    for i in range(1, 11):
        bkt = behaviors[i][2]
        m2[bkt] += balances[i]

    # M3: overall CE
    overall_ce = (total_paid_all / total_sched_all * 100) if total_sched_all > 0 else 0

    # Monthly CE
    monthly_ce = {}
    for month in sorted(monthly_sched.keys()):
        s = monthly_sched[month]
        p = monthly_paid.get(month, 0)
        monthly_ce[month] = round(p / s * 100, 4) if s > 0 else 0

    # M5-M8 transitions: For this synthetic data, we look at T-1 (Feb 2026) → T (Mar 2026)
    # In Feb 2026 (inst 14): L1-4 current, L5-6 current (they paid 14), L7 current (paid 13), 
    #   L8 current (paid 12), L9 current (paid 11), L10 NPA
    # Wait — let me reconsider. The DPD at each installment:
    # For loan i, installments 1..n_paid are "Paid" (Current), installments n_paid+1..15 are "Overdue"
    # At inst 14 (Feb 2026): 
    #   L1-L4 (paid 15): inst14 paid → Current
    #   L5-L6 (paid 14): inst14 paid → Current
    #   L7 (paid 13): inst14 NOT paid → it's been 1 missed → DPD ~30 → DPD 1-30
    #   L8 (paid 12): inst14 NOT paid, missed 13,14 → DPD ~55 → DPD 31-60
    #   L9 (paid 11): inst14 NOT paid, missed 12,13,14 → DPD ~85 → DPD 61-90
    #   L10 (paid 0): all missed → DPD 90+
    # At inst 15 (Mar 2026):
    #   L1-L4: Current
    #   L5-L6 (paid 14): inst15 NOT paid → DPD 1-30
    #   L7 (paid 13): missed 14,15 → DPD 31-60
    #   L8 (paid 12): missed 13,14,15 → DPD 61-90
    #   L9 (paid 11): missed 12,13,14,15 → DPD 90+
    #   L10 (paid 0): DPD 90+

    # Transition matrix (by count):
    # Current(6: L1-L6) → Current(4: L1-L4)=4, DPD1-30(2: L5,L6)=2
    # DPD1-30(1: L7) → DPD31-60(1)=1
    # DPD31-60(1: L8) → DPD61-90(1)=1
    # DPD61-90(1: L9) → DPD90+(1)=1
    # DPD90+(1: L10) → DPD90+(1)=1

    transition_count = {
        "Current": {"Current": 4, "DPD 1-30": 2},
        "DPD 1-30": {"DPD 31-60": 1},
        "DPD 31-60": {"DPD 61-90": 1},
        "DPD 61-90": {"DPD 90+": 1},
        "DPD 90+": {"DPD 90+": 1},
    }

    gt = {
        "M1": {
            "total_pos_cr": round(total_pos / 1e7, 4),
            "active_loan_count": 10,
            "wair_pct": round(wair, 4),
            "note": "WAIR = 15% (all same rate), POS = sum of remaining balances",
        },
        "M2": {k: round(v/1e7, 4) for k, v in m2.items()},
        "M2_pct": {k: round(v/total_pos*100, 2) if total_pos else 0 for k, v in m2.items()},
        "M3": {
            "overall_ce_pct": round(overall_ce, 4),
            "monthly_ce": monthly_ce,
            "total_scheduled": round(total_sched_all, 2),
            "total_paid": round(total_paid_all, 2),
        },
        "M5_transitions_by_count": transition_count,
        "loan_balances": {f"L{i}": round(balances[i], 2) for i in range(1, 11)},
    }
    json.dump(gt, open(f"{d}/ground_truth.json","w"), indent=2)
    print(f"  Ground truth → {d}/ground_truth.json")
    return d


# =============================================================================
# TEST CASE 3: "Edge Cases" — prepayments, zero payment, mixed, single loan NPA
# 6 loans with extreme behaviors
# =============================================================================
def gen_test_case_3():
    d = os.path.join(BASE, "test_case_3")
    print("\n=== TEST CASE 3: Edge Cases ===")

    rate = 12.0
    r_m = rate / 100 / 12
    obs = "2026-03-31"

    # L1: Prepayment — principal 500K, 12-month, pays 150% of EMI each month
    # L2: Zero payment — principal 500K, 12-month, pays nothing → DPD 90+
    # L3: Very large loan — principal 50Cr (500M), 12-month, all paid on time
    # L4: Very small loan — principal 10K, 12-month, all paid on time
    # L5: Partial payer — pays exactly 50% of EMI each month
    # L6: Late payer — pays full EMI but 45 days late each time

    configs = [
        # (id, principal, tenor, behavior, disb_date)
        (1, 500_000, 12, "prepay_150pct", "2025-04-01"),
        (2, 500_000, 12, "zero_payment", "2025-04-01"),
        (3, 500_000_000, 12, "full_pay", "2025-04-01"),
        (4, 10_000, 12, "full_pay", "2025-04-01"),
        (5, 500_000, 12, "half_pay", "2025-04-01"),
        (6, 500_000, 12, "late_pay_45d", "2025-04-01"),
    ]

    borrowers, collaterals, loans, txns, colls = [], [], [], [], []
    total_sched_all = 0
    total_paid_all = 0
    monthly_sched = {}
    monthly_paid = {}
    loan_data = {}

    for idx, (i, principal, tenor, behavior, disb) in enumerate(configs):
        bid = f"BRW{i:08d}"
        lid = f"LN{i:08d}"
        cid = f"COL{i:08d}"

        emi = round(principal * r_m * (1+r_m)**tenor / ((1+r_m)**tenor - 1), 2)

        borrowers.append(borrower_row(bid, f"Edge{i} Case"))
        collaterals.append(collateral_row(cid, lid, int(principal/0.75)))

        balance = principal
        cum_prin = 0
        cum_int = 0

        for inst in range(1, tenor+1):  # all 12 due
            due = (datetime(2025,4,1) + relativedelta(months=inst)).strftime("%Y-%m-%d")
            month = (datetime(2025,4,1) + relativedelta(months=inst)).strftime("%Y-%m")
            int_comp = round(balance * r_m, 2)
            prin_comp = round(emi - int_comp, 2)
            close_sched = round(balance - prin_comp, 2)
            if inst == tenor:
                prin_comp = round(balance, 2)
                close_sched = 0.0

            if behavior == "prepay_150pct":
                actual_amt = round(emi * 1.5, 2)
                # Extra goes to principal
                i_pay = int_comp
                extra = actual_amt - emi
                p_pay = round(prin_comp + extra, 2)
                if p_pay > balance:
                    p_pay = balance
                    actual_amt = round(p_pay + i_pay, 2)
                close_bal = round(balance - p_pay, 2)
                if close_bal < 0:
                    close_bal = 0
                status = "Paid"
                inst_dpd = 0
                inst_bkt = "Current"
                actual_date = due

            elif behavior == "zero_payment":
                actual_amt = 0
                i_pay = 0
                p_pay = 0
                close_bal = balance
                status = "Overdue"
                inst_dpd = min(inst * 30, 365)
                inst_bkt = "DPD 90+" if inst_dpd > 90 else \
                           "DPD 61-90" if inst_dpd > 60 else \
                           "DPD 31-60" if inst_dpd > 30 else \
                           "DPD 1-30" if inst_dpd > 0 else "Current"
                actual_date = ""

            elif behavior == "full_pay":
                actual_amt = emi
                i_pay = int_comp
                p_pay = prin_comp
                close_bal = close_sched
                status = "Paid"
                inst_dpd = 0
                inst_bkt = "Current"
                actual_date = due

            elif behavior == "half_pay":
                actual_amt = round(emi * 0.5, 2)
                i_pay = round(min(int_comp, actual_amt), 2)
                p_pay = round(actual_amt - i_pay, 2)
                close_bal = round(balance - p_pay, 2)
                status = "Partial"
                inst_dpd = min(inst * 15, 120)  # partial causes some DPD
                inst_bkt = "DPD 90+" if inst_dpd > 90 else \
                           "DPD 61-90" if inst_dpd > 60 else \
                           "DPD 31-60" if inst_dpd > 30 else \
                           "DPD 1-30" if inst_dpd > 0 else "Current"
                actual_date = due

            elif behavior == "late_pay_45d":
                actual_amt = emi
                i_pay = int_comp
                p_pay = prin_comp
                close_bal = close_sched
                status = "Paid"
                inst_dpd = 45  # always 45 days late
                inst_bkt = "DPD 31-60"
                late = datetime.strptime(due, "%Y-%m-%d") + timedelta(days=45)
                actual_date = late.strftime("%Y-%m-%d")

            cum_prin = round(cum_prin + p_pay, 2)
            cum_int = round(cum_int + i_pay, 2)
            balance = close_bal

            total_sched_all += emi
            total_paid_all += actual_amt
            monthly_sched[month] = monthly_sched.get(month, 0) + emi
            monthly_paid[month] = monthly_paid.get(month, 0) + actual_amt

            txns.append(txn_row(
                f"SCH{i:04d}{inst:04d}", lid, inst, due, emi, prin_comp, int_comp,
                balance + p_pay, actual_amt, p_pay, i_pay, status,
                inst_dpd, inst_bkt, close_bal, cum_prin, cum_int,
                actual_date, "N" if status == "Paid" else "Y",
            ))

            colls.append(coll_row(
                f"CEV{i:04d}{inst:04d}", lid, month, inst,
                inst_dpd, inst_bkt,
                0 if status == "Paid" else round(emi - actual_amt, 2),
                0 if status == "Paid" else emi,
                balance, actual_amt,
                "Normal" if inst_dpd == 0 else "Soft Collection",
            ))

        # Final loan state
        if behavior == "zero_payment":
            dpd_final, bkt_final = 365, "DPD 90+"
        elif behavior == "half_pay":
            dpd_final, bkt_final = 120, "DPD 90+"
        elif behavior == "late_pay_45d":
            dpd_final, bkt_final = 45, "DPD 31-60"
        elif behavior == "prepay_150pct":
            dpd_final, bkt_final = 0, "Current"
        else:
            dpd_final, bkt_final = 0, "Current"

        loans.append(loan_row(
            lid, bid, cid, principal, rate, tenor, disb, dpd=dpd_final, dpd_bucket=bkt_final,
            status="Active", paid_prin=cum_prin, paid_int=cum_int, emi=emi,
            outstanding=balance, n_installments_due=12,
            npa_date="2025-07-01" if dpd_final >= 90 else "",
        ))
        loan_data[f"L{i}"] = {
            "behavior": behavior, "outstanding": round(balance, 2),
            "dpd": dpd_final, "bucket": bkt_final,
            "total_paid": round(cum_prin + cum_int, 2),
        }

    write_csv(f"{d}/01_Borrowers.csv", borrowers)
    write_csv(f"{d}/02_Collateral.csv", collaterals)
    write_csv(f"{d}/03_Loan_Facilities.csv", loans)
    write_csv(f"{d}/04_Payment_Schedule_Transactions.csv", txns)
    write_csv(f"{d}/05_Collections.csv", colls)

    # CE calculations
    overall_ce = round(total_paid_all / total_sched_all * 100, 4) if total_sched_all > 0 else 0
    monthly_ce = {m: round(monthly_paid.get(m,0)/monthly_sched[m]*100, 4) for m in sorted(monthly_sched.keys())}

    gt = {
        "loan_details": loan_data,
        "M1": {
            "active_loan_count": 6,
            "note": "Mix of 6 loans with extreme behaviors",
        },
        "M2": {
            "description": "POS by DPD: Current (L1 prepay + L3 large + L4 small), DPD 31-60 (L6 late), DPD 90+ (L2 zero + L5 half)"
        },
        "M3": {
            "overall_ce_pct": overall_ce,
            "monthly_ce": monthly_ce,
            "total_scheduled": round(total_sched_all, 2),
            "total_paid": round(total_paid_all, 2),
            "description": f"CE mix: prepay boosts CE, zero-pay drags it. Overall ~{overall_ce:.1f}%",
        },
        "edge_cases_covered": [
            "Prepayment > 100% EMI (L1)",
            "Zero payments / total default (L2)",
            "Very large loan 50Cr (L3)",
            "Very small loan 10K (L4)",
            "Partial payer 50% (L5)",
            "Consistently late payer 45 days (L6)",
        ],
    }
    json.dump(gt, open(f"{d}/ground_truth.json","w"), indent=2)
    print(f"  Ground truth → {d}/ground_truth.json")
    return d


if __name__ == "__main__":
    d1 = gen_test_case_1()
    d2 = gen_test_case_2()
    d3 = gen_test_case_3()
    print(f"\n✅ All 3 test datasets generated:")
    print(f"   {d1}")
    print(f"   {d2}")
    print(f"   {d3}")
