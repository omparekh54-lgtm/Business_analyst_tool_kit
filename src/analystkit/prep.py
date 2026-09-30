"""Reviewable data cleaning, with source rows and an explicit change log."""

from dataclasses import dataclass
from pathlib import Path
import re

import pandas as pd

from .workbook import inspect, read_table


@dataclass
class PrepResult:
    data: pd.DataFrame
    changes: pd.DataFrame
    warnings: list[str]
    source_count: int

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix.lower() != ".xlsx":
            raise ValueError("Prepared data exports to .xlsx to include the change log")
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            self.data.to_excel(writer, sheet_name="Prepared data", index=False)
            self.changes.to_excel(writer, sheet_name="Changes", index=False)
            pd.DataFrame({"Warning": self.warnings}).to_excel(writer, sheet_name="Review", index=False)
        return path


def _amount(value: object) -> float | None:
    if pd.isna(value) or str(value).strip() == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    negative = text.startswith("(") and text.endswith(")")
    text = re.sub(r"[₹$£€,\s]", "", text.strip("()"))
    try:
        return -float(text) if negative else float(text)
    except ValueError:
        return None


def prepare(paths: list[str | Path], *, tables: dict[str, tuple[str, int]] | None = None,
            rename: dict[str, str] | None = None, date_columns: list[str] | None = None,
            amount_columns: list[str] | None = None, dedupe_keys: list[str] | None = None,
            per_file_rename: dict[str, dict[str, str]] | None = None) -> PrepResult:
    """Combine and clean selected tables; never delete duplicate or unparseable rows.

    `tables` maps each filename to (sheet, one-based header row). When more than one
    table is plausible, selection is mandatory. `rename` is an explicit schema map.
    """
    if not paths:
        raise ValueError("Choose at least one input file")
    frames = []
    warnings = []
    log: list[dict] = []
    for source in map(Path, paths):
        selection = (tables or {}).get(source.name)
        view = inspect(source)
        choices = [c for c in view.candidates if selection is None or (c.sheet, c.header_row) == selection]
        if not choices:
            raise ValueError(f"No selected table found in {source.name}")
        if selection is None and len(choices) > 1 and choices[0].score - choices[1].score < 3:
            raise ValueError(f"Choose a sheet and header row for {source.name}")
        chosen = choices[0]
        frame = read_table(source, chosen)
        mapping = {**(rename or {}), **(per_file_rename or {}).get(source.name, {})}
        unknown = set(mapping) - set(frame)
        if unknown:
            raise ValueError(f"{source.name}: columns to rename were not found: {', '.join(sorted(unknown))}")
        frame = frame.rename(columns=mapping)
        if frame.columns.duplicated().any():
            raise ValueError(f"Column mapping creates duplicate names in {source.name}")
        frame.insert(0, "_source_sheet", chosen.sheet)
        frame.insert(0, "_source_file", source.name)
        frames.append(frame)
        warnings.extend(f"{source.name}: {w}" for w in view.warnings + list(chosen.warnings))
        log.append({"source_file": source.name, "action": "import", "column": "", "affected_rows": len(frame),
                    "details": f"{chosen.sheet}, header row {chosen.header_row}"})
        if mapping:
            log.append({"source_file": source.name, "action": "align column names", "column": ", ".join(mapping),
                        "affected_rows": len(frame), "details": str(mapping)})
    if len(paths) > 1 and len({Path(p).name for p in paths}) != len(paths):
        raise ValueError("Input filenames must be distinct to preserve source references")
    column_sets = [set(f.columns) - {"_source_file", "_source_sheet", "_source_row"} for f in frames]
    if len(set(map(frozenset, column_sets))) > 1:
        warnings.append("Files have different columns. Missing fields remain blank; confirm they represent the same business data.")
    data = pd.concat(frames, ignore_index=True, sort=False)
    for column in data.columns:
        if column.startswith("_source_"):
            continue
        if pd.api.types.is_object_dtype(data[column]):
            original = data[column].copy()
            data[column] = data[column].map(lambda v: v.strip() if isinstance(v, str) else v)
            changed = int(sum(isinstance(a, str) and a != b for a, b in zip(original, data[column])))
            if changed:
                log.append({"source_file": "all", "action": "trim whitespace", "column": column,
                            "affected_rows": changed, "details": "Leading and trailing spaces removed"})
    for column in date_columns or []:
        if column not in data:
            raise ValueError(f"Date column not found: {column}")
        original = data[column]
        ambiguous = original.astype(str).str.match(r"^\s*(\d{1,2})/(\d{1,2})/(\d{2,4})(?:\s|$)")
        parts = original.astype(str).str.extract(r"^\s*(\d{1,2})/(\d{1,2})/")
        ambiguous &= pd.to_numeric(parts[0], errors="coerce").le(12) & pd.to_numeric(parts[1], errors="coerce").le(12)
        parsed = pd.to_datetime(original.mask(ambiguous), errors="coerce", format="mixed", dayfirst=False)
        invalid = original.notna() & parsed.isna()
        data[column] = parsed
        log.append({"source_file": "all", "action": "parse date", "column": column,
                    "affected_rows": int(parsed.notna().sum()), "details": f"{int(invalid.sum())} unparseable values preserved in review column"})
        if invalid.any():
            data[f"_original_{column}"] = original.where(invalid)
            warnings.append(f"{column}: {int(invalid.sum())} values could not be parsed. Check original values before analysis.")
        if ambiguous.any():
            warnings.append(f"{column}: {int(ambiguous.sum())} slash dates could mean day/month or month/day and need confirmation.")
    for column in amount_columns or []:
        if column not in data:
            raise ValueError(f"Amount column not found: {column}")
        original = data[column]
        parsed = original.map(_amount)
        invalid = original.notna() & parsed.isna()
        data[column] = parsed
        log.append({"source_file": "all", "action": "parse amount", "column": column,
                    "affected_rows": int(parsed.notna().sum()), "details": f"{int(invalid.sum())} unparseable values preserved in review column"})
        if invalid.any():
            data[f"_original_{column}"] = original.where(invalid)
            warnings.append(f"{column}: {int(invalid.sum())} values could not be parsed. Check original values before analysis.")
    if dedupe_keys:
        missing = set(dedupe_keys) - set(data.columns)
        if missing:
            raise ValueError(f"Duplicate keys not found: {', '.join(sorted(missing))}")
        data["_possible_duplicate"] = data.duplicated(subset=dedupe_keys, keep=False)
        count = int(data["_possible_duplicate"].sum())
        log.append({"source_file": "all", "action": "flag duplicate", "column": ", ".join(dedupe_keys),
                    "affected_rows": count, "details": "No rows removed"})
    return PrepResult(data, pd.DataFrame(log), warnings, len(frames))
