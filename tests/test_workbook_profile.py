from pathlib import Path

from openpyxl import Workbook
import pandas as pd
import pytest

from analystkit import inspect, profile, suggest_fields


def make_book(path: Path) -> None:
    book = Workbook()
    sheet = book.active
    sheet.title = "Notes"
    sheet.append(["Monthly export"])
    orders = book.create_sheet("Orders")
    orders.append(["Confidential sales export"])
    orders.append([])
    orders.append([None, "Invoice Dt", "Client Code", "Net Value", "Invoice No", "Analyst Comment"])
    orders.append([None, "2026-08-01", "A", 100, "I-1"])
    orders.append([None, "2026-08-02", "B", 150, "I-2"])
    orders.append([None, "2026-08-03", "A", None, "I-3"])
    book.save(path)


def test_shifted_header_and_source_evidence(tmp_path):
    path = tmp_path / "orders.xlsx"
    make_book(path)
    choices = inspect(path).candidates
    assert choices[0].sheet == "Orders"
    assert choices[0].header_row == 3
    report = profile(path, sheet="Orders", header_row=3)
    assert report.row_count == 3
    assert report.source_rows["_source_row"].tolist() == [4, 5, 6]
    assert any("Net Value: 1 blank" in finding for finding in report.findings)
    assert any("Analyst Comment: 3 blank" in finding for finding in report.findings)
    assert next(s for s in report.suggestions if s.field == "date").column == "Invoice Dt"
    assert next(s for s in report.suggestions if s.field == "amount").column == "Net Value"
    assert report.save(tmp_path / "report.html").exists()
    assert report.save(tmp_path / "report.xlsx").exists()
    assert report.save(tmp_path / "report.json").exists()


def test_ambiguous_amount_requires_confirmation():
    frame = pd.DataFrame({"Net Amount": [10], "Total": [12]})
    amount = next(s for s in suggest_fields(frame) if s.field == "amount")
    assert amount.needs_confirmation
    assert amount.alternatives


def test_csv_with_title_row_and_shifted_header(tmp_path):
    path = tmp_path / "sales.csv"
    path.write_text("Monthly sales export\nDate,Order ID,Amount\n2026-08-01,A,10\n2026-08-02,B,20\n", encoding="utf-8")
    result = profile(path)
    assert result.header_row == 2
    assert result.row_count == 2
    assert result.source_rows["_source_row"].tolist() == [3, 4]


def test_unsupported_input(tmp_path):
    path = tmp_path / "old.xls"
    path.write_bytes(b"not an Excel file")
    with pytest.raises(ValueError, match="Supported inputs"):
        inspect(path)
