# Business Analyst Tool Kit (AnalystKit)

One local-first Python package for preparing spreadsheets, answering business questions, managing requirements, and sharing repeatable reports. The analyst-facing interface uses upload → confirm → report. No external API key or hosted database is required for the core product.

> **Status:** Excel/CSV table detection, data profiling, Data Prep Assistant, Spreadsheet Audit, and a versioned Metric Dictionary are working. The remaining 12 capabilities below are planned, not yet implemented.

## Get started

Requires Python 3.10 or newer. Clone the repository and run:

```bash
python -m pip install -e '.[app]'
analystkit app
```

The command opens a local upload interface. Choose **Explore data**, **Prepare data**, **Audit workbook**, or **Define a metric**. Your file is processed on your machine; the temporary uploaded copy is removed after the run. The interface does not send the file to an AI API.

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
```

Suggestions are **not** confirmed metric definitions. In particular, do not treat an inferred `Amount` field as revenue without choosing the correct business rule.

## Product plan: one package, 16 capabilities

| Phase | Capability | User's question | Minimal input | Output |
|---|---|---|---|---|
| 1 | Data Prep Assistant **(working)** | Can I combine and clean these files? | Files, selected dates/amounts and duplicate keys | Prepared copy and change log |
| 1 | Data Profiler **(first slice working)** | What is in this file? | Table | Quality findings and source-linked workbook |
| 1 | Spreadsheet Audit **(working)** | Is this workbook reliable? | Workbook | Cell-level issues with severity |
| 1 | Metric Dictionary **(working)** | What exactly does this KPI mean? | Definition, filters, owner | Versioned draft/approved definitions |
| 2 | KPI Reconciler | Why do these reports disagree? | Two reports and metric | Difference bridge and matching rows |
| 2 | Variance & Root-Cause Explorer | Why did this number change? | Metric, comparison periods | Contribution breakdown and drill-down |
| 2 | Recurring Report Runner | What changed since last time? | Saved profile, new file | New report and schema-change warning |
| 3 | Funnel Diagnostics | Where do leads drop off? | Case ID, ordered stages | Conversion and segment report |
| 3 | Cohort Analysis | Do customers return? | Customer ID and transaction date | Retention and revenue cohorts |
| 3 | Process Bottleneck Finder | Where does work get stuck? | Case ID, activity, timestamp | Delays and repeated steps |
| 4 | Pricing & Margin Simulator | What if we change prices? | Price, cost, scenario | Profit, margin, break-even comparison |
| 4 | Experiment Decision Kit | Did our A/B test help? | Group and outcome | Effect, uncertainty, guardrails |
| 4 | Forecast Explainer | What might happen next? | Date and value | Forecast, range, historical accuracy |
| 5 | Requirements & Meeting Assistant | What was decided and requested? | Notes/document | Reviewable draft requirements and actions |
| 5 | Requirements Traceability | What is open, built, or tested? | Requirement IDs and status | Coverage and unresolved items |
| 5 | Insight-to-Report | How do I explain the findings? | Completed analysis results | Editable, evidence-linked report |

The requirements assistant will use deterministic extraction and templates in the API-free core. An optional local model could later improve drafting. Drafts always need analyst review.

## Shared experience and rules

1. **Upload and detect:** Find sheets, tables, header rows, field candidates, and source row numbers. Support renamed/reordered columns and new columns. Identify ambiguous layouts instead of choosing silently.
2. **Confirm meaning:** Ask about grain (one row per order or item), dates, currency, metric definitions, joins, and repeated events when they affect the answer. Save confirmed choices as reusable profiles.
3. **Preview the calculation:** Show selected rows, exclusions, time range, and filters before a business result is calculated.
4. **Explain and verify:** Reports separate calculated facts from possible explanations and show the input cells or rows. Reconciliation components must sum to the full difference; forecasts must show backtested error.
5. **Export and repeat:** HTML for reading, Excel for verification, JSON for automation. Reuse profiles only if critical schema and grain checks still pass.

The interface will contain **Prepare**, **Analyse**, **Manage requirements**, and **Share and repeat** sections. The Python API will call the same calculation functions as the interface. The initial implementation prioritizes file processing and correctness over a dashboard full of inactive controls.

## Development gates

- Phase 1: Inspect varied workbook layouts; profile an uploaded file; export source-linked findings; implement cleaning previews, audits, and metric definitions. **Initial implementation complete.** Further workbook layouts and usability refinement remain.
- Phase 2: Reconcile unmatched rows and build a mathematically complete variance bridge; save and rerun mappings with schema-change checks.
- Phase 3: Handle repeated stage events, transactions at different grains, and incomplete cases with explicit rules.
- Phase 4: Test simulations against hand-calculated scenarios; backtest forecasts and display uncertainty; avoid unsupported causal claims from experiments.
- Phase 5: Separate draft requirements from approved ones and keep report claims connected to source calculations.

Run the current tests with `python -m pip install -e '.[test]'` followed by `pytest -q`.

## Scope of the first release

The current importer supports `.xlsx`, `.xlsm`, and `.csv`; it does not run spreadsheet macros or recalculate formulas. Excel formula values may need to be recalculated and saved in Excel before numerical analysis. Data preparation combines rows, trims spaces, parses selected dates and amounts, and flags duplicate keys; it does not join tables or automatically align differently named columns in the interface. Use the Python `rename` argument for explicit alignment. Slash-formatted dates that could mean either day/month or month/day are set aside for review. The metric calculation is currently documentation, not executable SQL or a formula engine. The audit flags potential issues for human review; it cannot prove that every unusual formula is wrong. Large workbooks, merged headers, multiple adjacent tables in one sheet, and legacy `.xls` files will need further work.
