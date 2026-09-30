# Business Analyst Tool Kit (AnalystKit)

One local-first Python package for preparing spreadsheets, answering business questions, managing requirements, and sharing repeatable reports. The analyst-facing interface uses upload → confirm → report. No external API key or hosted database is required for the core product.

> **Status:** All 16 capabilities have initial local implementations and upload screens. These are tested with representative fixtures, but broader validation against diverse real business workbooks is still needed before production use.

## Get started

Requires Python 3.10 or newer. Clone the repository and run:

```bash
python -m pip install -e '.[app]'
analystkit app
```

The command opens a local upload interface with all 16 tasks. Choose the task, upload the files, confirm the selected table and business fields, and review the result and supporting rows. Download HTML, Excel, or JSON reports. Your file is processed on your machine; the temporary uploaded copy is removed after the run. The interface does not send the file to an AI API.

Command-line and Python usage:

```bash
analystkit inspect sales.xlsx
analystkit profile sales.xlsx --sheet Orders --header-row 4 --output profile.html
analystkit prepare august.csv september.csv --date "Invoice Dt" --amount "Net Value" --duplicate-key "Order ID" --output prepared.xlsx
analystkit audit budget.xlsx --output audit.xlsx
```

```python
from analystkit import inspect, profile

print(inspect('sales.xlsx').candidates)
result = profile('sales.xlsx', sheet='Orders', header_row=4)
result.save('profile.xlsx')  # .html and .json are also supported

from analystkit import prepare, audit, MetricCatalog
prepared = prepare(['august.csv', 'september.csv'], amount_columns=['Net Value'])
prepared.save('prepared.xlsx')  # Prepared rows, changes, warnings
audit('budget.xlsx').save('audit.xlsx')

catalog = MetricCatalog()
catalog.add(key='net_sales', name='Net sales', description='Sales after refunds',
            calculation='Invoice amount minus refunded amount', source='Invoices and refunds',
            grain='One row per invoice', owner='Finance', status='approved')
catalog.save('metrics.json')

from analystkit import reconcile, variance, forecast
result = reconcile('sales.xlsx', 'finance.xlsx', key='Invoice ID', amount='Net Amount')
result.save('reconciliation.xlsx')

forecast_result = forecast('monthly_sales.xlsx', date='Month', value='Sales', months=3)
forecast_result.save('forecast.html')

from analystkit import save_setup, run_saved
settings = dict(date='Date', amount='Sales', segment='Region',
                start_a='2026-01-01', end_a='2026-01-31',
                start_b='2026-02-01', end_b='2026-02-28')
save_setup('setup.json', task='variance', sample_files=['january_february.csv'], parameters=settings)
baseline = run_saved('setup.json', ['january_february.csv'])
baseline.save('baseline.json')
updated = run_saved('setup.json', ['new_export.csv'], previous='baseline.json')
updated.save('monthly_change.html')
```

Suggestions are **not** confirmed metric definitions. In particular, do not treat an inferred `Amount` field as revenue without choosing the correct business rule.

## Product plan: one package, 16 capabilities

| Phase | Capability | User's question | Minimal input | Output |
|---|---|---|---|---|
| 1 | Data Prep Assistant **(working)** | Can I combine and clean these files? | Files, selected dates/amounts and duplicate keys | Prepared copy and change log |
| 1 | Data Profiler **(working)** | What is in this file? | Table | Quality findings and source-linked workbook |
| 1 | Spreadsheet Audit **(working)** | Is this workbook reliable? | Workbook | Cell-level issues with severity |
| 1 | Metric Dictionary **(working)** | What exactly does this KPI mean? | Definition, filters, owner | Versioned draft/approved definitions |
| 2 | KPI Reconciler **(working)** | Why do these reports disagree? | Two reports and unique key | Exact difference bridge and matching rows |
| 2 | Variance Explorer **(working)** | Where did this number change? | Metric, comparison periods | Segment contribution breakdown |
| 2 | Recurring Report Runner **(working)** | What changed since last time? | Saved setup, new file, previous result optional | Updated report and schema-change review |
| 3 | Funnel Diagnostics **(working)** | Where do leads drop off? | Case ID, stages, event time | Conversion and case evidence |
| 3 | Cohort Analysis **(working)** | Do customers return? | Customer ID and transaction date | Retention and revenue cohorts |
| 3 | Process Bottleneck Finder **(working)** | Where does work get stuck? | Case ID, activity, timestamp | Waiting time and repeated steps |
| 4 | Pricing & Margin Simulator **(working)** | What if we change prices? | Price, cost, volume assumptions | Profit, margin, break-even comparison |
| 4 | Experiment Decision Kit **(working)** | Did the groups differ? | Group and outcome | Effect, uncertainty, guardrail summary |
| 4 | Forecast Explainer **(working)** | What might happen next? | Monthly date and value | Baseline forecast and historical error |
| 5 | Requirements & Meeting Assistant **(working)** | What was explicitly decided and requested? | Labelled notes | Reviewable draft items and unclassified lines |
| 5 | Requirements Traceability **(working)** | What is open, built, or tested? | Requirement IDs and status | Coverage and unresolved links |
| 5 | Insight-to-Report **(working)** | How do I explain the findings? | Exported analysis JSON | Shareable evidence-linked report |

The requirements assistant will use deterministic extraction and templates in the API-free core. An optional local model could later improve drafting. Drafts always need analyst review.

## Shared experience and rules

1. **Upload and detect:** Find sheets, tables, header rows, field candidates, and source row numbers. Support renamed/reordered columns and new columns. Identify ambiguous layouts instead of choosing silently.
2. **Confirm meaning:** Ask about grain (one row per order or item), dates, currency, metric definitions, joins, and repeated events when they affect the answer. Save confirmed choices as reusable profiles.
3. **Preview the calculation:** Show selected rows, exclusions, time range, and filters before a business result is calculated.
4. **Explain and verify:** Reports separate calculated facts from possible explanations and show the input cells or rows. Reconciliation components must sum to the full difference; forecasts must show backtested error.
5. **Export and repeat:** HTML for reading, Excel for verification, JSON for automation. Reuse profiles only if critical schema and grain checks still pass.

The local interface offers a **Save this setup for next time** download after a successful repeatable analysis. Upload that file in **Rerun a saved analysis**, choose the new table, and confirm any renamed critical column. For a previous-run comparison, also upload its JSON report.

The interface will contain **Prepare**, **Analyse**, **Manage requirements**, and **Share and repeat** sections. The Python API will call the same calculation functions as the interface. The initial implementation prioritizes file processing and correctness over a dashboard full of inactive controls.

## Development gates

- Phase 1: Inspect varied workbook layouts; profile an uploaded file; export source-linked findings; implement cleaning previews, audits, and metric definitions. **Initial implementation complete.** Further workbook layouts and usability refinement remain.
- Phase 2: Exact reconciliation bridges, additive segment changes, and saved reruns with critical-field review. **Initial implementation complete.**
- Phase 3: Ordered stages, distinct-customer cohorts, and event-level waiting times. **Initial implementation complete.**
- Phase 4: Hand-checked scenarios, baseline forecast backtests, and group comparison uncertainty. **Initial implementation complete.**
- Phase 5: Labelled-note extraction, draft traceability, and source-preserving combined reports. **Initial implementation complete.**
- Release hardening: Real workbook trials, accessibility and upload walkthroughs, larger-file performance, additional edge-case fixtures, and packaged distribution. **Remaining.**

Run the current tests with `python -m pip install -e '.[test]'` followed by `pytest -q`.

## Scope of the first release

The current importer supports `.xlsx`, `.xlsm`, and `.csv`; it does not run macros or recalculate formulas. Excel formula values may need to be recalculated and saved in Excel before numerical analysis. Data preparation combines rows, trims spaces, parses selected dates and amounts, and flags duplicate keys; it does not join tables or automatically align differently named columns in the interface. Use the Python `rename` argument for explicit alignment. Ambiguous slash dates are set aside for review. The metric calculation is documentation, not executable SQL. The audit flags possible issues, not proven errors. Forecast ranges reflect past errors, not calibrated prediction intervals. Experiment output does not establish causal impact without a valid assignment design. Meeting extraction recognises explicit labels and leaves other notes unclassified; it does not invent acceptance criteria. Large workbooks, merged headers, multiple adjacent tables in one sheet, and legacy `.xls` files need further work.
