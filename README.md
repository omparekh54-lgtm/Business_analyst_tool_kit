# Business Analyst Tool Kit (AnalystKit)

One local-first Python package for preparing spreadsheets, answering business questions, managing requirements, and sharing repeatable reports. The analyst-facing interface uses upload → confirm → report. No external API key or hosted database is required for the core product.

> **Status:** The first working slice supports Excel/CSV table detection, conservative field suggestions, data profiling, and HTML/Excel/JSON export. The other capabilities below are planned, not yet implemented.

## Get started

Requires Python 3.10 or newer. Clone the repository and run:

```bash
python -m pip install -e '.[app]'
analystkit app
```

The command opens a local upload interface. Choose an `.xlsx`, `.xlsm`, or `.csv` file, confirm the sheet and header row, and create a profile. Your file is processed on your machine; the temporary uploaded copy is removed after the run. The interface does not send the file to an AI API.

Command-line and Python usage:

```bash
analystkit inspect sales.xlsx
analystkit profile sales.xlsx --sheet Orders --header-row 4 --output profile.html
```

```python
from analystkit import inspect, profile

print(inspect('sales.xlsx').candidates)
result = profile('sales.xlsx', sheet='Orders', header_row=4)
result.save('profile.xlsx')  # .html and .json are also supported
```

Suggestions are **not** confirmed metric definitions. In particular, do not treat an inferred `Amount` field as revenue without choosing the correct business rule.

## Product plan: one package, 16 capabilities

| Phase | Capability | User's question | Minimal input | Output |
|---|---|---|---|---|
| 1 | Data Prep Assistant | Can I combine and clean these files? | Files, join keys if joining | Cleaned copy and change log |
| 1 | Data Profiler **(first slice working)** | What is in this file? | Table | Quality findings and source-linked workbook |
| 1 | Spreadsheet Audit | Is this workbook reliable? | Workbook | Cell-level issues with severity |
| 1 | Metric Dictionary | What exactly does this KPI mean? | Approved formula, filters, owner | Versioned reusable definition |
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

- Phase 1: Inspect varied workbook layouts; profile an uploaded file; export source-linked findings; implement cleaning previews, audits, and metric definitions.
- Phase 2: Reconcile unmatched rows and build a mathematically complete variance bridge; save and rerun mappings with schema-change checks.
- Phase 3: Handle repeated stage events, transactions at different grains, and incomplete cases with explicit rules.
- Phase 4: Test simulations against hand-calculated scenarios; backtest forecasts and display uncertainty; avoid unsupported causal claims from experiments.
- Phase 5: Separate draft requirements from approved ones and keep report claims connected to source calculations.

Run the current tests with `python -m pip install -e '.[test]'` followed by `pytest -q`.

## Scope of the first release

The current importer supports `.xlsx`, `.xlsm`, and `.csv`; it does not run spreadsheet macros or recalculate formulas. Excel formula values may need to be recalculated and saved in Excel before numerical analysis. Large workbooks, merged headers, multiple adjacent tables in one sheet, and legacy `.xls` files will need further work. The interface currently provides Data Profiler only. This scope is shown in the UI so analysts do not mistake a roadmap item for a working function.
