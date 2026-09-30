"""A first, source-linked analysis of a selected business table."""

from dataclasses import asdict, dataclass
from html import escape
import json
from pathlib import Path

import pandas as pd

from .schema import FieldSuggestion, suggest_fields
from .workbook import TableCandidate, inspect, read_table


@dataclass
class ProfileResult:
    source: str
    sheet: str
    header_row: int
    row_count: int
    columns: list[dict]
    suggestions: list[FieldSuggestion]
    findings: list[str]
    source_rows: pd.DataFrame
    warnings: list[str]

    def as_dict(self) -> dict:
        return {
            "source": self.source, "sheet": self.sheet, "header_row": self.header_row,
            "row_count": self.row_count, "columns": self.columns,
            "suggestions": [asdict(item) for item in self.suggestions],
            "findings": self.findings, "warnings": self.warnings,
        }

    def save(self, path: str | Path) -> Path:
        """Export HTML, JSON, or XLSX; source rows stay available for review."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix.lower() == ".json":
            path.write_text(json.dumps(self.as_dict(), indent=2, default=str), encoding="utf-8")
        elif path.suffix.lower() == ".xlsx":
            with pd.ExcelWriter(path, engine="openpyxl") as writer:
                pd.DataFrame(self.columns).to_excel(writer, sheet_name="Column quality", index=False)
                pd.DataFrame([asdict(s) for s in self.suggestions]).to_excel(writer, sheet_name="Suggested fields", index=False)
                pd.DataFrame({"Finding": self.findings + self.warnings}).to_excel(writer, sheet_name="Findings", index=False)
                self.source_rows.to_excel(writer, sheet_name="Source rows", index=False)
        elif path.suffix.lower() == ".html":
            rows = "".join("<tr>" + "".join(f"<td>{escape(str(item))}</td>" for item in row.values()) + "</tr>" for row in self.columns)
            findings = "".join(f"<li>{escape(item)}</li>" for item in self.findings + self.warnings)
            labels = "".join(f"<li>{escape(s.field)}: {escape(s.column or 'not found')} {'(confirm)' if s.needs_confirmation else ''}</li>" for s in self.suggestions)
            path.write_text(f"""<!doctype html><html lang="en"><meta charset="utf-8"><title>Data profile</title>
<style>body{{font:16px system-ui;max-width:960px;margin:48px auto;padding:0 20px;color:#182235;line-height:1.5}}table{{border-collapse:collapse;width:100%}}td,th{{padding:8px;border-bottom:1px solid #ccd4dc;text-align:left}}h1{{color:#17437d}}.note{{background:#f0f5fb;padding:16px;border-radius:8px}}</style>
<h1>Data profile</h1><p class="note">Source: {escape(self.source)} · Sheet: {escape(self.sheet)} · Header row: {self.header_row} · Data rows: {self.row_count}</p>
<h2>Findings</h2><ul>{findings}</ul><h2>Suggested fields</h2><ul>{labels}</ul>
<h2>Column quality</h2><table><thead><tr><th>Column</th><th>Nonblank</th><th>Missing</th><th>Distinct</th><th>Examples</th></tr></thead><tbody>{rows}</tbody></table>
<p>Review suggested field meanings before using them for business calculations. Download the Excel report for source rows.</p></html>""", encoding="utf-8")
        else:
            raise ValueError("Output must end in .html, .xlsx, or .json")
        return path


def profile(path: str | Path, *, sheet: str | None = None, header_row: int | None = None) -> ProfileResult:
    """Profile the detected table; select a sheet/header when detection is uncertain."""
    inspection = inspect(path)
    choices = [c for c in inspection.candidates if (sheet is None or c.sheet == sheet) and (header_row is None or c.header_row == header_row)]
    if not choices:
        raise ValueError("No matching table found. Choose an available sheet and header row.")
    if len(choices) > 1 and choices[0].score - choices[1].score < 3 and (sheet is None or header_row is None):
        options = ", ".join(f"{c.sheet} row {c.header_row}" for c in choices[:5])
        raise ValueError(f"More than one table is plausible: {options}. Select sheet and header_row.")
    selected: TableCandidate = choices[0]
    frame = read_table(path, selected)
    if frame.empty:
        raise ValueError("The selected table has no data rows.")
    columns = []
    for name in frame.columns:
        if name == "_source_row":
            continue
        series = frame[name]
        examples = [str(v)[:55] for v in series.dropna().drop_duplicates().head(3)]
        columns.append({"column": name, "nonblank": int(series.notna().sum()),
                        "missing": int(series.isna().sum()), "distinct": int(series.nunique(dropna=True)),
                        "examples": ", ".join(examples)})
    findings = [f"Found {len(frame):,} data rows and {len(columns)} columns."]
    for col in columns:
        if col["missing"]:
            findings.append(f"{col['column']}: {col['missing']:,} blank values ({col['missing'] / len(frame):.1%} of rows).")
    possible_ids = [s for s in suggest_fields(frame) if s.field in {"transaction_id", "customer_id"} and s.column]
    for suggestion in possible_ids:
        duplicates = int(frame[suggestion.column].dropna().duplicated().sum())
        if duplicates:
            findings.append(f"{suggestion.column}: {duplicates:,} repeated values. Confirm whether repeats are expected before treating them as duplicate records.")
    return ProfileResult(str(Path(path).name), selected.sheet, selected.header_row, len(frame), columns,
                         suggest_fields(frame), findings, frame, inspection.warnings + list(selected.warnings))
