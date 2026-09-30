"""Small command-line entry points for local analysts and scheduled jobs."""

import argparse
from pathlib import Path

from .profile import profile
from .workbook import inspect
from .prep import prepare
from .audit import audit


def main() -> None:
    parser = argparse.ArgumentParser(prog="analystkit", description="Analyse spreadsheets locally, without API keys")
    sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("inspect", help="Show possible tables and header rows")
    scan.add_argument("file")
    run = sub.add_parser("profile", help="Produce a data profile")
    run.add_argument("file")
    run.add_argument("--sheet")
    run.add_argument("--header-row", type=int)
    run.add_argument("--output", default="profile.html")
    clean = sub.add_parser("prepare", help="Combine and clean files with source and change logs")
    clean.add_argument("files", nargs="+")
    clean.add_argument("--date", action="append", default=[])
    clean.add_argument("--amount", action="append", default=[])
    clean.add_argument("--duplicate-key", action="append", default=[])
    clean.add_argument("--output", default="prepared.xlsx")
    check = sub.add_parser("audit", help="Audit a workbook for cell and formula issues")
    check.add_argument("file")
    check.add_argument("--output", default="audit.xlsx")
    sub.add_parser("app", help="Open the local upload interface")
    args = parser.parse_args()
    if args.command == "app":
        try:
            from streamlit.web import cli as stcli
        except ImportError as exc:
            raise SystemExit("Install the interface with: pip install '.[app]'") from exc
        import sys
        sys.argv = ["streamlit", "run", str(Path(__file__).with_name("app.py"))]
        stcli.main()
    elif args.command == "inspect":
        result = inspect(args.file)
        for candidate in result.candidates:
            print(f"{candidate.sheet}: header row {candidate.header_row}; {len(candidate.columns)} columns; score {candidate.score:.1f}")
        for warning in result.warnings:
            print(f"Review: {warning}")
    elif args.command == "prepare":
        result = prepare(args.files, date_columns=args.date, amount_columns=args.amount, dedupe_keys=args.duplicate_key)
        print(f"Saved {result.save(args.output)}")
        for warning in result.warnings:
            print(f"Review: {warning}")
    elif args.command == "audit":
        result = audit(args.file)
        print(f"Saved {result.save(args.output)} with {len(result.findings)} findings")
    else:
        report = profile(args.file, sheet=args.sheet, header_row=args.header_row)
        print(f"Saved {report.save(args.output)}")
