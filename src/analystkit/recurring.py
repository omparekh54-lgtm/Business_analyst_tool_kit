"""Saved local analyses with schema checks and comparable-run summaries."""

import json
from pathlib import Path

import pandas as pd

from .decisions import experiment, forecast, pricing
from .journeys import cohorts, funnel, process_bottlenecks
from .performance import reconcile, variance
from .requirements import traceability
from .results import AnalysisResult, table


TASKS = {
    "reconcile": reconcile, "variance": variance, "funnel": funnel, "cohorts": cohorts,
    "process_bottlenecks": process_bottlenecks, "pricing": pricing,
    "experiment": experiment, "forecast": forecast, "traceability": traceability,
}
FIELDS = {
    "reconcile": ["amount", "key"], "variance": ["date", "amount", "segment"],
    "funnel": ["case_id", "stage", "timestamp"], "cohorts": ["customer_id", "date", "amount"],
    "process_bottlenecks": ["case_id", "activity", "timestamp"],
    "pricing": ["product", "price", "cost", "quantity"],
    "experiment": ["group", "outcome", "guardrail"], "forecast": ["date", "value"],
    "traceability": ["requirement_id", "status", "design", "test", "acceptance"],
}


def save_setup(path: str | Path, *, task: str, sample_files: list[str | Path],
               parameters: dict, column_maps: list[dict[str, str]] | None = None,
               metric_reference: dict | None = None) -> Path:
    """Validate a run and store confirmed settings for later files."""
    if task not in TASKS:
        raise ValueError(f"Unknown repeatable analysis: {task}")
    expected = 2 if task == "reconcile" else 1
    if len(sample_files) != expected:
        raise ValueError(f"{task} expects {expected} input file(s)")
    mappings = column_maps or [{} for _ in sample_files]
    if len(mappings) != expected:
        raise ValueError("Provide one column map per file")
    frames = [table(file, columns=mapping) for file, mapping in zip(sample_files, mappings)]
    if task == "reconcile":
        required = [[parameters.get("key"), parameters.get("left_amount") or parameters["amount"]],
                    [parameters.get("key"), parameters.get("right_amount") or parameters["amount"]]]
    else:
        required = [[value for field in FIELDS[task] if (value := parameters.get(field))]]
    required = [[value for value in fields if value] for fields in required]
    for frame, fields in zip(frames, required):
        missing = set(fields) - set(frame)
        if missing:
            raise ValueError(f"Required fields missing: {', '.join(sorted(missing))}")
    TASKS[task](*frames, **parameters)  # A saved profile must work with its sample.
    config = {"format_version": 1, "task": task, "parameters": parameters,
              "column_maps": mappings, "required_fields": required,
              "metric_reference": metric_reference}
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return path


def run_saved(setup: str | Path, files: list[str | Path],
              previous: str | Path | None = None,
              column_maps_override: list[dict[str, str]] | None = None) -> AnalysisResult:
    config = json.loads(Path(setup).read_text(encoding="utf-8"))
    if config.get("format_version") != 1 or config.get("task") not in TASKS:
        raise ValueError("Unsupported or unknown saved setup")
    expected = 2 if config["task"] == "reconcile" else 1
    if len(files) != expected:
        raise ValueError(f"Saved setup expects {expected} file(s)")
    overrides = column_maps_override or [{} for _ in files]
    if len(overrides) != len(files):
        raise ValueError("Provide one updated column map per file")
    frames = [table(file, columns={**mapping, **override}) for file, mapping, override in
              zip(files, config["column_maps"], overrides)]
    for frame, fields in zip(frames, config["required_fields"]):
        missing = set(fields) - set(frame)
        if missing:
            raise ValueError(f"Critical columns changed: {', '.join(sorted(missing))}. Review the mapping before running.")
    current = TASKS[config["task"]](*frames, **config["parameters"])
    if config.get("metric_reference"):
        current.definitions["metric_reference"] = config["metric_reference"]
        current.warnings.append("Metric definition is a reference; confirm selected columns implement its documented calculation.")
    if previous is None:
        return current
    prior = json.loads(Path(previous).read_text(encoding="utf-8"))
    if prior.get("kind") != current.kind:
        raise ValueError("Previous result is from a different analysis")
    changes = [{"item": "summary", "previous": str(prior.get("summary")), "current": current.summary, "change": ""}]
    for name, now in current.tables.items():
        if any(word in name.lower() for word in ("evidence", "source rows", "history", "transaction")):
            continue
        old_rows = prior.get("tables", {}).get(name, [])
        if not old_rows or now.empty or len(now) > 5000:
            continue
        before = pd.DataFrame(old_rows)
        shared = [column for column in now if column in before]
        numeric_fields = [column for column in shared if pd.api.types.is_numeric_dtype(now[column])
                          and pd.api.types.is_numeric_dtype(before[column]) and not pd.api.types.is_bool_dtype(now[column])]
        keys = [column for column in shared if column not in numeric_fields and not column.startswith("_source_")]
        if len(now) == 1 and len(before) == 1:
            pairs = [("all", before.iloc[0], now.iloc[0])]
        elif keys and not before.duplicated(keys).any() and not now.duplicated(keys).any():
            joined = before.merge(now, on=keys, how="outer", suffixes=("_old", "_new"))
            pairs = [("; ".join(f"{key}={row[key]}" for key in keys), row, row) for _, row in joined.iterrows()]
        else:
            continue
        for label, old, new in pairs:
            for column in numeric_fields:
                old_value = old.get(column if label == "all" else column + "_old")
                new_value = new.get(column if label == "all" else column + "_new")
                if pd.isna(old_value) and pd.isna(new_value):
                    continue
                old_number = 0. if pd.isna(old_value) else float(old_value)
                new_number = 0. if pd.isna(new_value) else float(new_value)
                if abs(new_number - old_number) > 1e-9:
                    changes.append({"item": f"{name}.{label}.{column}", "previous": old_value,
                                    "current": new_value, "change": new_number - old_number})
    return AnalysisResult("recurring_report_runner", f"Updated {config['task']}; compare the current result with the prior run.",
                          {"Changes since last run": pd.DataFrame(changes),
                           **{f"Current {name}": frame for name, frame in current.tables.items()}},
                          current.warnings + ["Unique summary rows are compared; review source evidence for the reasons behind changes."],
                          {"saved_setup": config, "previous_summary": prior.get("summary"), "current_definitions": current.definitions})
