"""Business Analyst Tool Kit: local spreadsheet analysis with visible assumptions."""

from .profile import profile, ProfileResult
from .workbook import inspect, TableCandidate, WorkbookInspection
from .schema import suggest_fields, FieldSuggestion

__all__ = ["profile", "ProfileResult", "inspect", "TableCandidate", "WorkbookInspection", "suggest_fields", "FieldSuggestion"]
