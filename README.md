# Fintech-Agent — AI-Powered Loan Portfolio Analytics

An **agentic workflow** built with **Google Gemini + LangChain + LangGraph** that autonomously analyses loan portfolio CSV data from Indian NBFCs. Instead of hard-coded rules, an LLM reasons about your data — classifying files, mapping columns, validating quality, and generating Python code to compute financial metrics.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        LangGraph State Graph                        │
│                                                                     │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────┐   │
│  │ discover_    │───▶│ map_schema   │───▶│ load_and_validate    │   │
│  │ files        │    │ (Gemini LLM) │    │ (Gemini LLM)         │   │
│  └──────────────┘    └──────────────┘    └──────────┬───────────┘   │
│                                                     │               │
│                                          ┌──────────▼───────────┐   │
│                                          │ Conditional Edge     │   │
│                                          │ proceed / halt       │   │
│                                          └───┬─────────────┬────┘   │
│                                              │             │        │
│                                    ┌─────────▼──┐    ┌─────▼─────┐  │
│                                    │ compute_   │    │   halt    │  │
│                                    │ metrics    │    │ pipeline  │  │
│                                    │(Gemini LLM)│    └───────────┘  │
│                                    └─────────┬──┘                   │
│                                              │                      │
│                                    ┌─────────▼──────┐               │
│                                    │ final_report   │               │
│                                    └────────────────┘               │
└─────────────────────────────────────────────────────────────────────┘
```

### Agent Nodes

| Node | What it does | LLM Role |
|------|-------------|----------|
| **discover_files** | Scans directory for CSVs, reads 500-row samples, profiles columns/dtypes/nulls | — (data only) |
| **map_schema** | Sends file profiles to Gemini | LLM classifies file domains (loan/txn/borrower/…), maps columns to canonical fields, assesses which metrics are computable |
| **load_and_validate** | Loads full CSVs, computes quality stats (nulls, ranges, distributions, referential integrity) | LLM reviews stats and decides pass/fail with error/warning details |
| **compute_metrics** | For each computable metric, sends schema to Gemini | LLM generates Python/pandas code per metric; code is executed on loaded DataFrames; if it fails, LLM self-corrects |
| **final_report** | Prints summary of all results | — |

## Supported Metrics

### Portfolio Metrics (require loan + transaction data)

| ID | Metric | Required Data |
|----|--------|---------------|
| M1 | Portfolio Summary (POS, Active Count, Wtd Avg Rate/Tenor) | Loan file |
| M2 | POS by DPD Bucket | Loan file |
| M3 | Collections Efficiency Time Series | Transaction file |
| M4 | CE% by DPD Bucket | Transaction file |
| M5–M8 | DPD Transition Matrices (POS & Count, INR & %) | Transaction file |
| M9 | Vintage Cohort Repayment | Loan + Transaction files |

### Borrower Metrics (work with borrower data alone)

| ID | Metric | Required Data |
|----|--------|---------------|
| B1 | Borrower Demographics Summary | Borrower file |
| B2 | Credit Profile Analysis | Borrower file |
| B3 | Risk Segmentation Analysis | Borrower file |

> The LLM decides which metrics are feasible based on what files/columns you provide. Missing data is handled gracefully — non-computable metrics are skipped with a reason.

## Setup

### 1. Clone & install

```bash
cd Fintech-Agent/src
pip install -r requirements.txt
```

### 2. Configure API key

```bash
cp .env.example .env
# Edit .env and paste your Gemini API key
# Get one from: https://aistudio.google.com/apikey
```

### 3. Run

```bash
# With a directory of CSVs
python run_agentic.py "../Large data set/"

# With a single CSV file
python run_agentic.py "../Medium Size data Set/01_Borrowers.csv"
```

## Project Structure

```
src/
├── run_agentic.py              # Entry point — accepts file or directory
├── requirements.txt            # Python dependencies
├── agentic/
│   ├── __init__.py
│   ├── llm_config.py           # Gemini LLM configuration (model, API key)
│   ├── state.py                # LangGraph TypedDict state definitions
│   ├── prompts.py              # All prompt templates (schema, validation, metrics)
│   ├── agent_schema.py         # Schema Discovery Agent (file profiling + LLM mapping)
│   ├── agent_validation.py     # Data Validation Agent (quality stats + LLM assessment)
│   ├── agent_metrics.py        # Metric Computation Agent (LLM code generation + execution)
│   └── graph.py                # LangGraph StateGraph wiring + orchestration
├── core/
│   └── logger.py               # Structured terminal logging with colours
.env.example                    # API key template
.gitignore                      # Ignores .env, __pycache__
docs/                           # Domain knowledge documentation
```

## How It Works

1. **You provide CSV(s)** — one file or a full directory. The agent handles any count.

2. **Schema Discovery Agent** profiles each CSV (columns, types, samples, nulls) and sends the profile to **Gemini**, which reasons about:
   - What domain each file belongs to (loan, transaction, borrower, collateral, collections)
   - Which column maps to which canonical field (e.g. `prin_outstanding` → `current_pos`)
   - Which metrics are computable given the available data

3. **Validation Agent** loads the full data, computes quality statistics (null rates, value ranges, DPD distributions, referential integrity), and sends them to **Gemini** for assessment. The LLM decides whether to proceed, proceed with caution, or halt.

4. **Metric Computation Agent** iterates over computable metrics. For each one, it sends the schema mapping + metric definition to **Gemini**, which **generates executable Python/pandas code**. The code runs on the loaded DataFrames. If execution fails, the LLM reviews the error and generates a fix (self-correction). After computation, the LLM also interprets the results.

5. **Final Report** summarises all results, LLM insights, and agent activity.

## Configuration

| Env Variable | Default | Description |
|-------------|---------|-------------|
| `GOOGLE_API_KEY` | — | Required. Gemini API key |
| `GEMINI_MODEL` | `gemini-2.0-flash` | Model to use |

## Tech Stack

- **Python 3.12+**
- **Google Gemini 2.0 Flash** — LLM for reasoning, code generation, and data interpretation
- **LangChain** — LLM abstraction and message handling
- **LangGraph** — State graph orchestration with conditional edges
- **pandas / numpy** — Data loading and metric computation