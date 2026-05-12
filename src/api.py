"""
FastAPI — Loan Portfolio Analytics Agent
=========================================
POST /analyze        { "csv_paths": [...] }  → full JSON result
POST /analyze/stream { "csv_paths": [...] }  → SSE progress + final result
POST /upload         multipart CSV upload    → returns saved paths
GET  /health         liveness check
"""

from __future__ import annotations
import os
import json
import asyncio
import uuid
import tempfile
import shutil
import numpy as np
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fastapi import FastAPI, HTTPException, UploadFile, File, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator

from dotenv import load_dotenv
load_dotenv()

# Make sure src/ is importable
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agentic.graph import run_pipeline
from agentic.agent_chat import answer_question
from auth import (
    init_db, signup_user, login_user, get_current_user,
    SignupRequest, LoginRequest, AuthResponse,
)

# ── In-memory session store (pipeline results keyed by session_id) ─────────
# Stores the serialised result dict so the chat agent can reference it later.
_session_store: dict[str, dict] = {}

# ── App ────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Fintech Loan Portfolio Agent",
    description="AI-powered loan portfolio analytics using Google Gemini + LangGraph",
    version="1.0.0",
)

# CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pipeline runs are CPU/IO heavy — use a thread pool so the event loop stays free
_executor = ThreadPoolExecutor(max_workers=2)

# Initialize user database on startup
init_db()

# Upload directory for CSV files
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ── Request / Response models ──────────────────────────────────────────────
class ChatRequest(BaseModel):
    session_id: str
    question: str
    history: list[dict] = []


class AnalyzeRequest(BaseModel):
    csv_paths: list[str]

    @field_validator("csv_paths")
    @classmethod
    def at_least_one(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("csv_paths must contain at least one path")
        return v


class HealthResponse(BaseModel):
    status: str
    api_key_set: bool
    model: str


# ── JSON serialiser that handles numpy / pandas scalars ───────────────────
class _SafeEncoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, np.bool_):
            return bool(obj)
        try:
            # pandas Timestamp, Period, etc.
            return str(obj)
        except Exception:
            return super().default(obj)


def _serialize(data: Any) -> Any:
    """Round-trip through JSON with safe encoder to strip numpy types."""
    return json.loads(json.dumps(data, cls=_SafeEncoder))


# ── Auth Routes ────────────────────────────────────────────────────────────
@app.post("/signup", response_model=AuthResponse)
def signup(req: SignupRequest):
    return signup_user(req)


@app.post("/login", response_model=AuthResponse)
def login(req: LoginRequest):
    return login_user(req)


@app.get("/me")
def me(user: dict = Depends(get_current_user)):
    return user


# ── Routes ─────────────────────────────────────────────────────────────────
@app.get("/health", response_model=HealthResponse)
def health():
    api_key = os.getenv("GOOGLE_API_KEY", "")
    return HealthResponse(
        status="ok",
        api_key_set=bool(api_key and api_key != "your_gemini_api_key_here"),
        model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
    )


@app.post("/analyze")
async def analyze(request: AnalyzeRequest, user: dict = Depends(get_current_user)):
    # ── Validate paths before handing off to the agent ────────────────
    bad = [p for p in request.csv_paths if not os.path.isfile(p)]
    if bad:
        raise HTTPException(
            status_code=422,
            detail=[{"path": p, "error": "File not found"} for p in bad],
        )

    # Check API key early
    api_key = os.getenv("GOOGLE_API_KEY", "")
    if not api_key or api_key == "your_gemini_api_key_here":
        raise HTTPException(
            status_code=503,
            detail="GOOGLE_API_KEY not configured. Set it in .env and restart.",
        )

    # ── Run pipeline in thread pool (blocking LLM calls) ──────────────
    loop = asyncio.get_event_loop()
    try:
        final_state = await loop.run_in_executor(
            _executor,
            lambda: run_pipeline(request.csv_paths),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline error: {e}")

    # ── Build clean response ───────────────────────────────────────────
    schema = final_state.get("schema") or {}
    validation = final_state.get("validation") or {}
    metrics_raw = final_state.get("metrics") or {}

    metrics_out = {}
    for mid, m in metrics_raw.items():
        metrics_out[mid] = {
            "metric_id": m["metric_id"],
            "name": m["name"],
            "status": m["status"],
            "data": _serialize(m.get("data")),
            "llm_insight": m.get("llm_insight", ""),
        }

    response = {
        "input_files": [os.path.basename(p) for p in request.csv_paths],
        "schema": {
            "loan_file": schema.get("loan_file", ""),
            "transaction_file": schema.get("transaction_file", ""),
            "borrower_file": schema.get("borrower_file", ""),
            "collateral_file": schema.get("collateral_file", ""),
            "collections_file": schema.get("collections_file", ""),
            "fields_mapped": len(schema.get("field_mappings", {})),
            "field_mappings": {
                k: {
                    "file": v["file"],
                    "column": v["column"],
                    "confidence": v["confidence"],
                    "reasoning": v.get("reasoning", ""),
                }
                for k, v in schema.get("field_mappings", {}).items()
            },
            "computable_metrics": schema.get("computable_metrics", []),
            "non_computable_metrics": schema.get("non_computable_metrics", {}),
            "llm_assessment": schema.get("llm_reasoning", ""),
        },
        "validation": {
            "passed": validation.get("passed", False),
            "total_loans": validation.get("total_loans", 0),
            "total_transactions": validation.get("total_transactions", 0),
            "errors": validation.get("errors", []),
            "warnings": validation.get("warnings", []),
            "llm_analysis": validation.get("llm_analysis", ""),
        },
        "metrics": metrics_out,
        "summary": {
            "total_metrics": len(metrics_out),
            "ok": sum(1 for m in metrics_out.values() if m["status"] == "ok"),
            "skipped": sum(1 for m in metrics_out.values() if m["status"] == "not_available"),
            "errors": sum(1 for m in metrics_out.values() if m["status"] == "error"),
        },
        "agent_log": final_state.get("messages", []),
        "pipeline_errors": final_state.get("errors", []),
    }

    # ── Generate session_id and cache state for chat agent ────────────
    session_id = str(uuid.uuid4())[:12]
    _session_store[session_id] = {
        "schema":     response.get("schema"),
        "validation": response.get("validation"),
        "metrics":    metrics_out,
    }
    response["session_id"] = session_id

    # ── Interactive charts (generated by Visualization Agent via LLM) ──
    charts_raw = final_state.get("charts") or {}
    charts_out = {}
    for mid, chart_info in charts_raw.items():
        if "error" in chart_info:
            charts_out[mid] = {"error": chart_info["error"]}
        else:
            charts_out[mid] = {
                "plotly_json": chart_info.get("plotly_json"),
                "html_snippet": chart_info.get("html_snippet", ""),
                "html_path": chart_info.get("html_path", ""),
            }

    response["charts"] = charts_out
    response["summary"]["charts_generated"] = len([c for c in charts_out.values() if "error" not in c])

    return JSONResponse(content=_serialize(response))


# ── File Upload ────────────────────────────────────────────────────────────
@app.post("/upload")
async def upload_files(files: list[UploadFile] = File(...), user: dict = Depends(get_current_user)):
    """Upload CSV files and return their saved paths."""
    session_id = uuid.uuid4().hex[:8]
    session_dir = os.path.join(UPLOAD_DIR, session_id)
    os.makedirs(session_dir, exist_ok=True)

    saved_paths = []
    for f in files:
        if not f.filename.endswith(".csv"):
            raise HTTPException(status_code=422, detail=f"Only CSV files allowed: {f.filename}")
        dest = os.path.join(session_dir, f.filename)
        with open(dest, "wb") as buf:
            shutil.copyfileobj(f.file, buf)
        saved_paths.append(dest)

    return {"session_id": session_id, "csv_paths": saved_paths, "count": len(saved_paths)}


# ── SSE Streaming Endpoint ─────────────────────────────────────────────────
@app.post("/analyze/stream")
async def analyze_stream(request: AnalyzeRequest, user: dict = Depends(get_current_user)):
    """Run the pipeline and stream progress via Server-Sent Events."""
    bad = [p for p in request.csv_paths if not os.path.isfile(p)]
    if bad:
        raise HTTPException(
            status_code=422,
            detail=[{"path": p, "error": "File not found"} for p in bad],
        )

    api_key = os.getenv("GOOGLE_API_KEY", "")
    if not api_key or api_key == "your_gemini_api_key_here":
        raise HTTPException(status_code=503, detail="GOOGLE_API_KEY not configured.")

    import threading
    import queue

    progress_queue: queue.Queue = queue.Queue()

    def run_with_sse():
        # Use thread-local SSE queue (no global monkey-patching)
        from core.logger import set_sse_queue
        set_sse_queue(progress_queue)
        try:
            result = run_pipeline(request.csv_paths)
            progress_queue.put({"type": "complete", "data": result})
        except Exception as e:
            progress_queue.put({"type": "pipeline_error", "error": str(e)})
        finally:
            set_sse_queue(None)
            progress_queue.put(None)  # Sentinel

    # Start pipeline in a thread
    thread = threading.Thread(target=run_with_sse, daemon=True)
    thread.start()

    # Generate a stable session_id for this analysis run
    session_id = str(uuid.uuid4())[:12]

    async def event_generator():
        loop = asyncio.get_event_loop()
        while True:
            try:
                # Long timeout: LLM calls can take minutes per metric
                event = await loop.run_in_executor(
                    None, lambda: progress_queue.get(timeout=600)
                )
            except Exception:
                break

            if event is None:
                break

            if event["type"] == "complete":
                # Build final response same as /analyze
                final_state = event["data"]
                result_payload = _build_response(final_state, request.csv_paths)
                result_payload["session_id"] = session_id
                # Cache state for the chat agent (keep only the fields it needs)
                _session_store[session_id] = {
                    "schema":     result_payload.get("schema"),
                    "validation": result_payload.get("validation"),
                    "metrics":    result_payload.get("metrics"),
                }
                yield f"event: result\ndata: {json.dumps(_serialize(result_payload), cls=_SafeEncoder)}\n\n"
            elif event["type"] == "pipeline_error":
                yield f"event: error\ndata: {json.dumps({'error': event['error']})}\n\n"
            else:
                yield f"event: progress\ndata: {json.dumps(event)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Chat Endpoint ─────────────────────────────────────────────────────────
@app.post("/chat")
async def chat(request: ChatRequest, user: dict = Depends(get_current_user)):
    """Answer a natural-language question about the analysed portfolio."""
    state = _session_store.get(request.session_id)
    if not state:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{request.session_id}' not found. Run an analysis first.",
        )
    api_key = os.getenv("GOOGLE_API_KEY", "")
    if not api_key or api_key == "your_gemini_api_key_here":
        raise HTTPException(status_code=503, detail="GOOGLE_API_KEY not configured.")

    loop = asyncio.get_event_loop()
    try:
        answer = await loop.run_in_executor(
            _executor,
            lambda: answer_question(state, request.question, request.history),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat error: {e}")

    return {"answer": answer}


def _build_response(final_state: dict, csv_paths: list[str]) -> dict:
    """Build the JSON response dict from pipeline state."""
    schema = final_state.get("schema") or {}
    validation = final_state.get("validation") or {}
    metrics_raw = final_state.get("metrics") or {}

    metrics_out = {}
    for mid, m in metrics_raw.items():
        metrics_out[mid] = {
            "metric_id": m["metric_id"],
            "name": m["name"],
            "status": m["status"],
            "data": _serialize(m.get("data")),
            "llm_insight": m.get("llm_insight", ""),
        }

    charts_raw = final_state.get("charts") or {}
    charts_out = {}
    for mid, chart_info in charts_raw.items():
        if "error" in chart_info:
            charts_out[mid] = {"error": chart_info["error"]}
        else:
            charts_out[mid] = {
                "plotly_json": chart_info.get("plotly_json"),
                "html_snippet": chart_info.get("html_snippet", ""),
            }

    return {
        "input_files": [os.path.basename(p) for p in csv_paths],
        "schema": {
            "loan_file": schema.get("loan_file", ""),
            "transaction_file": schema.get("transaction_file", ""),
            "borrower_file": schema.get("borrower_file", ""),
            "collateral_file": schema.get("collateral_file", ""),
            "collections_file": schema.get("collections_file", ""),
            "fields_mapped": len(schema.get("field_mappings", {})),
            "field_mappings": {
                k: {
                    "file": v["file"],
                    "column": v["column"],
                    "confidence": v["confidence"],
                    "reasoning": v.get("reasoning", ""),
                }
                for k, v in schema.get("field_mappings", {}).items()
            },
            "computable_metrics": schema.get("computable_metrics", []),
            "non_computable_metrics": schema.get("non_computable_metrics", {}),
            "llm_assessment": schema.get("llm_reasoning", ""),
        },
        "validation": {
            "passed": validation.get("passed", False),
            "total_loans": validation.get("total_loans", 0),
            "total_transactions": validation.get("total_transactions", 0),
            "errors": validation.get("errors", []),
            "warnings": validation.get("warnings", []),
            "llm_analysis": validation.get("llm_analysis", ""),
        },
        "metrics": metrics_out,
        "summary": {
            "total_metrics": len(metrics_out),
            "ok": sum(1 for m in metrics_out.values() if m["status"] == "ok"),
            "skipped": sum(1 for m in metrics_out.values() if m["status"] == "not_available"),
            "errors": sum(1 for m in metrics_out.values() if m["status"] == "error"),
            "charts_generated": len([c for c in charts_out.values() if "error" not in c]),
        },
        "charts": charts_out,
        "agent_log": final_state.get("messages", []),
        "pipeline_errors": final_state.get("errors", []),
    }
