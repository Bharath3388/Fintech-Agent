"""
Agentic Pipeline State — LangGraph TypedDict state
===================================================
This is the central state that flows through the LangGraph graph.
Every node reads from and writes to this shared state.
"""

from __future__ import annotations
from typing import TypedDict, Any, Annotated
import operator


class FileInfo(TypedDict):
    filepath: str
    filename: str
    columns: list[str]
    row_count: int
    dtypes: dict[str, str]
    sample_values: dict[str, list[str]]  # col -> first 5 values
    null_pcts: dict[str, float]


class FieldMapping(TypedDict):
    canonical: str        # Standard name e.g. "loan_id"
    file: str             # Which CSV
    column: str           # Actual column name in CSV
    confidence: str       # "high" / "medium" / "derived"
    reasoning: str        # LLM's explanation for this mapping


class SchemaResult(TypedDict):
    loan_file: str
    transaction_file: str
    borrower_file: str
    collateral_file: str
    collections_file: str
    field_mappings: dict[str, FieldMapping]  # canonical -> mapping
    unmapped_fields: list[str]
    computable_metrics: list[str]             # e.g. ["M1", "M2"]
    non_computable_metrics: dict[str, str]    # e.g. {"M3": "no txn data"}
    llm_reasoning: str  # Full LLM reasoning trace


class ValidationResult(TypedDict):
    passed: bool
    total_loans: int
    total_transactions: int
    errors: list[dict]
    warnings: list[dict]
    llm_analysis: str  # LLM's data quality assessment


class MetricResultItem(TypedDict):
    metric_id: str
    name: str
    status: str        # "ok" / "partial" / "not_available" / "error"
    data: Any
    llm_insight: str   # LLM's interpretation of the metric


class AgentState(TypedDict):
    """Full pipeline state for LangGraph."""
    # Input — one or more absolute paths to CSV files
    csv_paths: list[str]

    # File discovery
    files: list[str]
    file_profiles: dict[str, FileInfo]

    # Schema Discovery Agent output
    schema: SchemaResult | None

    # Data loaded in memory (DataFrames serialised as needed)
    data_loaded: bool

    # Validation Agent output
    validation: ValidationResult | None

    # Metric Computation Agent output
    metrics: dict[str, MetricResultItem]

    # Visualization Agent output — {metric_id: {plotly_json, html_snippet, ...}}
    charts: dict[str, Any]

    # Conversation / reasoning log
    messages: Annotated[list[str], operator.add]

    # Errors
    errors: Annotated[list[str], operator.add]
