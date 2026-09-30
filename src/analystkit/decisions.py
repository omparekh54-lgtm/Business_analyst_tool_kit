"""Deterministic decision tools with explicit assumptions and uncertainty."""

import numpy as np
import pandas as pd
from scipy import stats

from .results import AnalysisResult, dates, numeric, require, table


def pricing(data, *, product: str, price: str, cost: str, quantity: str,
            price_change_pct: float = 0, cost_change_pct: float = 0,
            quantity_change_pct: float = 0) -> AnalysisResult:
    """Simulate a stated volume scenario; it does not predict demand elasticity."""
    frame = table(data)
    require(frame, product, price, cost, quantity)
    for label in (price, cost, quantity):
        frame[label + "_numeric"] = numeric(frame[label], label)
        if frame[label + "_numeric"].isna().any():
            raise ValueError(f"{label}: blank values need an explicit assumption")
    p, c, q = (frame[label + "_numeric"] for label in (price, cost, quantity))
    if (p < 0).any() or (c < 0).any() or (q < 0).any():
        raise ValueError("Price, unit cost, and quantity must be non-negative")
    new_p = p * (1 + price_change_pct / 100)
    new_c = c * (1 + cost_change_pct / 100)
    new_q = q * (1 + quantity_change_pct / 100)
    if (new_p < 0).any() or (new_c < 0).any() or (new_q < 0).any():
        raise ValueError("The proposed scenario cannot have negative values")
    detail = frame[[product, "_source_row"]].copy()
    detail["current_revenue"] = p * q
    detail["current_profit"] = (p - c) * q
    detail["proposed_revenue"] = new_p * new_q
    detail["proposed_profit"] = (new_p - new_c) * new_q
    detail["profit_change"] = detail["proposed_profit"] - detail["current_profit"]
    detail["quantity_to_match_current_profit"] = np.where(
        new_p > new_c, detail["current_profit"].clip(lower=0) / (new_p - new_c).replace(0, np.nan), np.nan)
    totals = {column: float(detail[column].sum()) for column in
              ("current_revenue", "current_profit", "proposed_revenue", "proposed_profit", "profit_change")}
    totals["current_margin"] = totals["current_profit"] / totals["current_revenue"] if totals["current_revenue"] else None
    totals["proposed_margin"] = totals["proposed_profit"] / totals["proposed_revenue"] if totals["proposed_revenue"] else None
    return AnalysisResult("pricing_margin_simulator", f"Under the entered volume assumption, profit changes by {totals['profit_change']:,.2f}.",
                          {"Scenario totals": pd.DataFrame([totals]), "Product evidence": detail},
                          ["Quantity changes are user assumptions, not predicted customer behaviour.",
                           "Break-even quantity is unavailable when proposed unit margin is zero or negative."],
                          {"price_change_pct": price_change_pct, "cost_change_pct": cost_change_pct,
                           "quantity_change_pct": quantity_change_pct, "grain": "one input row per product or product grouping"})


def experiment(data, *, group: str, outcome: str, control: str, treatment: str,
               binary: bool = True, guardrail: str | None = None) -> AnalysisResult:
    """Compare two independent groups; report effects and a 95% interval."""
    frame = table(data)
    require(frame, group, outcome)
    if guardrail:
        require(frame, guardrail)
    subset = frame[frame[group].isin([control, treatment])].copy()
    if control == treatment or subset[group].nunique() != 2:
        raise ValueError("Select distinct control and treatment groups with observations")
    subset["_outcome"] = numeric(subset[outcome], outcome)
    if subset["_outcome"].isna().any():
        raise ValueError("Outcomes cannot be blank")
    if binary and not subset["_outcome"].isin([0, 1]).all():
        raise ValueError("Binary outcomes must be 0 or 1; choose numeric mode for continuous outcomes")
    a = subset.loc[subset[group] == control, "_outcome"].to_numpy(dtype=float)
    b = subset.loc[subset[group] == treatment, "_outcome"].to_numpy(dtype=float)
    if min(len(a), len(b)) < 2:
        raise ValueError("Each group needs at least two observations")
    effect = float(b.mean() - a.mean())
    if binary:
        se = float(np.sqrt(a.mean() * (1 - a.mean()) / len(a) + b.mean() * (1 - b.mean()) / len(b)))
        low, high = effect - 1.96 * se, effect + 1.96 * se
        test = stats.fisher_exact([[int(b.sum()), len(b) - int(b.sum())],
                                   [int(a.sum()), len(a) - int(a.sum())]])
        pvalue = float(test.pvalue)
    else:
        test = stats.ttest_ind(b, a, equal_var=False)
        pvalue = float(test.pvalue) if np.isfinite(test.pvalue) else None
        se = float(np.sqrt(np.var(a, ddof=1) / len(a) + np.var(b, ddof=1) / len(b)))
        df = (np.var(a, ddof=1) / len(a) + np.var(b, ddof=1) / len(b)) ** 2 / (
            (np.var(a, ddof=1) / len(a)) ** 2 / (len(a) - 1) +
            (np.var(b, ddof=1) / len(b)) ** 2 / (len(b) - 1)) if se else None
        radius = float(stats.t.ppf(.975, df) * se) if df and np.isfinite(df) else 0.
        low, high = effect - radius, effect + radius
    comparison = pd.DataFrame([{"control": control, "treatment": treatment,
                                "control_n": len(a), "treatment_n": len(b),
                                "control_mean": float(a.mean()), "treatment_mean": float(b.mean()),
                                "effect_treatment_minus_control": effect,
                                "ci_95_low": low, "ci_95_high": high, "p_value": pvalue}])
    warnings = ["Statistical differences do not establish causality unless assignment and data collection were sound.",
                "The interval is approximate; inspect small samples, imbalance, and repeated users."]
    tables = {"Comparison": comparison, "Observation evidence": subset.drop(columns=["_outcome"])}
    if guardrail:
        subset["_guardrail"] = numeric(subset[guardrail], guardrail)
        if subset["_guardrail"].isna().any():
            raise ValueError("Guardrail values cannot be blank")
        tables["Guardrail"] = subset.groupby(group)["_guardrail"].agg(["count", "mean"]).reset_index()
        warnings.append("Review guardrail effects separately before making a decision.")
    verdict = "interval includes zero" if low <= 0 <= high else "interval excludes zero"
    return AnalysisResult("experiment_decision_kit", f"Treatment minus control = {effect:.4g}; 95% interval [{low:.4g}, {high:.4g}] ({verdict}).",
                          tables, warnings, {"group": group, "outcome": outcome, "binary": binary, "guardrail": guardrail})


def forecast(data, *, date: str, value: str, months: int = 3) -> AnalysisResult:
    """Monthly naive or seasonal-naive forecast chosen by a historical holdout."""
    if not 1 <= months <= 12:
        raise ValueError("Forecast horizon must be 1 to 12 months")
    frame = table(data)
    require(frame, date, value)
    frame["_date"] = dates(frame[date], date)
    frame["_value"] = numeric(frame[value], value)
    if frame["_date"].isna().any() or frame["_value"].isna().any():
        raise ValueError("Dates and values cannot be blank")
    frame["_month"] = frame["_date"].dt.to_period("M")
    monthly = frame.groupby("_month")["_value"].sum().sort_index()
    full = pd.period_range(monthly.index.min(), monthly.index.max(), freq="M")
    if len(full) != len(monthly):
        missing = full.difference(monthly.index)
        raise ValueError(f"Missing months: {', '.join(map(str, missing[:6]))}. Fill them explicitly before forecasting")
    if len(monthly) < 6:
        raise ValueError("At least six complete monthly periods are required")
    values = monthly.to_numpy(dtype=float)
    holdout = min(6, max(2, len(values) // 4))
    errors_naive = [values[i] - values[i - 1] for i in range(len(values) - holdout, len(values))]
    choices = {"last_month": np.asarray(errors_naive)}
    if len(values) >= 24:
        choices["same_month_last_year"] = np.asarray(
            [values[i] - values[i - 12] for i in range(len(values) - holdout, len(values))])
    selected = min(choices, key=lambda name: np.mean(np.abs(choices[name])))
    errors = choices[selected]
    radius = float(np.quantile(np.abs(errors), .9))
    history = pd.DataFrame({"month": monthly.index.astype(str), "actual": values})
    future = []
    for step in range(1, months + 1):
        prediction = float(values[-1] if selected == "last_month" else values[-12 + (step - 1) % 12])
        future.append({"month": str(monthly.index[-1] + step), "forecast": prediction,
                       "indicative_low": prediction - radius, "indicative_high": prediction + radius})
    accuracy = pd.DataFrame([{"method": name, "holdout_months": holdout,
                              "mean_absolute_error": float(np.mean(np.abs(e)))} for name, e in choices.items()])
    return AnalysisResult("forecast_explainer", f"{months}-month forecast uses {selected}; historical holdout MAE is {np.mean(np.abs(errors)):,.2f}.",
                          {"Forecast": pd.DataFrame(future), "Historical accuracy": accuracy,
                           "Monthly history": history, "Source rows": frame.drop(columns=["_date", "_value", "_month"])},
                          ["The displayed range is the 90th percentile of past absolute errors, not a calibrated prediction interval.",
                           "External events and business changes are not modelled."],
                          {"date": date, "value": value, "aggregation": "sum by calendar month",
                           "selected_method": selected, "holdout_months": holdout})
