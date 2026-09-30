import json

import pandas as pd
import pytest

from analystkit import (cohorts, experiment, forecast, funnel, insight_report,
                        meeting_assistant, pricing, process_bottlenecks, reconcile,
                        run_saved, save_setup, traceability, variance)


def test_reconciliation_bridge_balances_and_rejects_repeated_keys():
    left = pd.DataFrame({"ID": ["A", "B"], "Amount": [100, 30]})
    right = pd.DataFrame({"ID": ["A", "C"], "Amount": [110, 50]})
    result = reconcile(left, right, key="ID", amount="Amount")
    assert result.tables["Totals"].iloc[0]["difference"] == 30
    assert result.tables["Difference bridge"]["contribution"].sum() == 30
    assert len(result.tables["Matched source rows"]) == 3
    with pytest.raises(ValueError, match="unique"):
        reconcile(pd.concat([left, left]), right, key="ID", amount="Amount")


def test_variance_contributions_add_to_change():
    data = pd.DataFrame({"Date": ["2026-01-05", "2026-01-10", "2026-02-01", "2026-02-02"],
                         "Region": ["West", "East", "West", "North"], "Sales": [10, 20, 25, 5]})
    result = variance(data, date="Date", amount="Sales", segment="Region",
                      start_a="2026-01-01", end_a="2026-01-31",
                      start_b="2026-02-01", end_b="2026-02-28")
    assert result.tables["Contribution by segment"]["change"].sum() == 0
    assert set(result.tables["Contribution by segment"]["segment"]) == {"West", "East", "North"}


def test_funnel_repeated_events_and_case_evidence():
    data = pd.DataFrame({"Lead": ["A", "A", "A", "A", "B", "B", "C"],
                         "Stage": ["Lead", "Quote", "Quote", "Order", "Lead", "Quote", "Quote"],
                         "Time": ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04",
                                  "2026-01-01", "2026-01-05", "2026-01-01"]})
    result = funnel(data, case_id="Lead", stage="Stage", timestamp="Time", stages=["Lead", "Quote", "Order"])
    assert result.tables["Funnel"]["cases"].tolist() == [2, 2, 1]
    assert len(result.tables["Case evidence"]) == 3
    assert "repeated" in result.warnings[0]


def test_cohorts_retention_uses_distinct_customers():
    data = pd.DataFrame({"Customer": ["A", "A", "A", "B", "B"],
                         "Date": ["2026-01-01", "2026-01-31", "2026-02-01", "2026-01-05", "2026-02-08"],
                         "Amount": [10, 12, 20, 5, 8]})
    result = cohorts(data, customer_id="Customer", date="Date", amount="Amount")
    activity = result.tables["Cohort activity"]
    assert activity.loc[activity["months_since_first"] == 0, "active_customers"].iloc[0] == 2
    assert activity.loc[activity["months_since_first"] == 1, "retention"].iloc[0] == 1
    assert activity.loc[activity["months_since_first"] == 0, "revenue"].iloc[0] == 27


def test_process_bottlenecks_counts_waits():
    data = pd.DataFrame({"Case": [1, 1, 1, 2, 2], "Activity": ["Open", "Review", "Done", "Open", "Done"],
                         "Time": ["2026-01-01", "2026-01-02", "2026-01-04", "2026-01-01", "2026-01-03"]})
    result = process_bottlenecks(data, case_id="Case", activity="Activity", timestamp="Time")
    assert result.tables["Event evidence"]["hours"].sum() == 120
    assert set(result.tables["Slow transitions"]["from_activity"]) == {"Open", "Review"}


def test_pricing_scenario_matches_hand_calculation():
    data = pd.DataFrame({"Product": ["P"], "Price": [100], "Cost": [60], "Units": [10]})
    result = pricing(data, product="Product", price="Price", cost="Cost", quantity="Units",
                     price_change_pct=10, quantity_change_pct=-20)
    totals = result.tables["Scenario totals"].iloc[0]
    assert totals["current_profit"] == 400
    assert totals["proposed_profit"] == pytest.approx(400)
    assert totals["profit_change"] == pytest.approx(0)


def test_experiment_binary_and_continuous():
    data = pd.DataFrame({"Group": ["A"] * 12 + ["B"] * 12,
                         "Bought": [0] * 10 + [1] * 2 + [1] * 8 + [0] * 4,
                         "Spend": list(range(12)) + list(range(2, 14))})
    binary = experiment(data, group="Group", outcome="Bought", control="A", treatment="B")
    assert binary.tables["Comparison"].iloc[0]["effect_treatment_minus_control"] == pytest.approx(.5)
    continuous = experiment(data, group="Group", outcome="Spend", control="A", treatment="B", binary=False)
    assert continuous.tables["Comparison"].iloc[0]["effect_treatment_minus_control"] == pytest.approx(2)


def test_forecast_backtests_and_rejects_missing_month():
    months = pd.period_range("2024-01", periods=28, freq="M")
    data = pd.DataFrame({"Month": [str(m.start_time.date()) for m in months],
                         "Sales": [100 + i % 12 for i in range(28)]})
    result = forecast(data, date="Month", value="Sales", months=2)
    assert len(result.tables["Forecast"]) == 2
    assert result.definitions["selected_method"] == "same_month_last_year"
    with pytest.raises(ValueError, match="Missing months"):
        forecast(data.drop(index=10), date="Month", value="Sales")


def test_meeting_drafts_unclassified_and_traceability(tmp_path):
    notes = "Decision: Use monthly reports\nAction: Send sample file; owner: Aayushi\nNeed: Track revenue\nMaybe use another chart"
    result = meeting_assistant(notes)
    assert len(result.tables["Draft items"]) == 3
    assert len(result.tables["Unclassified lines"]) == 1
    requirements = pd.DataFrame({"ID": ["R1", "R2"], "Status": ["accepted", "draft"],
                                 "Design": ["D1", ""], "Test": ["T1", ""]})
    traced = traceability(requirements, requirement_id="ID", status="Status", design="Design", test="Test")
    assert traced.tables["Requirement coverage"]["review_flags"].str.contains("Missing test").sum() == 1
    combined = insight_report([result, traced], audience="Manager")
    assert len(combined.tables["Executive overview"]) == 2
    combined.save(tmp_path / "summary.html")
    combined.save(tmp_path / "summary.xlsx")


def test_recurring_setup_detects_schema_change_and_differences(tmp_path):
    initial = tmp_path / "first.csv"
    next_file = tmp_path / "next.csv"
    initial.write_text("Date,Region,Sales\n2026-01-01,A,10\n2026-02-01,A,20\n")
    next_file.write_text("Region,Sales,Date,Extra\nA,10,2026-01-01,x\nA,30,2026-02-01,y\n")
    params = {"date": "Date", "amount": "Sales", "segment": "Region",
              "start_a": "2026-01-01", "end_a": "2026-01-31",
              "start_b": "2026-02-01", "end_b": "2026-02-28"}
    setup = save_setup(tmp_path / "setup.json", task="variance", sample_files=[initial], parameters=params)
    old = run_saved(setup, [initial])
    old.save(tmp_path / "previous.json")
    updated = run_saved(setup, [next_file], previous=tmp_path / "previous.json")
    assert "Changes since last run" in updated.tables
    assert any("Contribution by segment" in item for item in updated.tables["Changes since last run"]["item"])
    assert "A" in updated.tables["Current Contribution by segment"]["segment"].tolist()
    bad = tmp_path / "bad.csv"
    bad.write_text("Date,Region,Profit\n2026-01-01,A,10\n")
    with pytest.raises(ValueError, match="Critical columns"):
        run_saved(setup, [bad])
    renamed = tmp_path / "renamed.csv"
    renamed.write_text("Date,Region,Net Sales\n2026-01-01,A,10\n2026-02-01,A,31\n")
    remapped = run_saved(setup, [renamed], column_maps_override=[{"Net Sales": "Sales"}])
    assert remapped.tables["Contribution by segment"]["change"].iloc[0] == 21
