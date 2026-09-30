"""Business Analyst Tool Kit: local spreadsheet analysis with visible assumptions."""

from .profile import profile, ProfileResult
from .workbook import inspect, TableCandidate, WorkbookInspection
from .schema import suggest_fields, FieldSuggestion
from .prep import prepare, PrepResult
from .audit import audit, AuditResult, AuditFinding
from .metrics import MetricCatalog, MetricDefinition
from .results import AnalysisResult
from .performance import reconcile, variance
from .journeys import funnel, cohorts, process_bottlenecks
from .decisions import pricing, experiment, forecast
from .requirements import meeting_assistant, traceability
from .reporting import insight_report
from .recurring import save_setup, run_saved

__all__ = ["profile", "ProfileResult", "inspect", "TableCandidate", "WorkbookInspection", "suggest_fields", "FieldSuggestion",
           "prepare", "PrepResult", "audit", "AuditResult", "AuditFinding", "MetricCatalog", "MetricDefinition",
           "AnalysisResult", "reconcile", "variance", "funnel", "cohorts", "process_bottlenecks",
           "pricing", "experiment", "forecast", "meeting_assistant", "traceability", "insight_report",
           "save_setup", "run_saved"]
