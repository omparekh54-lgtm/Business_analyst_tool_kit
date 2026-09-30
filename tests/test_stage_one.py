from openpyxl import Workbook
import pandas as pd
import pytest

from analystkit import MetricCatalog, audit, prepare


def test_prep_preserves_source_and_flags_duplicates(tmp_path):
    first = tmp_path / "aug.csv"
    second = tmp_path / "sep.csv"
    first.write_text("Invoice Dt,Order ID,Net Value\n2026-08-01,A,₹1,200\n2026-08-02,B,bad\n".replace("₹1,200", '"₹1,200"'), encoding="utf-8")
    second.write_text("Invoice Dt,Order ID,Net Value\n2026-09-01,A,500\n", encoding="utf-8")
    result = prepare([first, second], date_columns=["Invoice Dt"], amount_columns=["Net Value"], dedupe_keys=["Order ID"])
    assert result.source_count == 2
    assert len(result.data) == 3
    assert result.data["Net Value"].iloc[0] == 1200
    assert result.data["_source_row"].tolist() == [2, 3, 2]
    assert result.data["_possible_duplicate"].sum() == 2
    assert result.data["_original_Net Value"].iloc[1] == "bad"
    assert any("could not be parsed" in w for w in result.warnings)
    result.save(tmp_path / "prepared.xlsx")
    assert "Changes" in pd.ExcelFile(tmp_path / "prepared.xlsx").sheet_names


def test_audit_issues_have_exact_cells(tmp_path):
    path = tmp_path / "budget.xlsx"
    book = Workbook()
    sheet = book.active
    sheet.title = "Budget"
    sheet.append(["Item", "Value", "Double"])
    for i in range(2, 6):
        sheet.append([f"P{i}", i, f"=B{i}*2"])
    sheet["C4"] = 99
    sheet["C5"] = "=#REF!*2"
    hidden = book.create_sheet("Inputs")
    hidden.sheet_state = "hidden"
    book.save(path)
    report = audit(path)
    assert any(f.category == "broken reference" and f.cell == "C5" for f in report.findings)
    assert any(f.category == "fixed value in formula column" and f.cell == "C4" for f in report.findings)
    assert any(f.category == "hidden sheet" and f.sheet == "Inputs" for f in report.findings)
    report.save(tmp_path / "audit.xlsx")


def test_metric_versions_keep_approved_definition(tmp_path):
    catalog = MetricCatalog()
    first = catalog.add(key="net_sales", name="Net sales", description="Sales after refunds",
                        calculation="Invoice amounts minus refunds", source="Invoices and refunds",
                        grain="One row per invoice", owner="Finance", status="approved")
    second = catalog.add(key="net_sales", name="Net sales", description="Proposed change",
                         calculation="Invoice amounts minus refunds and discounts", source="Invoices and refunds",
                         grain="One row per invoice", owner="Finance")
    assert first.version == 1 and second.version == 2
    restored = MetricCatalog.load(catalog.save(tmp_path / "metrics.json"))
    assert restored.latest("net_sales").status == "draft"
    assert restored.latest("net_sales", approved_only=True).version == 1
    with pytest.raises(ValueError):
        catalog.add(key="bad key", name="Invalid", description="X", calculation="X", source="X", grain="X", owner="X")


def test_ambiguous_slash_date_is_kept_for_review(tmp_path):
    source = tmp_path / "dates.csv"
    source.write_text("Date,Order ID\n03/04/2026,A\n2026-04-15,B\n", encoding="utf-8")
    result = prepare([source], date_columns=["Date"])
    assert pd.isna(result.data.loc[0, "Date"])
    assert result.data.loc[0, "_original_Date"] == "03/04/2026"
    assert result.data.loc[1, "Date"].day == 15
    assert any("day/month or month/day" in message for message in result.warnings)


def test_prepare_aligns_equivalent_columns_in_different_files(tmp_path):
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    first.write_text("Order ID,Net Value\nA,10\n")
    second.write_text("Invoice No,Sales Amount\nB,20\n")
    result = prepare([first, second], per_file_rename={"second.csv": {
        "Invoice No": "Order ID", "Sales Amount": "Net Value"}},
        amount_columns=["Net Value"])
    assert result.data["Net Value"].tolist() == [10.0, 20.0]
    assert "Invoice No" not in result.data
    assert any(result.changes["action"] == "align column names")
