"""Customer and case journeys with explicit event rules."""

import pandas as pd

from .results import AnalysisResult, dates, numeric, require, table


def funnel(data, *, case_id: str, stage: str, timestamp: str,
           stages: list[str]) -> AnalysisResult:
    """Count cases reaching ordered stages after the previous stage."""
    if len(stages) < 2 or len(set(stages)) != len(stages):
        raise ValueError("Choose at least two distinct stages in order")
    frame = table(data)
    require(frame, case_id, stage, timestamp)
    if frame[[case_id, stage, timestamp]].isna().any().any():
        raise ValueError("Case, stage, and time are required for every event")
    frame["_time"] = dates(frame[timestamp], timestamp)
    frame = frame[frame[stage].isin(stages)].sort_values([case_id, "_time", "_source_row"])
    if frame.empty:
        raise ValueError("No events match the selected stages")
    rows = []
    counts = dict.fromkeys(stages, 0)
    duration = {name: [] for name in stages[1:]}
    for case, events in frame.groupby(case_id, sort=False):
        previous = None
        record = {case_id: case}
        for position, label in enumerate(stages):
            eligible = events[(events[stage] == label) & ((events["_time"] >= previous) if previous is not None else True)]
            if eligible.empty:
                break
            event = eligible.iloc[0]
            current = event["_time"]
            record[f"{label} time"] = current
            record[f"{label} row"] = int(event["_source_row"])
            counts[label] += 1
            if position:
                duration[label].append((current - previous).total_seconds() / 3600)
            previous = current
        rows.append(record)
    stats = []
    for index, label in enumerate(stages):
        prior = counts[stages[index - 1]] if index else counts[label]
        stats.append({"stage": label, "cases": counts[label],
                      "conversion_from_previous": counts[label] / prior if prior else None,
                      "dropped_from_previous": prior - counts[label] if index else 0,
                      "median_hours_since_previous": float(pd.Series(duration[label]).median()) if index and duration[label] else None})
    repeated = int(frame.duplicated(subset=[case_id, stage]).sum())
    return AnalysisResult("funnel_diagnostics", f"{counts[stages[0]]} cases started; {counts[stages[-1]]} reached {stages[-1]}.",
                          {"Funnel": pd.DataFrame(stats), "Case evidence": pd.DataFrame(rows)},
                          [f"{repeated} repeated case-stage events; the first eligible event was used."] if repeated else [],
                          {"case_id": case_id, "stage": stage, "timestamp": timestamp, "ordered_stages": stages})


def cohorts(data, *, customer_id: str, date: str, amount: str | None = None) -> AnalysisResult:
    """Calendar-month acquisition cohorts and repeat activity."""
    frame = table(data)
    require(frame, customer_id, date)
    if frame[customer_id].isna().any():
        raise ValueError("Customer IDs cannot be blank")
    frame["_date"] = dates(frame[date], date)
    if frame["_date"].isna().any():
        raise ValueError("Transaction dates cannot be blank")
    if amount:
        require(frame, amount)
        frame["_amount"] = numeric(frame[amount], amount)
        if frame["_amount"].isna().any():
            raise ValueError("Blank amounts need a confirmed treatment")
    frame["_month"] = frame["_date"].dt.to_period("M")
    first = frame.groupby(customer_id)["_month"].min()
    frame["_cohort"] = frame[customer_id].map(first)
    frame["_age"] = (frame["_month"].dt.year - frame["_cohort"].dt.year) * 12 + (frame["_month"].dt.month - frame["_cohort"].dt.month)
    sizes = first.value_counts()
    grouped = frame.groupby(["_cohort", "_age"])
    activity = grouped[customer_id].nunique().rename("active_customers").reset_index()
    activity["cohort_size"] = activity["_cohort"].map(sizes)
    activity["retention"] = activity["active_customers"] / activity["cohort_size"]
    if amount:
        revenues = grouped["_amount"].sum().rename("revenue").reset_index()
        activity = activity.merge(revenues, on=["_cohort", "_age"])
    activity["_cohort"] = activity["_cohort"].astype(str)
    evidence = frame[[customer_id, date, "_source_row", "_cohort", "_age"] + ([amount] if amount else [])].copy()
    evidence["_cohort"] = evidence["_cohort"].astype(str)
    return AnalysisResult("cohort_analysis", f"Analysed {len(sizes) and len(first)} customers across {len(sizes)} acquisition months.",
                          {"Cohort activity": activity.rename(columns={"_cohort": "cohort_month", "_age": "months_since_first"}),
                           "Transaction evidence": evidence},
                          ["Recent cohorts have had less time to reach later months; compare equal cohort ages."],
                          {"customer_id": customer_id, "date": date, "amount": amount,
                           "cohort_rule": "customer's first observed transaction month"})


def process_bottlenecks(data, *, case_id: str, activity: str, timestamp: str) -> AnalysisResult:
    """Rank transitions by waiting time; preserve event rows for investigation."""
    frame = table(data)
    require(frame, case_id, activity, timestamp)
    if frame[[case_id, activity, timestamp]].isna().any().any():
        raise ValueError("Case, activity, and timestamp must be present")
    frame["_time"] = dates(frame[timestamp], timestamp)
    frame = frame.sort_values([case_id, "_time", "_source_row"]).copy()
    frame["_next_activity"] = frame.groupby(case_id)[activity].shift(-1)
    frame["_next_time"] = frame.groupby(case_id)["_time"].shift(-1)
    frame["_next_row"] = frame.groupby(case_id)["_source_row"].shift(-1)
    frame["_hours"] = (frame["_next_time"] - frame["_time"]).dt.total_seconds() / 3600
    transitions = frame.dropna(subset=["_next_activity"]).copy()
    if transitions.empty:
        raise ValueError("At least one case needs two events")
    stats = transitions.groupby([activity, "_next_activity"], dropna=False)["_hours"].agg(
        cases="count", median_hours="median", mean_hours="mean", total_hours="sum").reset_index()
    stats = stats.rename(columns={activity: "from_activity", "_next_activity": "to_activity"}).sort_values("total_hours", ascending=False)
    repeated = frame.duplicated(subset=[case_id, activity], keep=False)
    evidence = transitions[[case_id, activity, "_next_activity", "_source_row", "_next_row", "_hours"]].rename(
        columns={activity: "from_activity", "_next_activity": "to_activity", "_source_row": "from_row", "_next_row": "to_row", "_hours": "hours"})
    return AnalysisResult("process_bottleneck_finder", f"Analysed {len(transitions)} transitions across {frame[case_id].nunique()} cases.",
                          {"Slow transitions": stats, "Event evidence": evidence},
                          [f"{int(repeated.sum())} events repeat an activity within a case; investigate rework.",
                           "Time between timestamps includes queues and non-working hours unless the input excludes them."],
                          {"case_id": case_id, "activity": activity, "timestamp": timestamp})
