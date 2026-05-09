# Metric Computation — Detailed Implementation Guide

## Overview
This document provides implementation-ready specifications for all 17 metrics required by the Parse.ai Loan Portfolio Analytics Dashboard.

---

## Prerequisites: Snapshot Table

Before computing metrics, build a **monthly snapshot table** — one row per loan per month-end.

```python
import pandas as pd
import numpy as np

def build_snapshot_table(loans_df, payments_df, schedule_df):
    """
    Build month-end snapshots for all active loans.
    
    Returns DataFrame with columns:
    - loan_id, snapshot_date, pos, dpd, dpd_bucket, 
    - emi_due_month, principal_due_month, interest_due_month,
    - amount_collected_month, principal_collected_month, interest_collected_month,
    - product_type, region, city, disbursement_date, interest_rate, 
    - maturity_date, disbursed_amount, loan_status
    """
    # Determine date range
    min_date = loans_df['disbursement_date'].min()
    max_date = payments_df['transaction_date'].max()
    
    # Generate month-end dates
    month_ends = pd.date_range(
        start=min_date, 
        end=max_date, 
        freq='ME'  # Month-End frequency
    )
    
    snapshots = []
    for month_end in month_ends:
        # Active loans at this month-end
        active = loans_df[
            (loans_df['disbursement_date'] <= month_end) &
            (loans_df['loan_status'].isin(['Active', 'active', 'ACTIVE']) | 
             loans_df['closure_date'].isna() |
             loans_df['closure_date'] > month_end)
        ]
        
        for _, loan in active.iterrows():
            # Calculate POS
            principal_paid = payments_df[
                (payments_df['loan_id'] == loan['loan_id']) &
                (payments_df['transaction_date'] <= month_end)
            ]['principal_collected'].sum()
            pos = loan['disbursed_amount'] - principal_paid
            
            # Calculate DPD
            unpaid_dues = schedule_df[
                (schedule_df['loan_id'] == loan['loan_id']) &
                (schedule_df['due_date'] <= month_end)
            ]
            # Check which dues are unpaid
            # ... (complex logic involving matching payments to dues)
            
            dpd = calculate_dpd(loan['loan_id'], month_end, schedule_df, payments_df)
            dpd_bucket = assign_dpd_bucket(dpd)
            
            # EMI due this month
            month_start = month_end.replace(day=1)
            emi_due = schedule_df[
                (schedule_df['loan_id'] == loan['loan_id']) &
                (schedule_df['due_date'] >= month_start) &
                (schedule_df['due_date'] <= month_end)
            ]['emi_due_amount'].sum()
            
            # Amount collected this month
            collected = payments_df[
                (payments_df['loan_id'] == loan['loan_id']) &
                (payments_df['transaction_date'] >= month_start) &
                (payments_df['transaction_date'] <= month_end)
            ]
            
            snapshots.append({
                'loan_id': loan['loan_id'],
                'snapshot_date': month_end,
                'pos': max(0, pos),
                'dpd': dpd,
                'dpd_bucket': dpd_bucket,
                'emi_due_month': emi_due,
                'amount_collected_month': collected['amount_received'].sum(),
                'principal_collected_month': collected['principal_collected'].sum(),
                'interest_collected_month': collected['interest_collected'].sum(),
                'product_type': loan['product_type'],
                'region': loan['region'],
                'city': loan['city'],
                'disbursement_date': loan['disbursement_date'],
                'interest_rate': loan['interest_rate'],
                'maturity_date': loan['maturity_date'],
                'disbursed_amount': loan['disbursed_amount'],
            })
    
    return pd.DataFrame(snapshots)


def assign_dpd_bucket(dpd):
    """Assign DPD to standard bucket."""
    if dpd == 0:
        return 'Current'
    elif dpd <= 30:
        return 'DPD 1-30'
    elif dpd <= 60:
        return 'DPD 31-60'
    elif dpd <= 90:
        return 'DPD 61-90'
    else:
        return 'DPD 90+'
```

---

## Metric 1: Portfolio Summary Table

```python
def compute_portfolio_summary(snapshot_df, snapshot_date=None):
    """
    Compute 5 KPIs at the latest (or specified) month-end.
    """
    if snapshot_date is None:
        snapshot_date = snapshot_df['snapshot_date'].max()
    
    latest = snapshot_df[snapshot_df['snapshot_date'] == snapshot_date]
    
    # 1. Principal Outstanding (INR Crore)
    pos_total = latest['pos'].sum() / 1e7  # Convert to Crore
    
    # 2. Interest Outstanding (INR Crore)
    # Interest accrued but not collected
    interest_outstanding = latest['interest_outstanding'].sum() / 1e7
    
    # 3. Number of Active Loans
    active_count = latest['loan_id'].nunique()
    
    # 4. Weighted Average Interest Rate
    weighted_rate = (
        (latest['interest_rate'] * latest['pos']).sum() / 
        latest['pos'].sum()
    )
    
    # 5. Weighted Average Remaining Tenor
    latest['remaining_tenor'] = (
        (latest['maturity_date'] - snapshot_date).dt.days / 30.44
    ).clip(lower=0)
    weighted_tenor = (
        (latest['remaining_tenor'] * latest['pos']).sum() / 
        latest['pos'].sum()
    )
    
    # Month-on-month delta
    prev_month = snapshot_date - pd.offsets.MonthEnd(1)
    prev = snapshot_df[snapshot_df['snapshot_date'] == prev_month]
    prev_pos = prev['pos'].sum() / 1e7 if len(prev) > 0 else None
    
    return {
        'snapshot_date': snapshot_date,
        'principal_outstanding_cr': round(pos_total, 2),
        'interest_outstanding_cr': round(interest_outstanding, 2),
        'active_loan_count': active_count,
        'weighted_avg_rate_pct': round(weighted_rate, 2),
        'weighted_avg_tenor_months': round(weighted_tenor, 1),
        'pos_mom_change_cr': round(pos_total - prev_pos, 2) if prev_pos else None,
        'pos_mom_change_pct': round((pos_total - prev_pos) / prev_pos * 100, 2) if prev_pos else None,
    }
```

---

## Metric 2: POS Distribution by DPD Bucket

```python
def compute_pos_by_dpd(snapshot_df, snapshot_date=None):
    """
    Bar chart data: POS distribution across DPD buckets.
    """
    if snapshot_date is None:
        snapshot_date = snapshot_df['snapshot_date'].max()
    
    latest = snapshot_df[snapshot_df['snapshot_date'] == snapshot_date]
    
    bucket_order = ['Current', 'DPD 1-30', 'DPD 31-60', 'DPD 61-90', 'DPD 90+']
    
    result = latest.groupby('dpd_bucket')['pos'].sum().reindex(bucket_order, fill_value=0)
    total_pos = result.sum()
    
    return pd.DataFrame({
        'dpd_bucket': bucket_order,
        'pos_inr': result.values,
        'pos_crore': (result.values / 1e7).round(2),
        'pct_of_total': (result.values / total_pos * 100).round(2),
    })
```

---

## Metric 3: Overall Collections Efficiency — Time Series

```python
def compute_collections_efficiency_timeseries(snapshot_df, view='monthly'):
    """
    Monthly/Quarterly collections efficiency.
    """
    if view == 'monthly':
        grouped = snapshot_df.groupby('snapshot_date').agg(
            emi_due=('emi_due_month', 'sum'),
            collected=('principal_collected_month', 'sum') + 
                     ('interest_collected_month', 'sum')  # principal + interest only
        )
    elif view == 'quarterly':
        snapshot_df['quarter'] = snapshot_df['snapshot_date'].dt.to_period('Q')
        grouped = snapshot_df.groupby('quarter').agg(
            emi_due=('emi_due_month', 'sum'),
            collected=('amount_collected_excl_charges', 'sum')
        )
    
    grouped['ce_rate'] = (grouped['collected'] / grouped['emi_due'] * 100).round(2)
    grouped['emi_due_crore'] = (grouped['emi_due'] / 1e7).round(2)
    grouped['collected_crore'] = (grouped['collected'] / 1e7).round(2)
    
    return grouped
```

---

## Metric 4: Collections Efficiency by DPD Bucket

```python
def compute_ce_by_dpd_bucket(snapshot_df, month):
    """
    Collections efficiency per DPD bucket for a selected month.
    DPD bucket = bucket at START of month (prior month-end).
    """
    # Get prior month-end bucket assignments
    prior_month = month - pd.offsets.MonthEnd(1)
    prior_snapshot = snapshot_df[snapshot_df['snapshot_date'] == prior_month][['loan_id', 'dpd_bucket']]
    prior_snapshot = prior_snapshot.rename(columns={'dpd_bucket': 'start_bucket'})
    
    # Get current month collections
    current = snapshot_df[snapshot_df['snapshot_date'] == month]
    merged = current.merge(prior_snapshot, on='loan_id', how='left')
    
    bucket_order = ['Current', 'DPD 1-30', 'DPD 31-60', 'DPD 61-90', 'DPD 90+']
    
    result = merged.groupby('start_bucket').agg(
        emi_due=('emi_due_month', 'sum'),
        collected=('amount_collected_excl_charges', 'sum')
    ).reindex(bucket_order)
    
    result['ce_rate'] = (result['collected'] / result['emi_due'] * 100).round(2)
    
    return result
```

---

## Metrics 5-8: Transition Matrices

```python
def compute_transition_matrix(snapshot_df, period_start, period_end, 
                               measure='pos', as_percentage=False):
    """
    Compute transition matrix between two dates.
    
    Parameters:
    - measure: 'pos' or 'count'
    - as_percentage: if True, normalize rows to 100%
    
    Returns: 5x5 (or 5x6 with 'Paid Off') DataFrame
    """
    bucket_order = ['Current', 'DPD 1-30', 'DPD 31-60', 'DPD 61-90', 'DPD 90+']
    
    # Get start state
    start = snapshot_df[snapshot_df['snapshot_date'] == period_start][
        ['loan_id', 'dpd_bucket', 'pos']
    ].rename(columns={'dpd_bucket': 'from_bucket', 'pos': 'start_pos'})
    
    # Get end state
    end = snapshot_df[snapshot_df['snapshot_date'] == period_end][
        ['loan_id', 'dpd_bucket', 'pos']
    ].rename(columns={'dpd_bucket': 'to_bucket', 'pos': 'end_pos'})
    
    # Merge — loans in start but not end = "Paid Off"
    merged = start.merge(end, on='loan_id', how='left')
    merged['to_bucket'] = merged['to_bucket'].fillna('Paid Off')
    
    all_buckets = bucket_order + ['Paid Off']
    
    if measure == 'pos':
        matrix = merged.pivot_table(
            index='from_bucket', columns='to_bucket',
            values='start_pos', aggfunc='sum', fill_value=0
        ).reindex(index=bucket_order, columns=all_buckets, fill_value=0)
    else:  # count
        matrix = merged.pivot_table(
            index='from_bucket', columns='to_bucket',
            values='loan_id', aggfunc='count', fill_value=0
        ).reindex(index=bucket_order, columns=all_buckets, fill_value=0)
    
    if as_percentage:
        row_totals = matrix.sum(axis=1)
        matrix = matrix.div(row_totals, axis=0) * 100
        matrix = matrix.round(1)
    
    # Add row/column totals
    matrix['Row Total'] = matrix.sum(axis=1)
    matrix.loc['Column Total'] = matrix.sum(axis=0)
    
    return matrix


def compute_transition_matrix_average(snapshot_df, months, measure='pos', as_percentage=False):
    """
    Compute N-month average transition matrix.
    """
    matrices = []
    for i in range(len(months) - 1):
        m = compute_transition_matrix(
            snapshot_df, months[i], months[i+1], 
            measure=measure, as_percentage=as_percentage
        )
        matrices.append(m)
    
    # Simple average
    avg_matrix = sum(matrices) / len(matrices)
    return avg_matrix.round(1 if as_percentage else 0)
```

---

## Metric 9: Principal Repayment Rate by Cohort

```python
def compute_vintage_repayment(loans_df, payments_df):
    """
    Cumulative principal repayment rate by disbursement cohort and MOB.
    """
    # Assign cohorts
    loans_df['cohort'] = loans_df['disbursement_date'].dt.to_period('M')
    
    results = []
    for cohort, cohort_loans in loans_df.groupby('cohort'):
        loan_ids = cohort_loans['loan_id'].tolist()
        total_disbursed = cohort_loans['disbursed_amount'].sum()
        
        # Get all payments for this cohort
        cohort_payments = payments_df[payments_df['loan_id'].isin(loan_ids)].copy()
        
        # Calculate MOB for each payment
        cohort_start = cohort.to_timestamp()
        cohort_payments['mob'] = (
            (cohort_payments['transaction_date'].dt.to_period('M') - cohort)
            .apply(lambda x: x.n)
        )
        
        # Cumulative principal by MOB
        cum_principal = cohort_payments.groupby('mob')['principal_collected'].sum().cumsum()
        
        for mob, cum_prin in cum_principal.items():
            results.append({
                'cohort': str(cohort),
                'mob': mob,
                'cum_principal_collected': cum_prin,
                'total_disbursed': total_disbursed,
                'repayment_rate_pct': round(cum_prin / total_disbursed * 100, 2)
            })
    
    return pd.DataFrame(results)
```

---

## Metric 10: Portfolio at Risk (PAR) — Delinquency Rate

```python
def compute_par_rates(snapshot_df):
    """
    PAR rates over time.
    """
    results = []
    for date, group in snapshot_df.groupby('snapshot_date'):
        total_pos = group['pos'].sum()
        results.append({
            'snapshot_date': date,
            'total_pos': total_pos,
            'par_0': group[group['dpd'] > 0]['pos'].sum() / total_pos * 100,
            'par_30': group[group['dpd'] > 30]['pos'].sum() / total_pos * 100,
            'par_60': group[group['dpd'] > 60]['pos'].sum() / total_pos * 100,
            'par_90': group[group['dpd'] > 90]['pos'].sum() / total_pos * 100,
        })
    
    return pd.DataFrame(results).round(2)
```

---

## Metric 11: Roll Rate Analysis

```python
def compute_roll_rates(snapshot_df):
    """
    Month-over-month roll rates (% moving to next worse bucket).
    """
    bucket_order = ['Current', 'DPD 1-30', 'DPD 31-60', 'DPD 61-90', 'DPD 90+']
    months = sorted(snapshot_df['snapshot_date'].unique())
    
    results = []
    for i in range(1, len(months)):
        prev = snapshot_df[snapshot_df['snapshot_date'] == months[i-1]][['loan_id', 'dpd_bucket', 'pos']]
        curr = snapshot_df[snapshot_df['snapshot_date'] == months[i]][['loan_id', 'dpd_bucket']]
        
        merged = prev.merge(curr, on='loan_id', suffixes=('_prev', '_curr'))
        
        for bucket_idx in range(len(bucket_order) - 1):
            from_bucket = bucket_order[bucket_idx]
            to_bucket = bucket_order[bucket_idx + 1]
            
            in_bucket = merged[merged['dpd_bucket_prev'] == from_bucket]
            rolled = in_bucket[in_bucket['dpd_bucket_curr'] == to_bucket]
            
            if len(in_bucket) > 0:
                roll_rate_count = len(rolled) / len(in_bucket) * 100
                roll_rate_pos = rolled['pos'].sum() / in_bucket['pos'].sum() * 100
            else:
                roll_rate_count = 0
                roll_rate_pos = 0
            
            results.append({
                'month': months[i],
                'from_bucket': from_bucket,
                'to_bucket': to_bucket,
                'roll_rate_count_pct': round(roll_rate_count, 2),
                'roll_rate_pos_pct': round(roll_rate_pos, 2),
            })
    
    return pd.DataFrame(results)
```

---

## Metric 12: NPA Rate & Movement

```python
def compute_npa_metrics(snapshot_df):
    """
    NPA formation and resolution tracking.
    """
    months = sorted(snapshot_df['snapshot_date'].unique())
    results = []
    
    for i, month in enumerate(months):
        current_month = snapshot_df[snapshot_df['snapshot_date'] == month]
        total_pos = current_month['pos'].sum()
        npa_pos = current_month[current_month['dpd'] > 90]['pos'].sum()
        
        gnpa_rate = npa_pos / total_pos * 100 if total_pos > 0 else 0
        
        # NPA additions/reductions (need prior month)
        if i > 0:
            prev_month = snapshot_df[snapshot_df['snapshot_date'] == months[i-1]]
            prev_npa_loans = set(prev_month[prev_month['dpd'] > 90]['loan_id'])
            curr_npa_loans = set(current_month[current_month['dpd'] > 90]['loan_id'])
            
            new_npas = curr_npa_loans - prev_npa_loans  # Additions
            cured_npas = prev_npa_loans - curr_npa_loans  # Reductions
            
            additions_pos = current_month[current_month['loan_id'].isin(new_npas)]['pos'].sum()
            reductions_pos = prev_month[prev_month['loan_id'].isin(cured_npas)]['pos'].sum()
        else:
            additions_pos = 0
            reductions_pos = 0
        
        results.append({
            'snapshot_date': month,
            'gnpa_rate_pct': round(gnpa_rate, 2),
            'npa_pos_crore': round(npa_pos / 1e7, 2),
            'additions_crore': round(additions_pos / 1e7, 2),
            'reductions_crore': round(reductions_pos / 1e7, 2),
        })
    
    return pd.DataFrame(results)
```

---

## Metric 13-17: Additional Metrics

```python
def compute_prepayment_rate(snapshot_df, loans_df):
    """Metric 13: Foreclosure/Prepayment analysis."""
    months = sorted(snapshot_df['snapshot_date'].unique())
    results = []
    
    for month in months:
        foreclosed_this_month = loans_df[
            (loans_df['closure_type'] == 'foreclosure') &
            (loans_df['closure_date'].dt.to_period('M') == month.to_period('M'))
        ]
        total_active = snapshot_df[snapshot_df['snapshot_date'] == month]
        
        results.append({
            'month': month,
            'foreclosure_count': len(foreclosed_this_month),
            'foreclosure_pos_crore': foreclosed_this_month['pos_at_closure'].sum() / 1e7,
            'foreclosure_rate_pct': len(foreclosed_this_month) / len(total_active) * 100,
        })
    
    return pd.DataFrame(results)


def compute_disbursement_trends(loans_df):
    """Metric 14: Disbursement trends."""
    loans_df['disb_month'] = loans_df['disbursement_date'].dt.to_period('M')
    
    return loans_df.groupby('disb_month').agg(
        count=('loan_id', 'count'),
        total_disbursed_crore=('disbursed_amount', lambda x: x.sum() / 1e7),
        avg_ticket_size=('disbursed_amount', 'mean'),
        avg_rate=('interest_rate', 'mean'),
        avg_tenor=('tenor_months', 'mean'),
    ).round(2)


def compute_concentration_risk(snapshot_df, snapshot_date=None):
    """Metric 15: Concentration by product/region."""
    if snapshot_date is None:
        snapshot_date = snapshot_df['snapshot_date'].max()
    
    latest = snapshot_df[snapshot_df['snapshot_date'] == snapshot_date]
    total_pos = latest['pos'].sum()
    
    by_product = latest.groupby('product_type')['pos'].sum() / total_pos * 100
    by_region = latest.groupby('region')['pos'].sum() / total_pos * 100
    by_city = latest.groupby('city')['pos'].sum() / total_pos * 100
    
    return {
        'by_product': by_product.round(2).to_dict(),
        'by_region': by_region.round(2).to_dict(),
        'by_city': by_city.round(2).to_dict(),
    }


def compute_yield_analysis(snapshot_df):
    """Metric 16: Portfolio yield."""
    monthly = snapshot_df.groupby('snapshot_date').agg(
        avg_pos=('pos', 'mean'),
        total_pos=('pos', 'sum'),
        interest_collected=('interest_collected_month', 'sum'),
    )
    
    monthly['monthly_yield_pct'] = (monthly['interest_collected'] / monthly['total_pos'] * 100).round(4)
    monthly['annualised_yield_pct'] = (monthly['monthly_yield_pct'] * 12).round(2)
    
    return monthly


def compute_bounce_rate(payments_df):
    """Metric 17: Payment bounce/failure rate."""
    if 'payment_status' not in payments_df.columns:
        return None  # Not available in this dataset
    
    monthly = payments_df.groupby(payments_df['transaction_date'].dt.to_period('M')).agg(
        total_presentations=('transaction_id', 'count'),
        bounced=('payment_status', lambda x: (x == 'bounced').sum()),
    )
    
    monthly['bounce_rate_pct'] = (monthly['bounced'] / monthly['total_presentations'] * 100).round(2)
    
    return monthly
```

---

## Filter Implementation

All metrics should support filtering:

```python
def apply_filters(snapshot_df, filters):
    """
    Apply user-selected filters to the snapshot dataframe.
    
    filters = {
        'product_type': ['Personal Loan', 'Vehicle Loan'],  # or None for all
        'region': ['North', 'West'],  # or None for all
        'city': ['Mumbai'],  # or None for all
    }
    """
    filtered = snapshot_df.copy()
    
    if filters.get('product_type'):
        filtered = filtered[filtered['product_type'].isin(filters['product_type'])]
    if filters.get('region'):
        filtered = filtered[filtered['region'].isin(filters['region'])]
    if filters.get('city'):
        filtered = filtered[filtered['city'].isin(filters['city'])]
    
    return filtered
```

---

## DPD Calculation — Detailed Algorithm

```python
def calculate_dpd(loan_id, snapshot_date, schedule_df, payments_df):
    """
    Calculate DPD for a loan at a given snapshot date.
    
    Logic:
    1. Get all scheduled instalments due on or before snapshot_date
    2. Get all payments made on or before snapshot_date
    3. Apply payments to dues in chronological order (FIFO)
    4. Find earliest unpaid/partially-paid instalment
    5. DPD = snapshot_date - earliest_unpaid_due_date (in days)
    """
    # Get scheduled dues
    dues = schedule_df[
        (schedule_df['loan_id'] == loan_id) &
        (schedule_df['due_date'] <= snapshot_date)
    ].sort_values('due_date')
    
    # Get payments
    payments = payments_df[
        (payments_df['loan_id'] == loan_id) &
        (payments_df['transaction_date'] <= snapshot_date)
    ].sort_values('transaction_date')
    
    # Total due vs total paid
    total_due = dues['emi_due_amount'].sum()
    total_paid = payments['amount_received'].sum()
    
    if total_paid >= total_due:
        return 0  # Fully current
    
    # Find earliest unpaid instalment using FIFO allocation
    cumulative_paid = payments['amount_received'].sum()
    cumulative_due = 0
    
    for _, due_row in dues.iterrows():
        cumulative_due += due_row['emi_due_amount']
        if cumulative_due > cumulative_paid:
            # This is the earliest unpaid instalment
            earliest_unpaid_date = due_row['due_date']
            dpd = (snapshot_date - earliest_unpaid_date).days
            return max(0, dpd)
    
    return 0
```

---

## Performance Optimisation Notes

1. **Vectorise DPD calculation**: Instead of per-loan loops, use cumulative sums and merge operations
2. **Pre-compute snapshots**: Build once, query many times
3. **Use DuckDB for large datasets**: Better performance than pandas for analytical queries
4. **Cache intermediate results**: Transition matrices are expensive; cache per time-window
5. **Lazy computation**: Only compute metrics when requested (not all 17 upfront)

---

*Implementation reference for Parse.ai Loan Portfolio Analytics — Metric Computation Agent*
