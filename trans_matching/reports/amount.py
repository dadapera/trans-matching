from pathlib import Path

from trans_matching.matchers.amount import MatchResult
from trans_matching.reports.html import generate_html_report

__all__ = ["generate_amount_report", "generate_html_report"]


def generate_amount_report(results: list[MatchResult], output_path: Path) -> None:
    from trans_matching.storage import save_run

    run_id = save_run(results)
    generate_html_report(output_path, run_id=run_id)
