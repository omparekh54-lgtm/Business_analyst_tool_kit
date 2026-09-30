"""Upload forms for the twelve analysis and reporting functions."""

from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import tempfile

import pandas as pd
import streamlit as st

from . import (AnalysisResult, cohorts, experiment, forecast, funnel, insight_report,
               meeting_assistant, MetricCatalog, pricing, process_bottlenecks, reconcile, run_saved,
               save_setup, traceability, variance)
from .results import table
from .workbook import inspect, read_table


FUNCTIONS = {
    "Reconcile two KPIs": "reconcile",
    "Explain a change": "variance",
    "Analyse a funnel": "funnel",
    "Analyse customer cohorts": "cohorts",
    "Find process bottlenecks": "process_bottlenecks",
    "Simulate pricing and margin": "pricing",
    "Compare experiment groups": "experiment",
    "Forecast monthly values": "forecast",
    "Draft meeting requirements": "meeting_assistant",
    "Track requirements": "traceability",
    "Combine findings into a report": "insight_report",
    "Rerun a saved analysis": "recurring_report_runner",
}


def _select(frame, label, *, optional=False, key=None):
    options = (["(none)"] if optional else []) + [str(c) for c in frame.columns if not str(c).startswith("_source_")]
    choice = st.selectbox(label, options, key=key)
    return None if choice == "(none)" else choice


def _upload_table(upload, directory, key):
    path = Path(directory) / Path(upload.name).name
    path.write_bytes(upload.getvalue())
    options = inspect(path).candidates
    if not options:
        raise ValueError(f"No table found in {upload.name}")
    chosen = st.selectbox(f"Table in {upload.name}", range(len(options)), key=key,
                          format_func=lambda i: f"{options[i].sheet}, header row {options[i].header_row}: {', '.join(options[i].columns[:4])}")
    candidate = options[chosen]
    return read_table(path, candidate), path, candidate


def _show_result(result, fingerprint, prefix="analysis"):
    st.subheader("Answer")
    st.write(result.summary)
    for warning in result.warnings:
        st.warning(warning)
    for name, frame in result.tables.items():
        with st.expander(f"{name} ({len(frame)} rows)", expanded=name in {"Totals", "Funnel", "Comparison", "Forecast", "Executive overview"}):
            st.dataframe(frame.head(500), hide_index=True)
    with tempfile.TemporaryDirectory() as directory:
        for suffix, mime in (("html", "text/html"),
                             ("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
                             ("json", "application/json")):
            path = result.save(Path(directory) / f"{prefix}.{suffix}")
            st.download_button(f"Download {suffix.upper()} report", path.read_bytes(),
                               f"{prefix}.{suffix}", mime=mime, key=f"{prefix}_{suffix}_{fingerprint[:8]}")


def render(label: str) -> None:
    task = FUNCTIONS[label]
    st.write({
        "reconcile": "Find the transactions behind a difference between two totals.",
        "variance": "See which segments contributed to a change between two periods.",
        "funnel": "Follow cases through stages in the order you select.",
        "cohorts": "See whether customers acquired in the same month return.",
        "process_bottlenecks": "Find the longest waits between activities.",
        "pricing": "Compare current profit with a price, cost, and volume scenario.",
        "experiment": "Compare two groups and inspect uncertainty.",
        "forecast": "Forecast monthly totals and see historical error.",
        "meeting_assistant": "Extract explicitly labelled decisions, actions, requirements, and questions as drafts.",
        "traceability": "Check requirement status and links to design, tests, and acceptance.",
        "insight_report": "Combine exported JSON analyses into one shareable report.",
        "recurring_report_runner": "Run a saved setup on a new file and compare with a previous JSON result.",
    }[task])
    if task == "meeting_assistant":
        notes_file = st.file_uploader("Upload .txt or .md notes (optional)", type=["txt", "md"], key="notes_file")
        initial_notes = notes_file.getvalue().decode("utf-8-sig") if notes_file else ""
        notes = st.text_area("Review notes; label lines Decision:, Action:, Requirement:, Acceptance:, or Question:",
                             value=initial_notes, height=220)
        fingerprint = sha256(notes.encode()).hexdigest()
        if st.button("Create drafts", type="primary"):
            try:
                st.session_state["meeting_result"] = (fingerprint, meeting_assistant(notes))
            except ValueError as error:
                st.error(str(error))
        saved = st.session_state.get("meeting_result")
        if saved and saved[0] == fingerprint:
            _show_result(saved[1], fingerprint)
        return
    if task == "insight_report":
        uploads = st.file_uploader("Select JSON reports exported by AnalystKit", type=["json"], accept_multiple_files=True, key="insight_files")
        title = st.text_input("Report title", "Business analysis report")
        audience = st.text_input("Audience", "Management")
        fingerprint = sha256(b"".join(u.getvalue() for u in uploads) + str((title, audience)).encode()).hexdigest() if uploads else ""
        if uploads and st.button("Combine reports", type="primary"):
            try:
                reports = []
                for upload in uploads:
                    obj = json.loads(upload.getvalue())
                    reports.append(AnalysisResult(obj["kind"], obj["summary"],
                                                  {name: pd.DataFrame(rows) for name, rows in obj["tables"].items()},
                                                  obj.get("warnings", []), obj.get("definitions", {})))
                st.session_state["insight_result"] = (fingerprint, insight_report(reports, title=title, audience=audience))
            except (ValueError, KeyError, TypeError) as error:
                st.error(f"Could not read these AnalystKit results: {error}")
        saved = st.session_state.get("insight_result")
        if saved and saved[0] == fingerprint:
            _show_result(saved[1], fingerprint)
        return
    if task == "recurring_report_runner":
        setup = st.file_uploader("Saved setup.json", type=["json"], key="setup_file")
        previous = st.file_uploader("Previous JSON report (optional)", type=["json"], key="previous_file")
        if setup:
            try:
                config = json.loads(setup.getvalue())
                count = 2 if config.get("task") == "reconcile" else 1
                uploads = st.file_uploader(f"Choose {count} new data file(s)", type=["xlsx", "xlsm", "csv"],
                                           accept_multiple_files=True, key="recurring_files")
                if uploads and len(uploads) == count:
                    with tempfile.TemporaryDirectory() as directory:
                        setup_path = Path(directory) / "setup.json"
                        setup_path.write_bytes(setup.getvalue())
                        frames = [_upload_table(u, directory, f"recurring_{i}")[0] for i, u in enumerate(uploads)]
                        overrides = []
                        for i, frame in enumerate(frames):
                            mapped = frame.rename(columns=config["column_maps"][i])
                            mapping = {}
                            for field in config["required_fields"][i]:
                                if field not in mapped:
                                    choices = [str(c) for c in frame.columns if not str(c).startswith("_source_")]
                                    replacement = st.selectbox(f"Which new column means {field} in file {i + 1}?", choices, key=f"remap_{i}_{field}")
                                    mapping[replacement] = field
                            overrides.append(mapping)
                        fingerprint = sha256(setup.getvalue() + b"".join(u.getvalue() for u in uploads) +
                                             (previous.getvalue() if previous else b"") + str(overrides).encode()).hexdigest()
                        previous_path = None
                        if previous:
                            previous_path = Path(directory) / "previous.json"
                            previous_path.write_bytes(previous.getvalue())
                        if st.button("Run saved analysis", type="primary"):
                            st.session_state["recurring_result"] = (fingerprint, run_saved(setup_path, frames, previous_path, overrides))
                        saved = st.session_state.get("recurring_result")
                        if saved and saved[0] == fingerprint:
                            _show_result(saved[1], fingerprint)
            except (ValueError, KeyError, TypeError) as error:
                st.error(str(error))
        return

    count = 2 if task == "reconcile" else 1
    uploads = st.file_uploader(f"Choose {count} data file(s)", type=["xlsx", "xlsm", "csv"],
                               accept_multiple_files=True, key=f"{task}_files")
    if not uploads or len(uploads) != count:
        return
    if len({upload.name for upload in uploads}) != count:
        st.error("Choose files with distinct names.")
        return
    with tempfile.TemporaryDirectory() as directory:
        try:
            frames = [_upload_table(upload, directory, f"{task}_table_{i}")[0] for i, upload in enumerate(uploads)]
            data = frames[0]
            args = {}
            if task == "reconcile":
                args = {"amount": _select(data, "Amount in first report"),
                        "left_amount": None,
                        "right_amount": _select(frames[1], "Amount in second report"),
                        "key": _select(data, "Unique ID present in both files", optional=True)}
                if args["key"] and args["key"] not in frames[1]:
                    raise ValueError(f"{args['key']} is missing in the second file")
            elif task == "variance":
                args = {"date": _select(data, "Date"), "amount": _select(data, "Metric value"),
                        "segment": _select(data, "Break down by (optional)", optional=True)}
                first = st.date_input("First period (start and end)", value=(pd.Timestamp.today().date().replace(day=1), pd.Timestamp.today().date()))
                second = st.date_input("Second period (start and end)", value=(pd.Timestamp.today().date().replace(day=1), pd.Timestamp.today().date()), key="second_period")
                if len(first) != 2 or len(second) != 2:
                    st.info("Choose both dates for each period.")
                    return
                args.update(start_a=str(first[0]), end_a=str(first[1]), start_b=str(second[0]), end_b=str(second[1]))
            elif task == "funnel":
                args = {"case_id": _select(data, "Case or lead ID"), "stage": _select(data, "Stage"),
                        "timestamp": _select(data, "Event time")}
                options = list(data[args["stage"]].dropna().astype(str).unique()[:100])
                count_stages = st.number_input("How many funnel stages?", min_value=2, max_value=20, value=3)
                args["stages"] = [st.selectbox(f"Stage {index + 1}", options,
                                               index=min(index, len(options) - 1), key=f"funnel_stage_{index}")
                                  for index in range(count_stages)] if options else []
            elif task == "cohorts":
                args = {"customer_id": _select(data, "Customer ID"), "date": _select(data, "Transaction date"),
                        "amount": _select(data, "Amount (optional)", optional=True)}
            elif task == "process_bottlenecks":
                args = {"case_id": _select(data, "Case ID"), "activity": _select(data, "Activity"),
                        "timestamp": _select(data, "Event time")}
            elif task == "pricing":
                args = {field: _select(data, label) for field, label in
                        [("product", "Product"), ("price", "Unit price"), ("cost", "Unit cost"), ("quantity", "Quantity")]}
                args.update(price_change_pct=st.number_input("Price change %", value=0.0),
                            cost_change_pct=st.number_input("Cost change %", value=0.0),
                            quantity_change_pct=st.number_input("Assumed quantity change %", value=0.0))
            elif task == "experiment":
                args = {"group": _select(data, "Experiment group"), "outcome": _select(data, "Outcome"),
                        "guardrail": _select(data, "Guardrail (optional)", optional=True)}
                groups = list(data[args["group"]].dropna().astype(str).unique()[:100])
                if len(groups) < 2:
                    raise ValueError("The group column needs two distinct groups")
                args.update(control=st.selectbox("Control group", groups),
                            treatment=st.selectbox("Treatment group", groups, index=1),
                            binary=st.checkbox("Outcome is 0/1", value=True))
            elif task == "forecast":
                args = {"date": _select(data, "Date"), "value": _select(data, "Value to forecast"),
                        "months": st.slider("Months ahead", 1, 12, 3)}
            else:
                args = {"requirement_id": _select(data, "Requirement ID"), "status": _select(data, "Status"),
                        "design": _select(data, "Design link (optional)", optional=True),
                        "test": _select(data, "Test link (optional)", optional=True),
                        "acceptance": _select(data, "Acceptance link (optional)", optional=True)}
            metric_reference = None
            if task in {"reconcile", "variance", "cohorts", "pricing", "experiment", "forecast"}:
                catalog_file = st.file_uploader("Approved metric dictionary (optional)", type=["json"], key=f"{task}_metrics")
                if catalog_file:
                    local_catalog = Path(directory) / "catalog.json"
                    local_catalog.write_bytes(catalog_file.getvalue())
                    approved = [item for item in MetricCatalog.load(local_catalog).definitions if item.status == "approved"]
                    if approved:
                        chosen_metric = st.selectbox("Reference an approved metric", [None] + approved,
                                                     format_func=lambda item: "No metric reference" if item is None else f"{item.name} (v{item.version})")
                        if chosen_metric:
                            metric_reference = asdict(chosen_metric)
                            st.info(f"Definition: {chosen_metric.description}. Calculation: {chosen_metric.calculation}. Confirm your chosen columns match it.")
                    else:
                        st.warning("This dictionary contains no approved definitions.")
            fingerprint = sha256(b"".join(u.getvalue() for u in uploads) + str((args, metric_reference)).encode()).hexdigest()
            if st.button("Run analysis", type="primary"):
                runner = {"reconcile": reconcile, "variance": variance, "funnel": funnel, "cohorts": cohorts,
                          "process_bottlenecks": process_bottlenecks, "pricing": pricing,
                          "experiment": experiment, "forecast": forecast, "traceability": traceability}[task]
                result = runner(*frames, **args)
                if metric_reference:
                    result.definitions["metric_reference"] = metric_reference
                    result.warnings.append("Metric definition is a reference; confirm selected columns implement its documented calculation.")
                st.session_state[f"{task}_result"] = (fingerprint, result)
                with tempfile.TemporaryDirectory() as setup_dir:
                    setup = save_setup(Path(setup_dir) / "setup.json", task=task, sample_files=frames,
                                       parameters=args, metric_reference=metric_reference)
                    st.session_state[f"{task}_setup"] = (fingerprint, setup.read_bytes())
            saved = st.session_state.get(f"{task}_result")
            if saved and saved[0] == fingerprint:
                _show_result(saved[1], saved[0], prefix=task)
                st.download_button("Save this setup for next time", st.session_state[f"{task}_setup"][1],
                                   "setup.json", mime="application/json", key=f"setup_download_{task}")
        except (ValueError, KeyError, OSError, ArithmeticError, TypeError) as error:
            st.error(str(error))
