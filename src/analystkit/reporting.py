"""Combine completed analyses into a source-preserving management report."""

import pandas as pd

from .results import AnalysisResult


def insight_report(results: list[AnalysisResult], *, audience: str = "Management",
                   title: str = "Business analysis report") -> AnalysisResult:
    if not results:
        raise ValueError("Choose at least one completed analysis")
    if not all(isinstance(item, AnalysisResult) for item in results):
        raise TypeError("All inputs must be completed AnalysisResult objects")
    overview = pd.DataFrame([{"analysis": item.kind, "finding": item.summary,
                              "warnings": "; ".join(item.warnings)} for item in results])
    tables = {"Executive overview": overview}
    for index, item in enumerate(results, 1):
        for name, frame in item.tables.items():
            tables[f"{index} {item.kind[:10]} {name[:16]}"] = frame.copy()
    return AnalysisResult("insight_to_report", f"{title} for {audience}: {len(results)} analyses combined.",
                          tables, ["Findings are copied from the analyses; review wording before sharing.",
                                   "Recommendations are not generated automatically from correlations."],
                          {"audience": audience, "title": title,
                           "analyses": [{"kind": item.kind, "definitions": item.definitions} for item in results]})
