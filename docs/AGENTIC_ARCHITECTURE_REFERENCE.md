# Agentic Architecture — Design Reference

## Overview

This document provides domain knowledge for implementing the **Agentic Architecture** required by the Parse.ai case study. The system must use AI agents that orchestrate data ingestion, transformation, metric computation, and visualisation.

---

## 1. Agent Architecture Design

### 1.1 Required Agents

```
┌─────────────────────────────────────────────────────────────────┐
│                        ORCHESTRATOR                              │
│  (Coordinates agents, manages state, handles errors, routes)     │
└─────────┬──────────┬──────────┬──────────┬──────────┬───────────┘
          │          │          │          │          │
          ▼          ▼          ▼          ▼          ▼
┌─────────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌───────────┐
│   Schema    │ │  Data   │ │ Metric  │ │  Viz    │ │Interaction│
│  Discovery  │ │Validation│ │Compute  │ │  Agent  │ │   Agent   │
│   Agent     │ │  Agent  │ │  Agent  │ │         │ │           │
└─────────────┘ └─────────┘ └─────────┘ └─────────┘ └───────────┘
```

### 1.2 Agent Responsibilities

#### Schema Discovery Agent
**Purpose**: Read uploaded CSVs, infer schema, map columns to canonical data model.

**Tools**:
- File reader (read CSV headers + sample rows)
- LLM reasoning (semantic column matching)
- Statistical profiler (data type inference, null rates, value distributions)

**Process**:
1. Read file(s) — detect encoding, delimiter, header row
2. Profile each column: data type, cardinality, null%, sample values, min/max
3. Use LLM to semantically match columns to canonical fields
4. Output: Column mapping JSON + confidence scores
5. Handle multi-file scenarios (detect relationships via common keys)

**Key Design Decision**: Must NOT hard-code schema assumptions. The agent must work with:
- Different column names (e.g., "loan_id" vs "account_no" vs "facility_id")
- Different date formats (DD-MM-YYYY, YYYY/MM/DD, epoch timestamps)
- Merged vs split files (single CSV with all data vs multiple CSVs)
- Missing columns (gracefully handle absence of optional domains)

#### Data Validation Agent
**Purpose**: Ensure data quality before metric computation.

**Tools**:
- Data profiler
- Rule engine (validation rules)
- Report generator

**Validation Categories**:
```python
VALIDATION_RULES = {
    "completeness": [
        "loan_id not null",
        "disbursement_date not null",
        "sanctioned_amount > 0",
    ],
    "referential_integrity": [
        "all payment.loan_id exists in loans",
        "all schedule.loan_id exists in loans",
    ],
    "temporal_consistency": [
        "disbursement_date <= maturity_date",
        "payment_date >= disbursement_date",
        "due_dates are sequential",
    ],
    "value_ranges": [
        "0 < interest_rate < 50",
        "1 <= tenor_months <= 360",
        "pos <= sanctioned_amount",
    ],
    "duplicates": [
        "loan_id is unique in facility table",
        "no duplicate payment transactions",
    ],
}
```

#### Metric Computation Agent
**Purpose**: Compute all 17 portfolio metrics using exact formulas.

**Tools**:
- Pandas/DataFrame operations
- Date arithmetic functions
- Aggregation functions

**Design Principles**:
- Deterministic: Same input → same output always
- Documented: Each metric computation logs its formula and inputs
- Validated: Cross-checks (e.g., transition matrix rows sum to 100%)
- Parameterised: Time windows, filters passed as parameters

#### Visualisation Agent
**Purpose**: Render charts and tables in the dashboard UI.

**Tools**:
- Charting library (Plotly, Chart.js, Recharts, etc.)
- Table renderer
- Filter/control builder

**Requirements**:
- Interactive filters (Product, Region, City)
- Time period selectors
- Multiple views (Monthly/Quarterly toggle)
- Colour coding per DPD severity
- Data labels on all charts
- Export functionality

#### Interaction Agent
**Purpose**: Allow natural language Q&A about the displayed data.

**Tools**:
- LLM for natural language understanding
- Data query builder (translates questions to data lookups)
- Response formatter (text + mini-charts)

**Capabilities**:
- "What is the NPA rate for personal loans?"
- "Which region has the worst collections efficiency?"
- "Compare Q1 vs Q2 roll rates"
- "Why did DPD 1-30 bucket increase in March?"

---

## 2. Orchestrator Design Patterns

### 2.1 Sequential Pipeline (Basic)
```
Upload → Schema Discovery → Validation → Compute → Visualise
```

### 2.2 Event-Driven (Advanced)
```
Upload Event → Schema Agent
Schema Complete Event → Validation Agent
Validation Complete Event → Metric Agent
Metrics Ready Event → Viz Agent
User Query Event → Interaction Agent
Filter Change Event → Re-compute subset → Update Viz
```

### 2.3 State Management
```json
{
  "session_id": "uuid",
  "status": "computing_metrics",
  "uploaded_files": ["loan_tape_1.csv"],
  "schema_mapping": { "completed": true, "confidence": 0.95 },
  "validation_report": { "errors": 0, "warnings": 12 },
  "computed_metrics": [1, 2, 3, 4, 5],
  "pending_metrics": [6, 7, 8, 9],
  "active_filters": { "product": "all", "region": "all" },
  "error_log": []
}
```

---

## 3. Schema Discovery Strategy

### 3.1 Column Classification Approach

```python
# Step 1: Statistical profiling
profile = {
    "column_name": "disb_dt",
    "dtype": "object",
    "null_pct": 0.1,
    "unique_count": 245,
    "sample_values": ["2023-04-15", "2023-05-01", "2023-06-20"],
    "inferred_type": "date",
    "pattern": "YYYY-MM-DD"
}

# Step 2: Semantic matching via LLM
prompt = """
Given these CSV columns with their profiles, map each to the canonical field:
Column: 'disb_dt' (date type, 245 unique values, sample: 2023-04-15)
Canonical options: disbursement_date, maturity_date, payment_date, due_date
Best match: disbursement_date (confidence: 0.92)
"""

# Step 3: Validation
# Check that mapped dates make logical sense:
# disbursement_date < maturity_date for all records
```

### 3.2 Multi-File Detection
```python
# If multiple files uploaded:
# 1. Find common key columns (likely loan_id variants)
# 2. Determine cardinality relationships (1:1, 1:N, M:N)
# 3. Classify each file by primary domain:
#    - File with most unique loan_ids + amounts = Loan Facility
#    - File with repeating loan_ids + dates + amounts = Payments/Schedule
#    - File with demographic fields = Borrower Info
```

---

## 4. Technology Stack Options

### 4.1 Option A: Python + FastAPI + React
```
Backend:
- Python 3.11+
- FastAPI (API layer)
- Pandas (data processing)
- LangChain / LangGraph (agent orchestration)
- OpenAI / Anthropic API (LLM)

Frontend:
- React / Next.js
- Recharts / Plotly.js (visualisation)
- TailwindCSS (styling)

Database:
- SQLite or DuckDB (embedded, no setup)
- Redis (optional, for caching)
```

### 4.2 Option B: Python + Streamlit
```
Full Stack:
- Python 3.11+
- Streamlit (UI + backend)
- Pandas (data processing)
- Plotly (visualisation)
- CrewAI / AutoGen (agent framework)
- OpenAI API (LLM)
```

### 4.3 Option C: TypeScript Full-Stack
```
Backend:
- Node.js + TypeScript
- Express / Hono
- LangChain.js (agents)

Frontend:
- Next.js 14+
- Chart.js / D3.js
- shadcn/ui

Database:
- SQLite (better-sqlite3)
```

### 4.4 Agent Framework Options
| Framework | Pros | Cons |
|-----------|------|------|
| **LangChain/LangGraph** | Mature, great tooling | Complex, over-abstracted |
| **CrewAI** | Simple multi-agent | Less flexible |
| **AutoGen** | Microsoft-backed, conversational | Heavier |
| **Custom** | Full control, lightweight | More work |
| **Semantic Kernel** | .NET/Python, enterprise | Less community |

---

## 5. Key Design Decisions

### 5.1 Determinism Requirement
The document states: "All computation must be deterministic and reproducible for the same input data."

**Implication**: 
- LLM calls for schema discovery can be non-deterministic, but the FINAL mapping must be cached/stored
- Once schema is mapped, all metric computations use pure pandas/numpy operations (deterministic)
- Set random seeds if any sampling is used
- Use `temperature=0` for LLM calls where consistency matters

### 5.2 Schema-Agnostic Design
```python
# BAD: Hard-coded schema assumption
df['dpd'] = (df['snapshot_date'] - df['due_date']).dt.days

# GOOD: Schema-agnostic with dynamic mapping
mapping = schema_agent.get_mapping(uploaded_file)
due_date_col = mapping['due_date']  # Could be 'emi_due_dt' or 'payment_due_date'
df['dpd'] = (df['snapshot_date'] - df[due_date_col]).dt.days
```

### 5.3 Error Handling Strategy
```python
# Orchestrator error handling
try:
    schema = await schema_agent.discover(files)
except SchemaAmbiguityError as e:
    # Ask user for clarification
    return {"status": "needs_input", "question": e.message}
except DataQualityError as e:
    # Surface issues but continue where possible
    return {"status": "partial", "warnings": e.issues, "metrics": computed}
```

---

## 6. Data Pipeline Architecture

```
┌──────────┐     ┌──────────────┐     ┌───────────────┐     ┌──────────────┐
│  Upload  │────▶│    Schema    │────▶│   Canonical   │────▶│  Validated   │
│  Raw CSV │     │   Discovery  │     │  DataFrame(s) │     │    Data      │
└──────────┘     └──────────────┘     └───────────────┘     └──────┬───────┘
                                                                    │
                                                                    ▼
┌──────────────┐     ┌──────────────┐     ┌───────────────┐  ┌──────────────┐
│  Dashboard   │◀────│ Visualisation│◀────│    Metric     │◀─│  Snapshot    │
│     UI       │     │    Agent     │     │  Computation  │  │  Generator   │
└──────────────┘     └──────────────┘     └───────────────┘  └──────────────┘
```

### Snapshot Generation
The critical intermediate step: Generate month-end snapshots for each active loan.

```python
# For each month-end in the data range:
#   For each active loan at that date:
#     - Calculate POS
#     - Calculate DPD
#     - Assign DPD bucket
#     - Record EMI due and amount collected in that month

snapshots = []
for month_end in month_ends:
    for loan in active_loans_at(month_end):
        snapshots.append({
            'loan_id': loan.id,
            'snapshot_date': month_end,
            'pos': calculate_pos(loan, month_end),
            'dpd': calculate_dpd(loan, month_end),
            'dpd_bucket': assign_bucket(dpd),
            'emi_due': get_emi_due(loan, month_end),
            'collected': get_collected(loan, month_end),
        })
```

---

## 7. Testing Strategy

### 7.1 Metric Accuracy Testing
- Create synthetic loan tape with known expected outputs
- Verify each metric formula with hand-calculated results
- Edge cases: zero EMI months, loans at exact bucket boundaries, leap years

### 7.2 Schema Robustness Testing
- Provide Loan Tape 2 (different column names) — must produce same metrics (for same underlying data)
- Test with missing optional columns
- Test with combined vs split files

### 7.3 Visualisation Testing
- Verify chart matches data (spot-check values)
- Filter interactions update correctly
- Time period selectors work

---

*This document serves as the architectural reference for implementing the agentic loan portfolio analytics system.*
