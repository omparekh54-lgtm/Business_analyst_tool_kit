"""Explain discrepancies and period changes with additive, source-linked bridges."""

import pandas as pd

from .results import AnalysisResult, dates, numeric, require, table


def reconcile(left, right, *, amount: str, key: str | None = None,
              left_amount: str | None = None, right_amount: str | None = None,
              sheet_left: str | None = None, sheet_right: str | None = None) -> AnalysisResult:
    """Explain right total minus left total; keys must identify unique rows."""
    a = table(left, sheet=sheet_left)
    b = table(right, sheet=sheet_right)
    la, ra = left_amount or amount, right_amount or amount
    require(a, la)
    require(b, ra)
    a["_measure"] = numeric(a[la], la)
    b["_measure"] = numeric(b[ra], ra)
    if a["_measure"].isna().any() or b["_measure"].isna().any():
        raise ValueError("Blank amounts need a confirmed treatment before reconciliation")
    total_a, total_b = float(a["_measure"].sum()), float(b["_measure"].sum())
    difference = total_b - total_a
    bridge = []
    evidence = pd.DataFrame()
    warnings = []
    if key:
        require(a, key)
        require(b, key)
        for name, frame in (("left", a), ("right", b)):
            if frame[key].isna().any() or frame[key].duplicated().any():
                raise ValueError(f"{name}: {key} has blank/repeated values; select a unique transaction key or resolve the row grain")
        joined = a[[key, "_measure", "_source_row"]].merge(
            b[[key, "_measure", "_source_row"]], on=key, how="outer", indicator=True,
            suffixes=("_left", "_right"), validate="one_to_one")
        joined["contribution"] = joined["_measure_right"].fillna(0) - joined["_measure_left"].fillna(0)
        joined["reason"] = joined["_merge"].map({"left_only": "Only in left", "right_only": "Only in right", "both": "Different amount"}).astype(str)
        joined.loc[(joined["_merge"] == "both") & (joined["contribution"].abs() < 1e-9), "reason"] = "Matched"
        evidence = joined.rename(columns={"_source_row_left": "left_row", "_source_row_right": "right_row"}).drop(columns=["_merge"])
        for reason in ("Only in left", "Only in right", "Different amount"):
            subset = evidence[evidence["reason"] == reason]
            bridge.append({"reason": reason, "records": len(subset), "contribution": float(subset["contribution"].sum())})
    else:
        warnings.append("No unique transaction key was selected. The total difference cannot be assigned to records.")
        bridge.append({"reason": "Unexplained without matching IDs", "records": 0, "contribution": difference})
    if abs(sum(item["contribution"] for item in bridge) - difference) > 1e-6:
        raise ArithmeticError("Reconciliation bridge does not equal total difference")
    return AnalysisResult("kpi_reconciler", f"Right total {total_b:,.2f} minus left total {total_a:,.2f} = {difference:,.2f}.",
                          {"Totals": pd.DataFrame([{"left": total_a, "right": total_b, "difference": difference}]),
                           "Difference bridge": pd.DataFrame(bridge), "Matched source rows": evidence},
                          warnings, {"amount_left": la, "amount_right": ra, "key": key, "direction": "right minus left"})


def variance(data, *, date: str, amount: str, start_a: str, end_a: str,
             start_b: str, end_b: str, segment: str | None = None) -> AnalysisResult:
    """Explain B minus A by a named segment; labels are contributions, not causal claims."""
    frame = table(data)
    require(frame, date, amount)
    if segment:
        require(frame, segment)
    frame["_date"] = dates(frame[date], date)
    frame["_amount"] = numeric(frame[amount], amount)
    if frame["_amount"].isna().any():
        raise ValueError("Blank metric values require a confirmed treatment")
    a0, a1, b0, b1 = (pd.Timestamp(d) for d in (start_a, end_a, start_b, end_b))
    if a0 > a1 or b0 > b1:
        raise ValueError("Each period must start before it ends")
    if not (a1 < b0 or b1 < a0):
        raise ValueError("Comparison periods overlap; choose non-overlapping dates")
    first = frame[frame["_date"].between(a0, a1)].copy()
    second = frame[frame["_date"].between(b0, b1)].copy()
    if first.empty or second.empty:
        raise ValueError("Both periods need at least one record")
    first["_period"], second["_period"] = "A", "B"
    evidence = pd.concat([first, second], ignore_index=True)
    if segment:
        first["_segment"] = first[segment].fillna("(blank)").astype(str)
        second["_segment"] = second[segment].fillna("(blank)").astype(str)
    else:
        first["_segment"], second["_segment"] = "All records", "All records"
    a = first.groupby("_segment")["_amount"].sum()
    b = second.groupby("_segment")["_amount"].sum()
    breakdown = pd.DataFrame({"A": a, "B": b}).fillna(0).rename_axis("segment").reset_index()
    breakdown["change"] = breakdown["B"] - breakdown["A"]
    breakdown = breakdown.sort_values("change", key=lambda s: s.abs(), ascending=False)
    change = float(second["_amount"].sum() - first["_amount"].sum())
    if abs(breakdown["change"].sum() - change) > 1e-6:
        raise ArithmeticError("Segment changes do not add to the overall change")
    return AnalysisResult("variance_explorer", f"The metric changed by {change:,.2f} from period A to B.",
                          {"Contribution by segment": breakdown, "Source rows": evidence.drop(columns=["_date", "_amount"], errors="ignore")},
                          ["A segment contribution shows where a change occurred; it does not prove its cause."],
                          {"date": date, "amount": amount, "segment": segment,
                           "period_A": [start_a, end_a], "period_B": [start_b, end_b]})
