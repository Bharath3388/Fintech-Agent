# Fintech-Agent — AI-Powered Loan Portfolio Analytics

A full-stack agentic application that autonomously analyses loan portfolio CSV data from Indian NBFCs. Upload your CSVs through a React web UI, watch real-time agent progress via Server-Sent Events, and get computed financial metrics with interactive Plotly charts — all powered by **Google Gemini + LangGraph**.

## What It Does

1. **Upload CSVs** via the React frontend (drag-and-drop or file picker)
2. **AI agents** autonomously discover file schemas, validate data quality, compute financial metrics, and generate visualisations — no manual column mapping needed
3. **Real-time progress** is streamed to the browser as each agent stage completes
4. **Results dashboard** displays computed metrics and interactive Plotly charts

## System Architecture

```
Browser (React + Vite)
        │  upload CSVs  /api/upload
        │  stream SSE   /api/analyze/stream
        ▼
FastAPI Backend  (src/api.py)
        │
        ▼
LangGraph State Machine
  ┌─────────────────────────────────────────────────────┐
  │  discover_files → map_schema → load_and_validate   │
  │                                    │               │
  │                          ┌─────────▼──────────┐   │
  │                          │  proceed / halt?   │   │
  │                          └────┬──────────┬────┘   │
  │                               │          │        │
  │                    ┌──────────▼──┐   ┌───▼──────┐ │
  │                    │compute_     │   │  halt    │ │
  │                    │metrics      │   │ pipeline │ │
  │                    └──────────┬──┘   └──────────┘ │
  │                               │                   │
  │                    ┌──────────▼──┐                │
  │                    │ visualise   │                │
  │                    └──────────┬──┘                │
  │                               │                   │
  │                    ┌──────────▼──┐                │
  │                    │final_report │                │
  │                    └─────────────┘                │
  └─────────────────────────────────────────────────────┘
```

### Agent Nodes

| Node | What it does |
|------|-------------|
| **discover_files** | Scans uploaded CSVs, reads 500-row samples, profiles columns/dtypes/nulls |
| **map_schema** | Gemini classifies each file's domain (loan/txn/borrower/…), maps columns to canonical fields, identifies computable metrics |
| **load_and_validate** | Loads full CSVs, computes quality stats (nulls, ranges, referential integrity); Gemini decides pass / warn / halt |
| **compute_metrics** | Gemini generates pandas code per metric; code executes on live DataFrames; self-corrects on failure |
| **visualise** | Generates interactive Plotly HTML charts for each computed metric |
| **final_report** | Aggregates all results into a structured JSON response |

## Supported Metrics

### Portfolio Metrics

| ID | Metric |
|----|--------|
| M1 | Portfolio Summary — POS, active count, weighted avg rate & tenor |
| M2 | POS by DPD Bucket |
| M3 | Collections Efficiency Time Series |
| M4 | CE% by DPD Bucket |
| M5–M8 | DPD Transition Matrices (POS & Count, INR & %) |
| M9 | Vintage Cohort Repayment |

### Borrower Metrics

| ID | Metric |
|----|--------|
| B1 | Borrower Demographics Summary |
| B2 | Credit Profile Analysis |
| B3 | Risk Segmentation Analysis |

> The LLM decides which metrics are feasible based on the files and columns you provide. Non-computable metrics are skipped with a reason.

## Setup

### 1. Clone & install Python dependencies

```bash
cd Fintech-Agent/src
pip install -r requirements.txt
```

### 2. Configure API key

```bash
cp .env.example .env
# Edit .env and set your Gemini API key
# Get one from: https://aistudio.google.com/apikey
```

### 3. Start the backend

```bash
cd src
uvicorn api:app --reload --port 8000
```

### 4. Start the frontend

```bash
cd frontend
npm install
npm run dev
# Opens at http://localhost:5173
```

### 5. CLI usage (no frontend needed)

```bash
cd src
python run_agentic.py "../Medium Size data Set/"
python run_agentic.py "../Medium Size data Set/01_Borrowers.csv"
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/upload` | Upload one or more CSV files; returns saved paths |
| `POST` | `/analyze` | Run full pipeline; returns JSON result |
| `POST` | `/analyze/stream` | Run pipeline with SSE progress events + final result |
| `GET` | `/health` | Liveness check |

## Project Structure

```
Fintech-Agent/
├── src/
│   ├── api.py                  # FastAPI app — upload, analyze, SSE streaming
│   ├── run_agentic.py          # CLI entry point
│   ├── requirements.txt
│   ├── agentic/
│   │   ├── graph.py            # LangGraph StateGraph wiring
│   │   ├── state.py            # TypedDict state definitions
│   │   ├── agent_schema.py     # Schema Discovery agent
│   │   ├── agent_validation.py # Data Validation agent
│   │   ├── agent_metrics.py    # Metric Computation agent (LLM code-gen)
│   │   ├── agent_visualizations.py  # Plotly chart generation
│   │   ├── charts.py           # Chart helpers
│   │   ├── llm_config.py       # Gemini model config
│   │   └── prompts.py          # All LLM prompt templates
│   └── core/
│       ├── models.py           # Pydantic models
│       ├── field_definitions.py
│       └── logger.py           # Coloured terminal logger
├── frontend/
│   ├── src/
│   │   ├── App.jsx             # Main app — upload → stream → results
│   │   ├── components/
│   │   │   ├── UploadArea.jsx      # Drag-and-drop CSV upload
│   │   │   ├── ProgressTracker.jsx # Live SSE stage progress
│   │   │   ├── ResultsDashboard.jsx# Metrics + chart display
│   │   │   └── MetricCard.jsx      # Individual metric card
│   │   └── index.css
│   ├── package.json
│   └── vite.config.js          # Proxies /api → localhost:8000
├── docs/                       # Domain knowledge & architecture docs
├── output_charts/              # Generated Plotly HTML charts
├── uploads/                    # Uploaded CSV storage
├── .env.example
└── .gitignore
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `GOOGLE_API_KEY` | — | Required — Gemini API key |
| `GEMINI_MODEL` | `gemini-2.0-flash` | Gemini model to use |

## Tech Stack

| Layer | Technology |
|-------|-----------|
| LLM | Google Gemini 2.0 Flash |
| Agent orchestration | LangGraph |
| LLM abstraction | LangChain |
| Backend API | FastAPI + SSE streaming |
| Data processing | pandas, numpy |
| Visualisation | Plotly |
| Frontend | React 18 + Vite |
| Styling | CSS (custom) |