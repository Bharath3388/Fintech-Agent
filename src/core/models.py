"""
Data models — typed dictionaries for state passing between agents.
Designed to map directly to LangGraph state when migrated.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class FileProfile:
    """Profile of a single CSV file."""
    filepath: str
    filename: str
    columns: list[str]
    row_count: int
    sample_data: dict[str, list]       # col -> first 5 values
    dtypes: dict[str, str]             # col -> inferred dtype
    null_pcts: dict[str, float]        # col -> null %
    unique_counts: dict[str, int]      # col -> nunique
    domain: str = ""                   # loan / transaction / borrower / collateral / collections


@dataclass
class FieldMapping:
    """Mapping from a canonical field to an actual CSV column."""
    canonical: str          # our standard field name
    file: str               # which CSV file
    column: str             # actual column name in that file
    confidence: float       # 0-1 match confidence
    method: str             # "exact" | "fuzzy" | "derived"
    derivation: str = ""    # formula if method == "derived"


@dataclass
class SchemaMapping:
    """Complete schema mapping for an uploaded dataset."""
    loan_file: str = ""
    transaction_file: str = ""
    borrower_file: str | None = None
    collateral_file: str | None = None
    collections_file: str | None = None
    field_map: dict[str, FieldMapping] = field(default_factory=dict)
    unmapped_fields: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class ValidationIssue:
    severity: str   # "error" | "warning" | "info"
    category: str   # "completeness" | "integrity" | "range" | "temporal"
    field: str
    message: str
    affected_rows: int = 0


@dataclass
class ValidationReport:
    issues: list[ValidationIssue] = field(default_factory=list)
    total_loans: int = 0
    total_transactions: int = 0
    passed: bool = True

    @property
    def error_count(self):
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warning_count(self):
        return sum(1 for i in self.issues if i.severity == "warning")


@dataclass
class MetricResult:
    """Result of computing a single metric."""
    metric_id: str          # e.g. "M1", "M2"
    name: str               # human-readable metric name
    status: str             # "ok" | "partial" | "not_available" | "error"
    data: Any = None        # DataFrame or dict with computed values
    missing_fields: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str = ""


@dataclass
class PipelineState:
    """
    Full pipeline state passed between agents.
    Maps to LangGraph State when migrated.
    """
    # Input
    input_dir: str = ""
    files: list[str] = field(default_factory=list)

    # Schema Discovery output
    file_profiles: dict[str, FileProfile] = field(default_factory=dict)
    schema: SchemaMapping | None = None

    # Validation output
    validation: ValidationReport | None = None

    # Loaded data (DataFrames stored by domain)
    data: dict[str, Any] = field(default_factory=dict)  # "loans" -> DataFrame, etc.

    # Metric Computation output
    metrics: dict[str, MetricResult] = field(default_factory=dict)

    # Errors
    errors: list[str] = field(default_factory=list)
