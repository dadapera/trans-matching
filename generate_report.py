"""Rigenera il report HTML da una run salvata in matching.db."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from trans_matching.paths import DB_PATH, REPORT_AMOUNT
from trans_matching.reports.html import generate_html_report
from trans_matching.storage import list_runs


def _print_runs() -> None:
    runs = list_runs()
    if not runs:
        print(f"Nessuna run in {DB_PATH}", file=sys.stderr)
        return

    print(f"Run in {DB_PATH}:\n")
    for run in runs:
        matcher = run.expedia_matcher
        if run.openai_model:
            matcher = f"{matcher} ({run.openai_model})"
        print(
            f"  #{run.id}  {run.created_at}  "
            f"{run.matched_count}/{run.total_transactions} match  [{matcher}]"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Rigenera report_matching.html da una run salvata nel database.",
    )
    parser.add_argument(
        "-r",
        "--run-id",
        type=int,
        help="ID run da usare (default: ultima run)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=REPORT_AMOUNT,
        help=f"Percorso file HTML di output (default: {REPORT_AMOUNT.name})",
    )
    parser.add_argument(
        "-l",
        "--list",
        action="store_true",
        help="Elenca le run salvate e esci",
    )
    args = parser.parse_args(argv)

    if args.list:
        _print_runs()
        return 0

    try:
        generate_html_report(args.output, run_id=args.run_id)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    run_label = f"#{args.run_id}" if args.run_id is not None else "ultima"
    print(f"Report generato: {args.output} (run {run_label})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
