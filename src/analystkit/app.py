"""Local upload interface. No web service or account is required."""

from pathlib import Path
import tempfile

import streamlit as st

from analystkit.profile import profile
from analystkit.workbook import inspect

st.set_page_config(page_title="AnalystKit", page_icon="📊", layout="wide")
st.title("Business Analyst Tool Kit")
st.caption("Explore your spreadsheets locally. No account or API key required.")
st.info("Working now: Data Profiler and table detection. The remaining analyses are in the project roadmap.")
uploaded = st.file_uploader("Choose an Excel or CSV file", type=["xlsx", "xlsm", "csv"])
if uploaded:
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / Path(uploaded.name).name
        source.write_bytes(uploaded.getvalue())
        try:
            inspection = inspect(source)
            if not inspection.candidates:
                st.error("No table was found. Check that your file has a header row and data beneath it.")
            else:
                for warning in inspection.warnings:
                    st.warning(warning)
                candidates = inspection.candidates
                selected = st.selectbox("Which table should I analyse?", range(len(candidates)),
                                        format_func=lambda i: f"{candidates[i].sheet} · header row {candidates[i].header_row} · {', '.join(candidates[i].columns[:4])}")
                table = candidates[selected]
                st.write("Detected columns:", ", ".join(table.columns))
                if st.button("Create data profile", type="primary"):
                    result = profile(source, sheet=table.sheet, header_row=table.header_row)
                    st.subheader("Findings")
                    for finding in result.findings:
                        st.write("•", finding)
                    st.subheader("Suggested field meanings")
                    st.dataframe([{"field": s.field, "column": s.column, "confidence": s.confidence,
                                   "confirm before calculations": s.needs_confirmation} for s in result.suggestions], hide_index=True)
                    st.subheader("Column quality")
                    st.dataframe(result.columns, hide_index=True)
                    html = Path(directory) / "profile.html"
                    excel = Path(directory) / "profile.xlsx"
                    result.save(html)
                    result.save(excel)
                    st.session_state["profile_downloads"] = (html.read_bytes(), excel.read_bytes(), uploaded.name, selected)
                downloads = st.session_state.get("profile_downloads")
                if downloads and downloads[2:] == (uploaded.name, selected):
                    st.download_button("Download readable report", downloads[0], "profile.html", mime="text/html")
                    st.download_button("Download Excel with source rows", downloads[1], "profile.xlsx",
                                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        except (ValueError, OSError) as error:
            st.error(str(error))
