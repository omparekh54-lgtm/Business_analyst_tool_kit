"""Local analyst interface: upload, confirm, review, download."""

from hashlib import sha256
from pathlib import Path
import tempfile

import streamlit as st

from analystkit import MetricCatalog, audit, inspect, prepare, profile
from analystkit.app_analysis import FUNCTIONS, render

st.set_page_config(page_title="AnalystKit", page_icon="📊", layout="wide")
st.title("Business Analyst Tool Kit")
st.caption("Analyse files locally. No account or API key required.")
task = st.selectbox("What do you want to do?", ["Explore data", "Prepare data", "Audit workbook", "Define a metric"] + list(FUNCTIONS))


def local_file(upload, directory):
    path = Path(directory) / Path(upload.name).name
    path.write_bytes(upload.getvalue())
    return path


def choose_table(path, key):
    result = inspect(path)
    for warning in result.warnings:
        st.warning(warning)
    if not result.candidates:
        st.error(f"No table found in {path.name}. Check the header and data rows.")
        return None
    candidates = result.candidates
    index = st.selectbox(f"Which table in {path.name}?", range(len(candidates)), key=key,
                         format_func=lambda i: f"{candidates[i].sheet}, header row {candidates[i].header_row}: {', '.join(candidates[i].columns[:4])}")
    chosen = candidates[index]
    st.caption("Detected columns: " + ", ".join(chosen.columns))
    return chosen


def download(key, fingerprint, filename, mime):
    saved = st.session_state.get(key)
    if saved and saved[0] == fingerprint:
        st.download_button(f"Download {filename}", saved[1], filename, mime=mime, key="download_" + key)


EXCEL_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

if task == "Explore data":
    st.write("See the columns, blank values, repeated IDs, and suggested field meanings.")
    upload = st.file_uploader("Choose Excel or CSV", type=["xlsx", "xlsm", "csv"], key="profile_upload")
    if upload:
        with tempfile.TemporaryDirectory() as directory:
            try:
                path = local_file(upload, directory)
                chosen = choose_table(path, "profile_table")
                if chosen:
                    fingerprint = sha256(upload.getvalue() + str((chosen.sheet, chosen.header_row)).encode()).hexdigest()
                    if st.button("Create data profile", type="primary"):
                        result = profile(path, sheet=chosen.sheet, header_row=chosen.header_row)
                        st.subheader("Findings")
                        for finding in result.findings:
                            st.write("•", finding)
                        st.dataframe(result.columns, hide_index=True)
                        st.caption("Confirm suggested field meanings before calculating a business metric.")
                        st.dataframe([{"field": s.field, "column": s.column, "confirm": s.needs_confirmation} for s in result.suggestions], hide_index=True)
                        for extension in ("html", "xlsx"):
                            output = result.save(Path(directory) / f"profile.{extension}")
                            st.session_state[f"profile_{extension}"] = (fingerprint, output.read_bytes())
                    download("profile_html", fingerprint, "profile.html", "text/html")
                    download("profile_xlsx", fingerprint, "profile.xlsx", EXCEL_MIME)
            except (ValueError, OSError) as error:
                st.error(str(error))

elif task == "Prepare data":
    st.write("Combine files, trim spaces, parse selected dates and amounts, and flag duplicates. No rows are deleted.")
    uploads = st.file_uploader("Choose one or more files", type=["xlsx", "xlsm", "csv"], accept_multiple_files=True, key="prep_upload")
    if uploads:
        if len({u.name for u in uploads}) != len(uploads):
            st.error("Files need distinct names to keep their source rows identifiable.")
        else:
            with tempfile.TemporaryDirectory() as directory:
                try:
                    paths = [local_file(u, directory) for u in uploads]
                    chosen = [choose_table(path, f"prep_{path.name}") for path in paths]
                    if all(chosen):
                        columns = sorted(set().union(*(set(item.columns) for item in chosen)))
                        dates = st.multiselect("Date columns to standardize", columns)
                        amounts = st.multiselect("Amount columns to standardize", columns)
                        keys = st.multiselect("Columns identifying possible duplicates (optional)", columns)
                        st.caption("Files with different column names can be aligned using the Python rename map; the report flags unmatched columns.")
                        settings = ([(item.sheet, item.header_row) for item in chosen], dates, amounts, keys)
                        fingerprint = sha256(b"".join(u.getvalue() + u.name.encode() for u in uploads) + str(settings).encode()).hexdigest()
                        if st.button("Prepare and preview", type="primary"):
                            selections = {path.name: (item.sheet, item.header_row) for path, item in zip(paths, chosen)}
                            result = prepare(paths, tables=selections, date_columns=dates, amount_columns=amounts, dedupe_keys=keys)
                            st.subheader("Changes made")
                            st.dataframe(result.changes, hide_index=True)
                            for warning in result.warnings:
                                st.warning(warning)
                            st.dataframe(result.data.head(100), hide_index=True)
                            output = result.save(Path(directory) / "prepared.xlsx")
                            st.session_state["prep_xlsx"] = (fingerprint, output.read_bytes())
                        download("prep_xlsx", fingerprint, "prepared.xlsx", EXCEL_MIME)
                except (ValueError, OSError) as error:
                    st.error(str(error))

elif task == "Audit workbook":
    st.write("Find broken references, Excel errors, hidden sheets, and formula patterns to review.")
    upload = st.file_uploader("Choose an Excel workbook", type=["xlsx", "xlsm"], key="audit_upload")
    if upload:
        with tempfile.TemporaryDirectory() as directory:
            try:
                path = local_file(upload, directory)
                fingerprint = sha256(upload.getvalue()).hexdigest()
                if st.button("Audit workbook", type="primary"):
                    result = audit(path)
                    st.write(f"Checked {result.sheets_checked} sheets; found {len(result.findings)} items.")
                    st.dataframe([vars(item) for item in result.findings], hide_index=True)
                    output = result.save(Path(directory) / "audit.xlsx")
                    st.session_state["audit_xlsx"] = (fingerprint, output.read_bytes())
                download("audit_xlsx", fingerprint, "audit.xlsx", EXCEL_MIME)
            except (ValueError, OSError) as error:
                st.error(str(error))

elif task == "Define a metric":
    st.write("Record a metric's meaning, source, calculation, and owner. Drafts do not replace approved definitions.")
    uploaded = st.file_uploader("Existing metrics.json (optional)", type=["json"], key="metrics_upload")
    with tempfile.TemporaryDirectory() as directory:
        try:
            fingerprint = sha256(uploaded.getvalue()).hexdigest() if uploaded else "new-catalog"
            workspace = st.session_state.get("metrics_workspace")
            if workspace and workspace[0] == fingerprint:
                saved = Path(directory) / "workspace.json"
                saved.write_bytes(workspace[1])
                catalog = MetricCatalog.load(saved)
            else:
                catalog = MetricCatalog.load(local_file(uploaded, directory)) if uploaded else MetricCatalog()
            if catalog.definitions:
                st.dataframe([vars(item) for item in catalog.definitions], hide_index=True)
            with st.form("metric_form"):
                key = st.text_input("Short ID, for example net_sales")
                name = st.text_input("Metric name")
                description = st.text_area("What does this metric mean?")
                calculation = st.text_area("How is it calculated? (documentation, not executable code)")
                source = st.text_input("Source files or systems")
                grain = st.text_input("What does one source row represent?")
                filters = st.text_input("Exclusions or filters (optional)")
                owner = st.text_input("Definition owner")
                status = st.selectbox("Status", ["draft", "approved"])
                submitted = st.form_submit_button("Save definition")
            if submitted:
                item = catalog.add(key=key, name=name, description=description, calculation=calculation,
                                   source=source, grain=grain, filters=filters, owner=owner, status=status)
                output = catalog.save(Path(directory) / "metrics.json")
                st.session_state["metrics_workspace"] = (fingerprint, output.read_bytes())
                st.success(f"Saved {item.name}, version {item.version}. Download the updated dictionary.")
            workspace = st.session_state.get("metrics_workspace")
            if workspace and workspace[0] == fingerprint:
                st.download_button("Download metrics.json", workspace[1], "metrics.json", mime="application/json")
        except (ValueError, OSError, TypeError, KeyError) as error:
            st.error(str(error))

else:
    render(task)
