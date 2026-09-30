"""Uniform, source-linked analysis results and local exports."""

from dataclasses import dataclass, field
from html import escape
import json
from pathlib import Path
import re

import pandas as pd

from .workbook import inspect, read_table


def table(data: pd.DataFrame | str | Path, *, sheet: str | None = None,
          header_row: int | None = None, columns: dict[str, str] | None = None) -> pd.DataFrame:
    """Load a dataframe or a detected file table, with explicit schema mapping."""
    if isinstance(data, pd.DataFrame):
        frame = data.copy()
        if "_source_row" not in frame:
            frame.insert(0, "_source_row", range(2, len(frame) + 2))
    else:
        options = inspect(data).candidates
        options = [c for c in options if (sheet is None or c.sheet == sheet)
                   and (header_row is None or c.header_row == header_row)]
        if not options:
            raise ValueError("No matching table; choose a sheet and header row")
        if len(options) > 1 and options[0].score - options[1].score < 3 and (sheet is None or header_row is None):
            raise ValueError("Several tables are plausible; choose a sheet and header row")
        frame = read_table(data, options[0])
        frame.insert(0, "_source_sheet", options[0].sheet)
        frame.insert(0, "_source_file", Path(data).name)
    if columns:
        missing = set(columns) - set(frame)
        if missing:
            raise ValueError(f"Columns to map were not found: {', '.join(sorted(missing))}")
        frame = frame.rename(columns=columns)
        if frame.columns.duplicated().any():
            raise ValueError("Column mapping produces duplicate names")
    return frame


def require(frame: pd.DataFrame, *names: str) -> None:
    missing = [name for name in names if name not in frame]
    if missing:
        raise ValueError(f"Missing columns: {', '.join(missing)}")


def numeric(series: pd.Series, label: str) -> pd.Series:
    cleaned = series.astype(str).str.replace(r"[₹$£€,\s]", "", regex=True)
    cleaned = cleaned.str.replace(r"^\((.*)\)$", r"-\1", regex=True)
    values = pd.to_numeric(cleaned, errors="coerce")
    bad = series.notna() & values.isna()
    if bad.any():
        raise ValueError(f"{label}: {int(bad.sum())} values are not numbers; clean them before analysis")
    return values


def dates(series: pd.Series, label: str) -> pd.Series:
    text = series.astype(str)
    parts = text.str.extract(r"^\s*(\d{1,2})/(\d{1,2})/")
    ambiguous = pd.to_numeric(parts[0], errors="coerce").le(12) & pd.to_numeric(parts[1], errors="coerce").le(12)
    if ambiguous.any():
        raise ValueError(f"{label}: ambiguous slash dates need an explicit day/month or month/day conversion")
    values = pd.to_datetime(series, errors="coerce", format="mixed")
    if (series.notna() & values.isna()).any():
        raise ValueError(f"{label}: some dates could not be parsed")
    return values


@dataclass
class AnalysisResult:
    kind: str
    summary: str
    tables: dict[str, pd.DataFrame] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    definitions: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"kind": self.kind, "summary": self.summary, "warnings": self.warnings,
                "definitions": self.definitions,
                "tables": {key: frame.to_dict(orient="records") for key, frame in self.tables.items()}}

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        suffix = path.suffix.lower()
        if suffix == ".json":
            path.write_text(json.dumps(self.as_dict(), indent=2, default=str), encoding="utf-8")
        elif suffix == ".xlsx":
            with pd.ExcelWriter(path, engine="openpyxl") as writer:
                pd.DataFrame([{"kind": self.kind, "summary": self.summary,
                               "warnings": "; ".join(self.warnings),
                               "definitions": json.dumps(self.definitions, default=str)}]).to_excel(
                    writer, sheet_name="Summary", index=False)
                for index, (name, frame) in enumerate(self.tables.items(), 1):
                    safe = re.sub(r"[][\\/*?:]", "_", name)[:25]
                    frame.to_excel(writer, sheet_name=f"{index}_{safe}"[:31], index=False)
        elif suffix == ".html":
            sections = []
            for name, frame in self.tables.items():
                sections.append(f"<h2>{escape(name)}</h2>" + frame.head(500).to_html(index=False, escape=True))
            warnings = "".join(f"<li>{escape(w)}</li>" for w in self.warnings)
            definitions = escape(json.dumps(self.definitions, indent=2, default=str))
            path.write_text(
                "<!doctype html><html lang='en'><meta charset='utf-8'><title>AnalystKit report</title>"
                "<style>body{font:16px system-ui;max-width:1100px;margin:40px auto;padding:0 20px;color:#243047}"
                "table{border-collapse:collapse;width:100%;font-size:14px}td,th{border-bottom:1px solid #ddd;padding:7px;text-align:left}"
                "h1{color:#17437d}pre{white-space:pre-wrap;background:#f3f5f8;padding:14px}</style>"
                f"<h1>{escape(self.kind.replace('_', ' ').title())}</h1><p>{escape(self.summary)}</p>"
                f"<h2>Review notes</h2><ul>{warnings}</ul>{''.join(sections)}"
                f"<h2>Definitions</h2><pre>{definitions}</pre>"
                "<p>HTML shows up to 500 rows per table; Excel contains all rows.</p></html>", encoding="utf-8")
        else:
            raise ValueError("Use .html, .xlsx, or .json")
        return path
