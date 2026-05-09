"""
LangGraph Orchestrator — Agentic Workflow
==========================================
Defines the state graph that chains agents:

    discover_files → map_schema_with_llm → load_and_validate → compute_metrics → final_report

Each node is an LLM-powered agent that reads from and writes to shared AgentState.
"""

from __future__ import annotations
import os
import time
import json

from langgraph.graph import StateGraph, START, END

from agentic.state import AgentState
from agentic.agent_schema import discover_files, map_schema_with_llm
from agentic.agent_validation import load_and_validate
from agentic.agent_metrics import compute_metrics
from agentic.agent_visualizations import generate_visualizations
from core.logger import (
    log_banner, log_step_start, log_step_end,
    log_info, log_success, log_error, log_data, log_warn,
    reset_steps,
)

AGENT = "Orchestrator"


def should_continue_after_validation(state: AgentState) -> str:
    """Conditional edge: decide whether to proceed to metrics or halt."""
    validation = state.get("validation")
    if not validation:
        return "halt"

    # If LLM said halt, respect it
    errors = validation.get("errors", [])
    critical_errors = [e for e in errors if e.get("severity") == "error"]

    if len(critical_errors) > 3:
        return "halt"

    return "compute"


def final_report(state: AgentState) -> dict:
    """LangGraph node: Print final pipeline report."""
    reset_steps(AGENT)
    step, t0 = log_step_start(AGENT, "Generating final report")

    log_info(AGENT, "")
    log_info(AGENT, "=" * 70)
    log_info(AGENT, "  AGENTIC PIPELINE RESULTS SUMMARY")
    log_info(AGENT, "=" * 70)

    log_data(AGENT, "Input files", len(state.get("csv_paths", [])))
    for p in state.get("csv_paths", []):
        log_info(AGENT, f"  {os.path.basename(p)}")
    log_data(AGENT, "Files profiled", len(state.get("files", [])))

    schema = state.get("schema")
    if schema:
        log_data(AGENT, "Loan file", schema.get("loan_file", "?"))
        log_data(AGENT, "Transaction file", schema.get("transaction_file", "?"))
        if schema.get("borrower_file"):
            log_data(AGENT, "Borrower file", schema["borrower_file"])
        if schema.get("collateral_file"):
            log_data(AGENT, "Collateral file", schema["collateral_file"])
        if schema.get("collections_file"):
            log_data(AGENT, "Collections file", schema["collections_file"])
        log_data(AGENT, "Fields mapped (by LLM)", len(schema.get("field_mappings", {})))
        computable = schema.get("computable_metrics", [])
        non_computable = schema.get("non_computable_metrics", {})
        if computable:
            log_data(AGENT, "Computable metrics", ", ".join(computable))
        if non_computable:
            log_data(AGENT, "Non-computable metrics", ", ".join(f"{k}: {v}" for k, v in non_computable.items()))
        log_data(AGENT, "LLM Assessment", schema.get("llm_reasoning", "")[:150])

    validation = state.get("validation")
    if validation:
        status = "PASSED" if validation.get("passed") else "FAILED"
        log_data(AGENT, "Validation", status)
        log_data(AGENT, "  Errors", len(validation.get("errors", [])))
        log_data(AGENT, "  Warnings", len(validation.get("warnings", [])))

    metrics = state.get("metrics", {})
    if metrics:
        log_info(AGENT, "\nMetric Results:")
        ok_count = 0
        for mid in sorted(metrics.keys()):
            m = metrics[mid]
            status_icon = {"ok": "✓", "partial": "~", "not_available": "✗", "error": "✖"}
            icon = status_icon.get(m["status"], "?")
            log_info(AGENT, f"  [{icon}] {mid} — {m['name']}: {m['status'].upper()}")
            if m.get("llm_insight"):
                log_info(AGENT, f"      AI: {m['llm_insight'][:120]}")
            if m["status"] == "ok":
                ok_count += 1

        log_info(AGENT, f"\n  {ok_count}/{len(metrics)} metrics computed successfully")

    # Print agent conversation log
    messages = state.get("messages", [])
    if messages:
        log_info(AGENT, "\nAgent Activity Log:")
        for msg in messages:
            log_info(AGENT, f"  {msg}")

    log_info(AGENT, "=" * 70)
    log_step_end(AGENT, step, t0)

    return {"messages": [f"[{AGENT}] Pipeline complete"]}


def halt_pipeline(state: AgentState) -> dict:
    """LangGraph node: Called when validation fails critically."""
    log_error(AGENT, "Pipeline HALTED due to critical validation errors")
    log_error(AGENT, "Fix data issues and retry")
    return {"messages": [f"[{AGENT}] Pipeline HALTED"]}


def build_graph() -> StateGraph:
    """Build the LangGraph state graph."""

    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("discover_files", discover_files)
    graph.add_node("map_schema", map_schema_with_llm)
    graph.add_node("validate", load_and_validate)
    graph.add_node("compute_metrics", compute_metrics)
    graph.add_node("generate_visualizations", generate_visualizations)
    graph.add_node("final_report", final_report)
    graph.add_node("halt", halt_pipeline)

    # Add edges
    graph.add_edge(START, "discover_files")
    graph.add_edge("discover_files", "map_schema")
    graph.add_edge("map_schema", "validate")

    # Conditional: proceed or halt based on validation
    graph.add_conditional_edges(
        "validate",
        should_continue_after_validation,
        {
            "compute": "compute_metrics",
            "halt": "halt",
        },
    )

    graph.add_edge("compute_metrics", "generate_visualizations")
    graph.add_edge("generate_visualizations", "final_report")
    graph.add_edge("final_report", END)
    graph.add_edge("halt", END)

    return graph


def run_pipeline(csv_paths: list[str]):
    """Run the full agentic pipeline on the given CSV file paths."""
    log_banner(AGENT)
    log_info(AGENT, "Building LangGraph state graph...")
    log_info(AGENT, "Nodes: discover_files → map_schema(LLM) → validate(LLM) → compute_metrics(LLM) → final_report")
    log_info(AGENT, f"Input files: {[os.path.basename(p) for p in csv_paths]}")
    log_info(AGENT, "")

    graph = build_graph()
    app = graph.compile()

    initial_state: AgentState = {
        "csv_paths": csv_paths,
        "files": [],
        "file_profiles": {},
        "schema": None,
        "data_loaded": False,
        "validation": None,
        "metrics": {},
        "messages": [],
        "errors": [],
    }

    t0 = time.time()

    # Run the graph
    final_state = app.invoke(initial_state)

    elapsed = time.time() - t0
    log_banner(AGENT)
    log_success(AGENT, f"Agentic pipeline complete in {elapsed:.2f}s")

    return final_state
